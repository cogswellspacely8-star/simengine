use crate::stats::{percentile_sorted, round_to};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TrajectoryBand {
    pub p10: Vec<f64>,
    pub p50: Vec<f64>,
    pub p90: Vec<f64>,
}

pub fn compute_trajectories(
    trajectory_samples: &BTreeMap<String, Vec<Vec<f64>>>,
) -> BTreeMap<String, TrajectoryBand> {
    let mut reduced = BTreeMap::new();
    for (accumulator, steps) in trajectory_samples {
        let mut p10 = Vec::with_capacity(steps.len());
        let mut p50 = Vec::with_capacity(steps.len());
        let mut p90 = Vec::with_capacity(steps.len());

        for values in steps {
            if values.is_empty() {
                p10.push(0.0);
                p50.push(0.0);
                p90.push(0.0);
                continue;
            }
            let mut sorted_values = values.clone();
            sorted_values.sort_by(f64::total_cmp);
            p10.push(round_to(percentile_sorted(&sorted_values, 10.0), 2));
            p50.push(round_to(percentile_sorted(&sorted_values, 50.0), 2));
            p90.push(round_to(percentile_sorted(&sorted_values, 90.0), 2));
        }

        reduced.insert(accumulator.clone(), TrajectoryBand { p10, p50, p90 });
    }
    reduced
}

#[cfg(test)]
mod tests {
    use super::compute_trajectories;
    use std::collections::BTreeMap;

    #[test]
    fn compute_trajectories_reduces_each_step() {
        let mut samples = BTreeMap::new();
        samples.insert(
            "cash".to_string(),
            vec![vec![10.0, 20.0, 30.0], vec![20.0, 30.0, 40.0]],
        );

        let reduced = compute_trajectories(&samples);
        let band = reduced.get("cash").expect("trajectory");

        assert_eq!(band.p50, vec![20.0, 30.0]);
        assert_eq!(band.p10, vec![12.0, 22.0]);
        assert_eq!(band.p90, vec![28.0, 38.0]);
    }
}
