use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use pythonize::{depythonize, pythonize};
use simengine_core::{
    build_histograms, compute_trajectories, evaluate_safety, reduce_metrics, sample_binomial,
    sample_variable_grid, SafetyConfig, VariableSamplerSpec,
};
use std::collections::BTreeMap;

fn as_value_error(err: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(err.to_string())
}

fn py_object<T>(py: Python<'_>, value: &T) -> PyResult<Py<PyAny>>
where
    T: serde::Serialize,
{
    pythonize(py, value)
        .map(|bound| bound.unbind())
        .map_err(as_value_error)
}

#[pyfunction]
fn backend_info(py: Python<'_>) -> PyResult<Py<PyAny>> {
    let mut info = BTreeMap::new();
    info.insert("module".to_string(), "simengine_native".to_string());
    info.insert("version".to_string(), env!("CARGO_PKG_VERSION").to_string());
    info.insert("core".to_string(), "simengine-core".to_string());
    info.insert(
        "features".to_string(),
        "reducers,safety,histograms,trajectories,batch_sampling,expr_sampling".to_string(),
    );
    py_object(py, &info)
}

#[pyfunction]
fn reduce_metrics_py(
    py: Python<'_>,
    raw_metrics: &Bound<'_, PyAny>,
    metric_formats: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let raw_metrics: BTreeMap<String, Vec<f64>> =
        depythonize(raw_metrics).map_err(as_value_error)?;
    let metric_formats: BTreeMap<String, String> =
        depythonize(metric_formats).map_err(as_value_error)?;
    py_object(py, &reduce_metrics(&raw_metrics, &metric_formats))
}

#[pyfunction]
fn compute_trajectories_py(
    py: Python<'_>,
    trajectory_samples: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let trajectory_samples: BTreeMap<String, Vec<Vec<f64>>> =
        depythonize(trajectory_samples).map_err(as_value_error)?;
    py_object(py, &compute_trajectories(&trajectory_samples))
}

#[pyfunction]
fn evaluate_safety_py(
    py: Python<'_>,
    raw_metrics: &Bound<'_, PyAny>,
    safety_config: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let raw_metrics: BTreeMap<String, Vec<f64>> =
        depythonize(raw_metrics).map_err(as_value_error)?;
    let safety_config: SafetyConfig = depythonize(safety_config).map_err(as_value_error)?;
    py_object(py, &evaluate_safety(&raw_metrics, &safety_config))
}

#[pyfunction]
fn build_histograms_py(
    py: Python<'_>,
    raw_metrics: &Bound<'_, PyAny>,
    n_bins: usize,
) -> PyResult<Py<PyAny>> {
    let raw_metrics: BTreeMap<String, Vec<f64>> =
        depythonize(raw_metrics).map_err(as_value_error)?;
    py_object(py, &build_histograms(&raw_metrics, n_bins))
}

#[pyfunction]
fn sample_variable_grid_py(
    py: Python<'_>,
    variable_specs: &Bound<'_, PyAny>,
    n_steps: usize,
    n_simulations: usize,
    seed: u64,
) -> PyResult<Py<PyAny>> {
    let variable_specs: BTreeMap<String, VariableSamplerSpec> =
        depythonize(variable_specs).map_err(as_value_error)?;
    let sampled = sample_variable_grid(&variable_specs, n_steps, n_simulations, seed)
        .map_err(as_value_error)?;
    py_object(py, &sampled)
}

#[pyfunction]
fn sample_binomial_py(trials: u64, probability: f64, seed: u64) -> PyResult<u64> {
    sample_binomial(trials, probability, seed).map_err(as_value_error)
}

#[pymodule]
fn simengine_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(backend_info, m)?)?;
    m.add_function(wrap_pyfunction!(reduce_metrics_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_trajectories_py, m)?)?;
    m.add_function(wrap_pyfunction!(evaluate_safety_py, m)?)?;
    m.add_function(wrap_pyfunction!(build_histograms_py, m)?)?;
    m.add("reduce_metrics", m.getattr("reduce_metrics_py")?)?;
    m.add(
        "compute_trajectories",
        m.getattr("compute_trajectories_py")?,
    )?;
    m.add("evaluate_safety", m.getattr("evaluate_safety_py")?)?;
    m.add("build_histograms", m.getattr("build_histograms_py")?)?;
    m.add_function(wrap_pyfunction!(sample_variable_grid_py, m)?)?;
    m.add(
        "sample_variable_grid",
        m.getattr("sample_variable_grid_py")?,
    )?;
    m.add_function(wrap_pyfunction!(sample_binomial_py, m)?)?;
    m.add("sample_binomial", m.getattr("sample_binomial_py")?)?;
    Ok(())
}
