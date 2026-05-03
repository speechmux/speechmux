VENV      ?= .venv
PYTHON    ?= $(abspath $(VENV)/bin/python3)
UV        ?= uv
GO        ?= go
CORE_BIN  := core/bin/speechmux-core
WORKSPACE ?= core/config/workspace.yaml
MODELS_DIR ?= ./models
# Space-separated list of Docker Compose profiles to activate for docker-* targets.
# Override: make docker-up DOCKER_PROFILE=sherpa  (sherpa only)
#           make docker-up DOCKER_PROFILE="sherpa faster-whisper"  (both; default)
DOCKER_PROFILE ?= sherpa faster-whisper
# Expands to: --profile sherpa --profile faster-whisper (evaluated lazily so overrides work).
_DOCKER_PROFILE_FLAGS = $(foreach p,$(DOCKER_PROFILE),--profile $(p))

.PHONY: clone-base clone-stt clone-vad clone-web clone-cli \
        setup proto build \
        up down status logs \
        test \
        docker-build docker-up docker-down docker-logs docker-logs-stt docker-logs-vad \
        download-models clean

# ── Clone ─────────────────────────────────────────────────────────────────────

define _clone
	@if [ ! -d $(1) ]; then \
		git clone git@github.com:speechmux/$(1).git; \
	else \
		echo "$(1): already exists, skipping"; \
	fi
endef

clone-base:
	$(call _clone,proto)
	$(call _clone,core)
	$(call _clone,plugin-vad)
	$(call _clone,plugin-stt)

# Usage: make clone-stt IMPL=faster-whisper
clone-stt:
ifndef IMPL
	$(error Usage: make clone-stt IMPL=<engine>  e.g. faster-whisper)
endif
	$(call _clone,plugin-stt-$(IMPL))

# Usage: make clone-vad IMPL=silero
clone-vad:
ifndef IMPL
	$(error Usage: make clone-vad IMPL=<engine>  e.g. silero)
endif
	$(call _clone,plugin-vad-$(IMPL))

clone-web:
	$(call _clone,client-web)

clone-cli:
	$(call _clone,client-cli)

# ── Setup / Build ─────────────────────────────────────────────────────────────

setup:
	@if [ ! -d $(VENV) ]; then $(UV) venv --python 3.13 $(VENV); fi
	cd core && $(GO) mod download
	@if [ ! -f proto/gen/python/pyproject.toml ]; then \
		printf '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[project]\nname = "speechmux-proto"\nversion = "0.1.0"\nrequires-python = ">=3.10"\ndependencies = ["grpcio>=1.60.0", "protobuf>=4.25.0"]\n\n[tool.hatch.build.targets.wheel]\npackages = ["stt_proto"]\n' \
		> proto/gen/python/pyproject.toml; \
	fi
	$(UV) pip install --python $(PYTHON) -e "proto/gen/python"
	@if [ -d plugin-vad ]; then $(UV) pip install --python $(PYTHON) -e "plugin-vad[dev]"; fi
	@if [ -d plugin-stt ]; then $(UV) pip install --python $(PYTHON) -e "plugin-stt[dev]"; fi
	@for d in plugin-vad-* plugin-stt-*; do \
		if [ -d "$$d" ]; then $(UV) pip install --python $(PYTHON) -e "$$d[dev]"; fi; \
	done
	@if [ -d client-cli ]; then $(UV) pip install --python $(PYTHON) -e "client-cli[dev]"; fi
	@if [ -d client-web/api ]; then $(UV) pip install --python $(PYTHON) -e "client-web/api[dev]"; fi

proto:
	cd proto && make generate
	$(UV) pip install --python $(PYTHON) -e "proto/gen/python"

build:
	cd core && $(GO) build -o bin/speechmux-core ./cmd/speechmux-core

# ── Local dev (native macOS) ──────────────────────────────────────────────────
#
# All processes (VAD plugin, STT plugin, Core) are managed by speechmux-core ctl.
# ctl starts them in declaration order (workspace.yaml) and restarts on failure.
# For external access via Tailscale: scripts/remote-access.sh

up: build
	@if lsof -ti :50051 >/dev/null 2>&1 || lsof -ti :8090 >/dev/null 2>&1 || lsof -ti :8091 >/dev/null 2>&1; then \
		echo "ERROR: core ports already in use. Run 'make down' first."; exit 1; \
	fi
	$(CORE_BIN) ctl start --workspace $(WORKSPACE) &

down:
	$(CORE_BIN) ctl stop --workspace $(WORKSPACE) || true
	@lsof -nP -iTCP:50051 -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null || true
	@lsof -nP -iTCP:8090  -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null || true
	@lsof -nP -iTCP:8091  -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null || true

status:
	$(CORE_BIN) ctl status --workspace $(WORKSPACE)

logs:
	tail -f /tmp/speechmux/*.log

# ── Test ──────────────────────────────────────────────────────────────────────

test:
	@if [ -d proto ]; then cd proto && make generate; fi
	@if [ -d core ]; then cd core && $(GO) test ./...; fi
	@if [ -d plugin-vad ]; then (cd plugin-vad && $(PYTHON) -m pytest tests/) || exit 1; fi
	@if [ -d plugin-stt ]; then (cd plugin-stt && $(PYTHON) -m pytest tests/) || exit 1; fi
	@for d in plugin-vad-* plugin-stt-*; do \
		if [ -d "$$d" ]; then (cd "$$d" && $(PYTHON) -m pytest tests/) || exit 1; fi; \
	done
	@if [ -d client-cli ]; then (cd client-cli && $(PYTHON) -m pytest tests/) || exit 1; fi

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker compose $(_DOCKER_PROFILE_FLAGS) build

docker-up:
	docker compose $(_DOCKER_PROFILE_FLAGS) up -d

docker-down:
	docker compose $(_DOCKER_PROFILE_FLAGS) down

# Tail core + all STT/VAD services; use --tail to avoid a wall of history.
docker-logs:
	docker compose $(_DOCKER_PROFILE_FLAGS) logs -f --tail=200 core vad-silero stt-sherpa stt-faster-whisper

# STT plugin logs only.
docker-logs-stt:
	docker compose $(_DOCKER_PROFILE_FLAGS) logs -f --tail=200 stt-sherpa stt-faster-whisper

# VAD plugin logs only.
docker-logs-vad:
	docker compose $(_DOCKER_PROFILE_FLAGS) logs -f --tail=200 vad-silero

download-models:
	@mkdir -p $(MODELS_DIR)/ko $(MODELS_DIR)/en
	@echo "Place sherpa-onnx streaming Zipformer model files at:"
	@echo "  $(MODELS_DIR)/ko/  — encoder, decoder, joiner .int8.onnx + tokens.txt"
	@echo "  $(MODELS_DIR)/en/  — same layout"
	@echo "See: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/"

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	rm -rf core/bin
