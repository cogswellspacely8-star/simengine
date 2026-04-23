#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${repo_root}/.venv"

python3 -m venv "${venv_dir}"
source "${venv_dir}/bin/activate"
python -m pip install --upgrade pip setuptools wheel maturin

cd "${repo_root}/crates/simengine-py"
maturin develop --release

cd "${repo_root}"
PYTHONPATH="${repo_root}/v3" python - <<'PY'
import native
print(native.backend_info())
PY
