use crate::stats::round_to;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Histogram {
    pub bins: Vec<f64>,
    pub counts: Vec<usize>,
    pub bin_width: Option<f64>,
    pub lo: f64,
    pub hi: f64,
}

pub fn build_histograms(
    raw_metrics: &BTreeMap<String, Vec<f64>>,
    n_bins: usize,
) -> BTreeMap<String, Histogram> {
    let bins_count = usize::max(1, n_bins);
    let mut histograms = BTreeMap::new();

    for (metric_name, values) in raw_metrics {
        if values.is_empty() {
            continue;
        }

        let mut sorted_values = values.clone();
        sorted_values.sort_by(f64::total_cmp);
        let lo = sorted_values[0];
        let hi = sorted_values[sorted_values.len() - 1];

        if lo == hi {
            histograms.insert(
                metric_name.clone(),
                Histogram {
                    bins: vec![lo],
                    counts: vec![sorted_values.len()],
                    bin_width: None,
                    lo,
                    hi,
                },
            );
            continue;
        }

        let bin_width = (hi - lo) / bins_count as f64;
        let mut bins = Vec::with_capacity(bins_count);
        let mut counts = vec![0usize; bins_count];

        for index in 0..bins_count {
            bins.push(round_to(lo + index as f64 * bin_width, 4));
        }
        for value in sorted_values {
            let idx = (((value - lo) / bin_width) as usize).min(bins_count - 1);
            counts[idx] += 1;
        }

        histograms.insert(
            metric_name.clone(),
            Histogram {
                bins,
                counts,
                bin_width: Some(round_to(bin_width, 4)),
                lo: round_to(lo, 2),
                hi: round_to(hi, 2),
            },
        );
    }

    histograms
}

#[cfg(test)]
mod tests {
    use super::build_histograms;
    use std::collections::BTreeMap;

    #[test]
    fn build_histograms_groups_values() {
        let mut raw = BTreeMap::new();
        raw.insert("metric".to_string(), vec![0.0, 1.0, 2.0, 3.0]);

        let histograms = build_histograms(&raw, 2);
        let histogram = histograms.get("metric").expect("histogram");

        assert_eq!(histogram.counts, vec![2, 2]);
        assert_eq!(histogram.bins.len(), 2);
    }
}
