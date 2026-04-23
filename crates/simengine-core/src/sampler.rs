use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use rand_distr::{Binomial, Distribution};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::f64::consts::PI;

const NEGATIVE_INF_CLAMP: f64 = -1e18;
const POSITIVE_INF_CLAMP: f64 = 1e18;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VariableSamplerSpec {
    pub distribution: String,
    #[serde(default)]
    pub params: BTreeMap<String, f64>,
}

pub fn sample_variable_grid(
    variable_specs: &BTreeMap<String, VariableSamplerSpec>,
    n_steps: usize,
    n_simulations: usize,
    seed: u64,
) -> Result<BTreeMap<String, Vec<Vec<f64>>>, String> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mut sampled = BTreeMap::new();

    for name in variable_specs.keys() {
        sampled.insert(name.clone(), vec![vec![0.0; n_steps]; n_simulations]);
    }

    for sim_index in 0..n_simulations {
        for step_index in 0..n_steps {
            for (name, spec) in variable_specs {
                let value = sample_distribution(spec, &mut rng)?;
                if let Some(per_sim) = sampled.get_mut(name) {
                    per_sim[sim_index][step_index] = value;
                }
            }
        }
    }

    Ok(sampled)
}

pub fn sample_binomial(trials: u64, probability: f64, seed: u64) -> Result<u64, String> {
    if !(0.0..=1.0).contains(&probability) {
        return Err(format!(
            "binomial.probability must be in [0, 1]: {probability}"
        ));
    }

    let distribution =
        Binomial::new(trials, probability).map_err(|err| format!("invalid binomial: {err}"))?;
    let mut rng = StdRng::seed_from_u64(seed);
    Ok(distribution.sample(&mut rng))
}

fn sample_distribution(spec: &VariableSamplerSpec, rng: &mut StdRng) -> Result<f64, String> {
    let params = &spec.params;
    let distribution = spec.distribution.as_str();
    let sampled = match distribution {
        "fixed" => param(params, "value", 0.0),
        "uniform" => {
            let low = param(params, "low", 0.0);
            let high = param(params, "high", 1.0);
            if low > high {
                return Err(format!(
                    "uniform.low must be <= uniform.high: {low} > {high}"
                ));
            }
            if (high - low).abs() < f64::EPSILON {
                low
            } else {
                rng.gen_range(low..=high)
            }
        }
        "triangular" => {
            let low = param(params, "low", 0.0);
            let high = param(params, "high", 1.0);
            let mode = param(params, "mode", (low + high) / 2.0);
            if low > high {
                return Err(format!(
                    "triangular.low must be <= triangular.high: {low} > {high}"
                ));
            }
            if mode < low || mode > high {
                return Err(format!(
                    "triangular.mode must be between low and high: {mode} not in [{low}, {high}]"
                ));
            }
            triangular_sample(low, mode, high, rng)
        }
        "normal" => {
            let mean = param(params, "mean", 0.0);
            let std = param(params, "std", 1.0);
            if std <= 0.0 {
                return Err(format!("normal.std must be > 0: {std}"));
            }
            let sampled = mean + std * standard_normal(rng);
            clamp(
                sampled,
                param(params, "min", NEGATIVE_INF_CLAMP),
                param(params, "max", POSITIVE_INF_CLAMP),
            )
        }
        "lognormal" => {
            let median = param(params, "median", 1.0);
            let spread = param(params, "spread", 0.5);
            if median <= 0.0 {
                return Err(format!("lognormal.median must be > 0: {median}"));
            }
            if spread <= 0.0 {
                return Err(format!("lognormal.spread must be > 0: {spread}"));
            }
            let sampled = (median.ln() + spread * standard_normal(rng)).exp();
            clamp(
                sampled,
                param(params, "min", 0.0),
                param(params, "max", POSITIVE_INF_CLAMP),
            )
        }
        "bernoulli" => {
            let probability = param(params, "p", 0.5);
            if !(0.0..=1.0).contains(&probability) {
                return Err(format!("bernoulli.p must be in [0, 1]: {probability}"));
            }
            if rng.gen::<f64>() < probability {
                1.0
            } else {
                0.0
            }
        }
        "poisson" => {
            let lambda = param(params, "lambda", 1.0);
            if lambda < 0.0 {
                return Err(format!("poisson.lambda must be >= 0: {lambda}"));
            }
            poisson_sample(lambda, rng)
        }
        "student_t" => {
            let df = param(params, "df", 5.0).round() as usize;
            if df == 0 {
                return Err("student_t.df must be >= 1".to_string());
            }
            let mean = param(params, "mean", 0.0);
            let scale = param(params, "scale", 1.0);
            if scale <= 0.0 {
                return Err(format!("student_t.scale must be > 0: {scale}"));
            }
            let z = standard_normal(rng);
            let v: f64 = (0..df)
                .map(|_| {
                    let sample = standard_normal(rng);
                    sample * sample
                })
                .sum();
            let t_value = if v > 0.0 {
                z / (v / df as f64).sqrt()
            } else {
                z
            };
            clamp(
                mean + scale * t_value,
                param(params, "min", NEGATIVE_INF_CLAMP),
                param(params, "max", POSITIVE_INF_CLAMP),
            )
        }
        other => return Err(format!("unsupported distribution: {other}")),
    };

    Ok(sampled)
}

fn triangular_sample(low: f64, mode: f64, high: f64, rng: &mut StdRng) -> f64 {
    if (high - low).abs() < f64::EPSILON {
        return low;
    }

    let u = rng.gen::<f64>();
    let split = (mode - low) / (high - low);
    if u < split {
        low + (u * (high - low) * (mode - low)).sqrt()
    } else {
        high - ((1.0 - u) * (high - low) * (high - mode)).sqrt()
    }
}

fn poisson_sample(lambda: f64, rng: &mut StdRng) -> f64 {
    if lambda == 0.0 {
        return 0.0;
    }

    let threshold = (-lambda).exp();
    let mut k: i64 = 0;
    let mut product = 1.0;
    while product > threshold {
        k += 1;
        product *= rng.gen::<f64>();
    }
    (k - 1) as f64
}

fn standard_normal(rng: &mut StdRng) -> f64 {
    let u1 = loop {
        let candidate = rng.gen::<f64>();
        if candidate > 0.0 {
            break candidate;
        }
    };
    let u2 = rng.gen::<f64>();
    (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
}

fn param(params: &BTreeMap<String, f64>, key: &str, default: f64) -> f64 {
    params.get(key).copied().unwrap_or(default)
}

fn clamp(value: f64, low: f64, high: f64) -> f64 {
    value.max(low).min(high)
}

#[cfg(test)]
mod tests {
    use super::{sample_variable_grid, VariableSamplerSpec};
    use std::collections::BTreeMap;

    #[test]
    fn sample_variable_grid_is_deterministic_for_the_same_seed() {
        let mut plan = BTreeMap::new();
        plan.insert(
            "rate".to_string(),
            VariableSamplerSpec {
                distribution: "triangular".to_string(),
                params: BTreeMap::from([
                    ("low".to_string(), 0.1),
                    ("mode".to_string(), 0.3),
                    ("high".to_string(), 0.5),
                ]),
            },
        );

        let first = sample_variable_grid(&plan, 3, 4, 42).expect("sample grid");
        let second = sample_variable_grid(&plan, 3, 4, 42).expect("sample grid");

        assert_eq!(first, second);
    }

    #[test]
    fn sample_variable_grid_supports_fixed_and_bernoulli_shapes() {
        let mut plan = BTreeMap::new();
        plan.insert(
            "fixed_cost".to_string(),
            VariableSamplerSpec {
                distribution: "fixed".to_string(),
                params: BTreeMap::from([("value".to_string(), 12.5)]),
            },
        );
        plan.insert(
            "flag".to_string(),
            VariableSamplerSpec {
                distribution: "bernoulli".to_string(),
                params: BTreeMap::from([("p".to_string(), 0.5)]),
            },
        );

        let sampled = sample_variable_grid(&plan, 2, 5, 7).expect("sample grid");
        assert_eq!(sampled["fixed_cost"].len(), 5);
        assert_eq!(sampled["fixed_cost"][0], vec![12.5, 12.5]);
        assert!(sampled["flag"]
            .iter()
            .flat_map(|draws| draws.iter())
            .all(
                |value| (*value - 0.0).abs() < f64::EPSILON || (*value - 1.0).abs() < f64::EPSILON
            ));
    }

    #[test]
    fn sample_variable_grid_rejects_invalid_distribution() {
        let mut plan = BTreeMap::new();
        plan.insert(
            "bad".to_string(),
            VariableSamplerSpec {
                distribution: "mystery".to_string(),
                params: BTreeMap::new(),
            },
        );

        let err = sample_variable_grid(&plan, 2, 3, 9).expect_err("unsupported distribution");
        assert!(err.contains("unsupported distribution"));
    }

    #[test]
    fn sample_binomial_is_deterministic_for_the_same_seed() {
        let first = super::sample_binomial(20, 0.35, 42).expect("binomial sample");
        let second = super::sample_binomial(20, 0.35, 42).expect("binomial sample");
        assert_eq!(first, second);
    }

    #[test]
    fn sample_binomial_rejects_bad_probability() {
        let err = super::sample_binomial(10, 1.2, 5).expect_err("invalid probability");
        assert!(err.contains("probability"));
    }
}
