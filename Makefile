PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: venv native-install native-check native-test native-bench test rust-test

venv:
	$(PYTHON) -m venv $(VENV)
	. $(VENV)/bin/activate && python -m pip install --upgrade pip setuptools wheel maturin

native-install: venv
	. $(VENV)/bin/activate && cd crates/simengine-py && maturin develop --release

native-check:
	. $(VENV)/bin/activate && PYTHONPATH=$(PWD)/v3 python -c "import native; print(native.backend_info())"

native-test:
	. $(VENV)/bin/activate && PYTHONPATH=$(PWD)/v3 python -m unittest discover -s $(PWD)/v3/tests -p 'test_*.py'

native-bench:
	. $(VENV)/bin/activate && PYTHONPATH=$(PWD)/v3 python scripts/bench_native.py

test:
	$(PYTHON) -m unittest discover -s $(PWD)/v3/tests -p 'test_*.py'

rust-test:
	cargo test -p simengine-core --lib
