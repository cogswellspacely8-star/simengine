use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MetricStats {
    pub mean: f64,
    pub median: f64,
    pub std: f64,
    pub p10: f64,
    pub p25: f64,
    pub p75: f64,
    pub p90: f64,
    pub format: String,
}

pub(crate) fn round_to(value: f64, decimals: i32) -> f64 {
    let factor = 10_f64.powi(decimals);
    (value * factor).round() / factor
}

pub fn percentile_sorted(data: &[f64], pct: f64) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    let k = (data.len() - 1) as f64 * (pct / 100.0);
    let f = k.floor() as usize;
    let c = k.ceil() as usize;
    if f == c {
        return data[k as usize];
    }
    data[f] * (c as f64 - k) + data[c] * (k - f as f64)
}

fn sample_mean(data: &[f64]) -> f64 {
    data.iter().sum::<f64>() / data.len() as f64
}

fn sample_median(sorted: &[f64]) -> f64 {
    let mid = sorted.len() / 2;
    if sorted.len().is_multiple_of(2) {
        (sorted[mid - 1] + sorted[mid]) / 2.0
    } else {
        sorted[mid]
    }
}

fn sample_std(data: &[f64], mean: f64) -> f64 {
    if data.len() <= 1 {
        return 0.0;
    }
    let variance = data
        .iter()
        .map(|value| {
            let delta = value - mean;
            delta * delta
        })
        .sum::<f64>()
        / (data.len() - 1) as f64;
    variance.sqrt()
}

pub fn reduce_metrics(
    raw_metrics: &BTreeMap<String, Vec<f64>>,
    metric_formats: &BTreeMap<String, String>,
) -> BTreeMap<String, MetricStats> {
    let mut reduced = BTreeMap::new();
    for (metric_name, values) in raw_metrics {
        if values.is_empty() {
            continue;
        }
        let mut sorted_values = values.clone();
        sorted_values.sort_by(f64::total_cmp);
        let mean = sample_mean(values);
        let median = sample_median(&sorted_values);
        let std = sample_std(values, mean);
        let format = metric_formats
            .get(metric_name)
            .cloned()
            .unwrap_or_else(|| "number".to_string());
        reduced.insert(
            metric_name.clone(),
            MetricStats {
                mean: round_to(mean, 2),
                median: round_to(median, 2),
                std: round_to(std, 2),
                p10: round_to(percentile_sorted(&sorted_values, 10.0), 2),
                p25: round_to(percentile_sorted(&sorted_values, 25.0), 2),
                p75: round_to(percentile_sorted(&sorted_values, 75.0), 2),
                p90: round_to(percentile_sorted(&sorted_values, 90.0), 2),
                format,
            },
        );
    }
    reduced
}

#[cfg(test)]
mod tests {
    use super::{percentile_sorted, reduce_metrics};
    use std::collections::BTreeMap;

    #[test]
    fn percentile_matches_linear_interpolation() {
        let values = vec![0.0, 10.0, 20.0, 30.0];
        assert_eq!(percentile_sorted(&values, 0.0), 0.0);
        assert_eq!(percentile_sorted(&values, 50.0), 15.0);
        assert_eq!(percentile_sorted(&values, 100.0), 30.0);
    }

    #[test]
    fn reduce_metrics_emits_expected_fields() {
        let mut raw = BTreeMap::new();
        raw.insert("profit".to_string(), vec![10.0, 20.0, 30.0, 40.0]);
        let mut formats = BTreeMap::new();
        formats.insert("profit".to_string(), "dollar".to_string());

        let reduced = reduce_metrics(&raw, &formats);
        let stats = reduced.get("profit").expect("metric stats");

        assert_eq!(stats.format, "dollar");
        assert_eq!(stats.mean, 25.0);
        assert_eq!(stats.median, 25.0);
        assert_eq!(stats.p10, 13.0);
        assert_eq!(stats.p90, 37.0);
    }
}
