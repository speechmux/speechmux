.PHONY: install test lint typecheck run-dummy clean

VENV   ?= ../.venv
PYTHON ?= $(VENV)/bin/python3
UV     ?= uv

install:
	$(UV) pip install --python $(PYTHON) -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check src/

typecheck:
	$(PYTHON) -m mypy src/

run-dummy:
	$(PYTHON) -m speechmux_plugin_vad.main \
		--config config/vad-dummy.yaml

clean:
	rm -rf dist/ build/ src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
