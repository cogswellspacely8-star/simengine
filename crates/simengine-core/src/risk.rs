use crate::stats::round_to;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SafetyConfig {
    #[serde(default)]
    pub chance_constraints: Vec<ChanceConstraint>,
    #[serde(default)]
    pub cvar_constraints: Vec<CvarConstraint>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChanceConstraint {
    pub metric: String,
    pub condition: String,
    pub threshold: f64,
    pub max_prob: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CvarConstraint {
    pub metric: String,
    pub alpha: f64,
    pub min_cvar: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChanceEvaluation {
    pub metric: String,
    pub condition: String,
    pub threshold: f64,
    pub max_prob: f64,
    pub actual_prob: f64,
    pub passed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CvarEvaluation {
    pub metric: String,
    pub alpha: f64,
    pub min_cvar: f64,
    pub actual_cvar: f64,
    pub passed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SafetyResult {
    pub chance: Vec<ChanceEvaluation>,
    pub cvar: Vec<CvarEvaluation>,
    pub all_passed: bool,
}

pub fn compute_cvar(values: &[f64], alpha: f64) -> f64 {
    let mut sorted_values = values.to_vec();
    sorted_values.sort_by(f64::total_cmp);
    let n_tail = usize::max(1, (sorted_values.len() as f64 * alpha).floor() as usize);
    let tail = &sorted_values[..n_tail];
    tail.iter().sum::<f64>() / tail.len() as f64
}

pub fn evaluate_safety(
    raw_metrics: &BTreeMap<String, Vec<f64>>,
    safety_config: &SafetyConfig,
) -> SafetyResult {
    let mut result = SafetyResult {
        chance: Vec::new(),
        cvar: Vec::new(),
        all_passed: true,
    };

    for constraint in &safety_config.chance_constraints {
        let Some(values) = raw_metrics.get(&constraint.metric) else {
            continue;
        };
        if values.is_empty() {
            continue;
        }

        let violations = match constraint.condition.as_str() {
            "below" => values
                .iter()
                .filter(|value| **value < constraint.threshold)
                .count(),
            _ => values
                .iter()
                .filter(|value| **value > constraint.threshold)
                .count(),
        };
        let actual_prob = violations as f64 / values.len() as f64;
        let passed = actual_prob <= constraint.max_prob;
        if !passed {
            result.all_passed = false;
        }

        result.chance.push(ChanceEvaluation {
            metric: constraint.metric.clone(),
            condition: constraint.condition.clone(),
            threshold: constraint.threshold,
            max_prob: constraint.max_prob,
            actual_prob: round_to(actual_prob, 4),
            passed,
        });
    }

    for constraint in &safety_config.cvar_constraints {
        let Some(values) = raw_metrics.get(&constraint.metric) else {
            continue;
        };
        if values.is_empty() {
            continue;
        }

        let actual_cvar = compute_cvar(values, constraint.alpha);
        let passed = actual_cvar >= constraint.min_cvar;
        if !passed {
            result.all_passed = false;
        }

        result.cvar.push(CvarEvaluation {
            metric: constraint.metric.clone(),
            alpha: constraint.alpha,
            min_cvar: constraint.min_cvar,
            actual_cvar: round_to(actual_cvar, 2),
            passed,
        });
    }

    result
}

#[cfg(test)]
mod tests {
    use super::{evaluate_safety, SafetyConfig};
    use std::collections::BTreeMap;

    #[test]
    fn evaluate_safety_tracks_pass_fail() {
        let mut raw = BTreeMap::new();
        raw.insert("cash".to_string(), vec![-10.0, 10.0, 20.0, 30.0]);
        let config = SafetyConfig {
            chance_constraints: vec![super::ChanceConstraint {
                metric: "cash".to_string(),
                condition: "below".to_string(),
                threshold: 0.0,
                max_prob: 0.5,
            }],
            cvar_constraints: vec![super::CvarConstraint {
                metric: "cash".to_string(),
                alpha: 0.25,
                min_cvar: -15.0,
            }],
        };

        let result = evaluate_safety(&raw, &config);
        assert!(result.all_passed);
        assert_eq!(result.chance[0].actual_prob, 0.25);
        assert_eq!(result.cvar[0].actual_cvar, -10.0);
    }
}
