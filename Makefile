SOCKET_DIR  := /tmp/speechmux
PIDS_DIR    := /tmp/speechmux/pids
LOGS_DIR    := /tmp/speechmux/logs
VENV        ?= .venv
PYTHON      ?= $(abspath $(VENV)/bin/python3)
UV          ?= uv
GO          ?= go
CADDY       ?= caddy
TAILSCALE   ?= /Applications/Tailscale.app/Contents/MacOS/Tailscale
CORE_GRPC_PORT := 50051
CORE_HTTP_PORT := 8090
CORE_WS_PORT   := 8091
WEB_API_PORT   := 8000
WEB_NEXT_PORT  := 3020
CADDY_PORT     := 8443
CADDY_NOTLS_PORT := 8080

.PHONY: setup proto build run run-all run-dummy stop stop-all status logs test loadtest clean run-web stop-web run-web-caddy stop-caddy run-all-caddy caddy-trust run-all-tailscale stop-tailscale _ensure-dirs _wait-socks _wait-socks-dummy run-core-dummy run-stt run-stt-sherpa run-stt-mlx clone-base clone-stt clone-vad clone-web clone-cli

# ── Clone ──────────────────────────────────────────────────────────────────
# Clone a repo only if the directory does not already exist.
define _clone
	@if [ ! -d $(1) ]; then \
		git clone git@github.com:speechmux/$(1).git; \
	else \
		echo "$(1): already exists, skipping"; \
	fi
endef

# Base layer — always needed to run SpeechMux.
clone-base:
	$(call _clone,proto)
	$(call _clone,core)
	$(call _clone,plugin-vad)
	$(call _clone,plugin-stt)

# STT engine implementation — pick one (or run multiple times for multiple engines).
# Usage: make clone-stt IMPL=mlx-whisper
#        make clone-stt IMPL=faster-whisper
clone-stt:
ifndef IMPL
	$(error Usage: make clone-stt IMPL=<engine>  e.g. mlx-whisper, faster-whisper, torch-whisper)
endif
	$(call _clone,plugin-stt-$(IMPL))

# VAD engine implementation — pick one.
# Usage: make clone-vad IMPL=silero
clone-vad:
ifndef IMPL
	$(error Usage: make clone-vad IMPL=<engine>  e.g. silero)
endif
	$(call _clone,plugin-vad-$(IMPL))

# Web and CLI clients.
clone-web:
	$(call _clone,client-web)

clone-cli:
	$(call _clone,client-cli)

# ── Initial setup ──

setup:
	@if [ ! -d $(VENV) ]; then $(UV) venv --python 3.13 $(VENV); fi
	cd core && $(GO) mod download
	@# Generate minimal pyproject.toml for proto/gen/python if absent (not committed to proto repo)
	@if [ ! -f proto/gen/python/pyproject.toml ]; then \
		printf '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n[project]\nname = "speechmux-proto"\nversion = "0.1.0"\nrequires-python = ">=3.13"\ndependencies = ["grpcio>=1.60.0", "protobuf>=4.25.0"]\n\n[tool.hatch.build.targets.wheel]\npackages = ["stt_proto"]\n' \
		> proto/gen/python/pyproject.toml; \
	fi
	$(UV) pip install --python $(PYTHON) -e "proto/gen/python"
	@# Base plugin packages (installed only if cloned)
	@if [ -d plugin-vad ]; then \
		echo "Installing plugin-vad..."; \
		$(UV) pip install --python $(PYTHON) -e "plugin-vad[dev]"; \
	fi
	@if [ -d plugin-stt ]; then \
		echo "Installing plugin-stt..."; \
		$(UV) pip install --python $(PYTHON) -e "plugin-stt[dev]"; \
	fi
	@# Engine implementations — any cloned plugin-vad-* / plugin-stt-* package
	@for d in plugin-vad-* plugin-stt-*; do \
		if [ -d "$$d" ]; then \
			echo "Installing $$d..."; \
			$(UV) pip install --python $(PYTHON) -e "$$d[dev]"; \
		fi; \
	done
	@# Clients (installed only if cloned)
	@if [ -d client-cli ]; then \
		echo "Installing client-cli..."; \
		$(UV) pip install --python $(PYTHON) -e "client-cli[dev]"; \
	fi
	@if [ -d client-web/api ]; then \
		echo "Installing client-web/api..."; \
		$(UV) pip install --python $(PYTHON) -e "client-web/api[dev]"; \
	fi

proto:
	cd proto && make generate
	$(UV) pip install --python $(PYTHON) -e "proto/gen/python"

# ── Build ──

build:
	cd core && $(GO) build -o bin/speechmux-core ./cmd/speechmux-core

# ── Internal helpers ──

_ensure-dirs:
	@mkdir -p $(SOCKET_DIR) $(PIDS_DIR) $(LOGS_DIR)

_wait-socks:
	@echo "Waiting for plugin sockets (up to 60s)..."; \
	sherpa_skip=0; \
	for i in $$(seq 1 60); do \
		if [ $$sherpa_skip -eq 0 ] && [ -f $(PIDS_DIR)/stt-sherpa.pid ]; then \
			if ! kill -0 $$(cat $(PIDS_DIR)/stt-sherpa.pid) 2>/dev/null; then \
				sherpa_skip=1; \
				echo "  WARNING: stt-sherpa crashed — skipping (last lines of $(LOGS_DIR)/stt-sherpa.log):"; \
				tail -5 $(LOGS_DIR)/stt-sherpa.log 2>/dev/null | sed 's/^/    /'; \
				rm -f $(PIDS_DIR)/stt-sherpa.pid; \
			fi; \
		fi; \
		vad_ok=0; mlx_ok=0; sherpa_ok=$$sherpa_skip; \
		[ -S $(SOCKET_DIR)/vad.sock ]        && vad_ok=1; \
		[ -S $(SOCKET_DIR)/stt-mlx.sock ]    && mlx_ok=1; \
		[ -S $(SOCKET_DIR)/stt-sherpa.sock ] && sherpa_ok=1; \
		if [ $$vad_ok -eq 1 ] && [ $$mlx_ok -eq 1 ] && [ $$sherpa_ok -eq 1 ]; then \
			echo "  vad.sock: ready"; \
			echo "  stt-mlx.sock: ready"; \
			[ -S $(SOCKET_DIR)/stt-sherpa.sock ] && echo "  stt-sherpa.sock: ready"; \
			[ $$sherpa_skip -eq 1 ] && echo "  stt-sherpa.sock: skipped (crashed)"; \
			exit 0; \
		fi; \
		[ $$vad_ok -eq 0 ]    && echo "  [$$i/60] waiting for vad.sock..."; \
		[ $$mlx_ok -eq 0 ]    && echo "  [$$i/60] waiting for stt-mlx.sock..."; \
		[ $$sherpa_ok -eq 0 ] && echo "  [$$i/60] waiting for stt-sherpa.sock..."; \
		sleep 1; \
	done; \
	echo "ERROR: plugin sockets not ready after 60s. Check logs in $(LOGS_DIR)."; \
	exit 1

_wait-socks-dummy:
	@echo "Waiting for dummy plugin sockets (up to 60s)..."
	@for i in $$(seq 1 60); do \
		vad_ok=0; stt_ok=0; \
		[ -S $(SOCKET_DIR)/vad.sock ]       && vad_ok=1; \
		[ -S $(SOCKET_DIR)/stt-dummy.sock ] && stt_ok=1; \
		if [ $$vad_ok -eq 1 ] && [ $$stt_ok -eq 1 ]; then \
			echo "  vad.sock: ready"; \
			echo "  stt-dummy.sock: ready"; \
			exit 0; \
		fi; \
		[ $$vad_ok -eq 0 ] && echo "  [$$i/60] waiting for vad.sock..."; \
		[ $$stt_ok -eq 0 ] && echo "  [$$i/60] waiting for stt-dummy.sock..."; \
		sleep 1; \
	done; \
	echo "ERROR: dummy plugin sockets not ready after 60s. Check logs in $(LOGS_DIR)."; \
	exit 1

# Check if a component is already running.
# Usage: $(call _check-running,vad)
# - pid file exists + process alive → error (user must run 'make stop-all' first)
# - pid file exists but process dead → stale, clean up silently
# - no pid file → ok
define _check-running
	@if [ -f $(PIDS_DIR)/$(1).pid ]; then \
		if kill -0 $$(cat $(PIDS_DIR)/$(1).pid) 2>/dev/null; then \
			echo "ERROR: $(1) is already running (pid=$$(cat $(PIDS_DIR)/$(1).pid)). Run 'make stop-all' first."; \
			exit 1; \
		else \
			echo "$(1): removing stale pid file"; \
			rm -f $(PIDS_DIR)/$(1).pid; \
		fi; \
	fi
endef

# Check if a TCP port is free.
# Usage: $(call _check-port,7000)
define _check-port
	@if lsof -ti :$(1) >/dev/null 2>&1; then \
		echo "ERROR: port $(1) already in use by pid=$$(lsof -ti :$(1)). Free the port first."; \
		exit 1; \
	fi
endef

# ── Run (real engines) ──

run: _ensure-dirs run-vad run-stt _wait-socks run-core
	@echo "All processes started (sherpa-onnx + mlx-whisper). Use 'make status' to check."

run-all: run run-web
	@echo "Full stack started (backend + web). Use 'make status' to check."

run-vad:
	$(call _check-running,vad)
	cd plugin-vad && \
	$(PYTHON) -m speechmux_plugin_vad.main \
		--config config/vad.yaml \
		>> $(LOGS_DIR)/vad.log 2>&1 & echo $$! > $(PIDS_DIR)/vad.pid
	@echo "VAD Plugin started (pid=$$(cat $(PIDS_DIR)/vad.pid), log=$(LOGS_DIR)/vad.log)"

run-stt: run-stt-sherpa run-stt-mlx

run-stt-sherpa:
	$(call _check-running,stt-sherpa)
	cd plugin-stt && \
	$(PYTHON) -m speechmux_plugin_stt.main \
		--config config/inference-onnx.yaml \
		>> $(LOGS_DIR)/stt-sherpa.log 2>&1 & echo $$! > $(PIDS_DIR)/stt-sherpa.pid
	@echo "STT Plugin (sherpa-onnx) started (pid=$$(cat $(PIDS_DIR)/stt-sherpa.pid), log=$(LOGS_DIR)/stt-sherpa.log)"

run-stt-mlx:
	$(call _check-running,stt-mlx)
	cd plugin-stt && \
	$(PYTHON) -m speechmux_plugin_stt.main \
		--config config/inference-mlx.yaml \
		>> $(LOGS_DIR)/stt-mlx.log 2>&1 & echo $$! > $(PIDS_DIR)/stt-mlx.pid
	@echo "STT Plugin (mlx-whisper) started (pid=$$(cat $(PIDS_DIR)/stt-mlx.pid), log=$(LOGS_DIR)/stt-mlx.log)"

run-core:
	$(call _check-running,core)
	$(call _check-port,50051)
	$(call _check-port,8090)
	$(call _check-port,8091)
	cd core && \
	./bin/speechmux-core \
		--config config/core.yaml \
		--plugins config/plugins.yaml \
		>> $(LOGS_DIR)/core.log 2>&1 & echo $$! > $(PIDS_DIR)/core.pid
	@echo "Core started (pid=$$(cat $(PIDS_DIR)/core.pid), log=$(LOGS_DIR)/core.log)"

run-core-dummy:
	$(call _check-running,core)
	$(call _check-port,50051)
	$(call _check-port,8090)
	$(call _check-port,8091)
	cd core && \
	./bin/speechmux-core \
		--config config/core.yaml \
		--plugins config/plugins-dummy.yaml \
		>> $(LOGS_DIR)/core.log 2>&1 & echo $$! > $(PIDS_DIR)/core.pid
	@echo "Core started (pid=$$(cat $(PIDS_DIR)/core.pid), log=$(LOGS_DIR)/core.log)"

# ── Run (Dummy engines — for load testing) ──

run-dummy: _ensure-dirs run-dummy-vad run-dummy-stt _wait-socks-dummy run-core-dummy
	@echo "Dummy plugins + Core started. Ready for load test."

run-dummy-vad:
	$(call _check-running,vad)
	cd plugin-vad && \
	$(PYTHON) -m speechmux_plugin_vad.main \
		--config config/vad-dummy.yaml \
		>> $(LOGS_DIR)/vad.log 2>&1 & echo $$! > $(PIDS_DIR)/vad.pid
	@echo "VAD Plugin (dummy) started (pid=$$(cat $(PIDS_DIR)/vad.pid), log=$(LOGS_DIR)/vad.log)"

run-dummy-stt:
	$(call _check-running,stt-dummy)
	cd plugin-stt && \
	$(PYTHON) -m speechmux_plugin_stt.main \
		--config config/inference-dummy.yaml \
		>> $(LOGS_DIR)/stt-dummy.log 2>&1 & echo $$! > $(PIDS_DIR)/stt-dummy.pid
	@echo "STT Plugin (dummy) started (pid=$$(cat $(PIDS_DIR)/stt-dummy.pid), log=$(LOGS_DIR)/stt-dummy.log)"

# ── Status / Stop ──

logs:
	@echo "Log files in $(LOGS_DIR):"
	@ls -lh $(LOGS_DIR)/*.log 2>/dev/null || echo "  (no log files yet)"
	@echo ""
	@echo "Usage: tail -f $(LOGS_DIR)/<name>.log"

status:
	@for name in vad stt-sherpa stt-mlx stt-dummy core web-api web-next caddy; do \
		if [ -f $(PIDS_DIR)/$$name.pid ] && kill -0 $$(cat $(PIDS_DIR)/$$name.pid) 2>/dev/null; then \
			echo "$$name: running (pid=$$(cat $(PIDS_DIR)/$$name.pid))"; \
		else \
			echo "$$name: stopped"; \
		fi; \
	done

stop:
	@for name in core stt-sherpa stt-mlx stt-dummy vad; do \
		if [ -f $(PIDS_DIR)/$$name.pid ]; then \
			pid=$$(cat $(PIDS_DIR)/$$name.pid); \
			pkill -P $$pid 2>/dev/null || true; \
			kill $$pid 2>/dev/null || true; \
			rm -f $(PIDS_DIR)/$$name.pid; \
			echo "$$name: stopped"; \
		fi; \
	done
	@lsof -ti :$(CORE_GRPC_PORT) | xargs kill 2>/dev/null || true
	@lsof -ti :$(CORE_HTTP_PORT) | xargs kill 2>/dev/null || true
	@lsof -ti :$(CORE_WS_PORT)   | xargs kill 2>/dev/null || true
	@rm -f $(SOCKET_DIR)/*.sock

stop-all: stop stop-web stop-caddy
	@echo "Full stack stopped."

# ── Test ──

test:
	@if [ -d proto ]; then cd proto && make generate; fi
	@if [ -d core ]; then cd core && $(GO) test ./...; fi
	@if [ -d plugin-vad ]; then \
		echo "Testing plugin-vad..."; \
		(cd plugin-vad && $(PYTHON) -m pytest tests/) || exit 1; \
	fi
	@if [ -d plugin-stt ]; then \
		echo "Testing plugin-stt..."; \
		(cd plugin-stt && $(PYTHON) -m pytest tests/) || exit 1; \
	fi
	@# Engine implementations — any cloned plugin-vad-* / plugin-stt-* package
	@for d in plugin-vad-* plugin-stt-*; do \
		if [ -d "$$d" ]; then \
			echo "Testing $$d..."; \
			(cd "$$d" && $(PYTHON) -m pytest tests/) || exit 1; \
		fi; \
	done
	@if [ -d client-cli ]; then \
		echo "Testing client-cli..."; \
		(cd client-cli && $(PYTHON) -m pytest tests/) || exit 1; \
	fi

# ── Load test ──

loadtest: run-dummy
	cd core && $(GO) build -o bin/loadtest ./tools/loadtest
	cd core && ./bin/loadtest --sessions 100 --duration 5m
	$(MAKE) stop

# ── Web client ──

run-web: _ensure-dirs
	$(call _check-running,web-api)
	$(call _check-running,web-next)
	$(call _check-port,$(WEB_API_PORT))
	$(call _check-port,$(WEB_NEXT_PORT))
	@printf "NEXT_PUBLIC_API_PORT=$(WEB_API_PORT)\n" > client-web/web/.env.local
	@printf "CORE_WS_URL=ws://localhost:$(CORE_WS_PORT)/ws/stream\nCORS_ORIGINS=*\n" > client-web/api/.env
	@echo "Starting FastAPI proxy (port $(WEB_API_PORT)) and Next.js (port $(WEB_NEXT_PORT))…"
	cd client-web/api && $(UV) run uvicorn speechmux_api.main:app --host 0.0.0.0 --port $(WEB_API_PORT) --reload --ws-per-message-deflate false >> $(LOGS_DIR)/web-api.log 2>&1 & echo $$! > $(PIDS_DIR)/web-api.pid
	@echo "FastAPI started (pid=$$(cat $(PIDS_DIR)/web-api.pid), log=$(LOGS_DIR)/web-api.log)"
	cd client-web/web && npm run dev -- --port $(WEB_NEXT_PORT) >> $(LOGS_DIR)/web-next.log 2>&1 & echo $$! > $(PIDS_DIR)/web-next.pid
	@echo "Next.js started (pid=$$(cat $(PIDS_DIR)/web-next.pid), log=$(LOGS_DIR)/web-next.log)"
	@echo "Open http://localhost:$(WEB_NEXT_PORT) in your browser."

stop-web:
	@for name in web-api web-next; do \
		if [ -f $(PIDS_DIR)/$$name.pid ]; then \
			pid=$$(cat $(PIDS_DIR)/$$name.pid); \
			pkill -P $$pid 2>/dev/null || true; \
			kill $$pid 2>/dev/null || true; \
			rm -f $(PIDS_DIR)/$$name.pid; \
			echo "$$name: stopped"; \
		fi; \
	done
	@lsof -ti :$(WEB_NEXT_PORT) | xargs kill 2>/dev/null || true
	@lsof -ti :$(WEB_API_PORT)  | xargs kill 2>/dev/null || true

# ── Web client (HTTPS via Caddy — required for microphone access) ──

caddy-trust:
	@echo "Starting Caddy briefly to install local CA into system trust store…"
	$(CADDY) run --config client-web/Caddyfile --adapter caddyfile &
	@sleep 2
	$(CADDY) trust
	@pkill -f "caddy run --config" 2>/dev/null || true
	@echo "CA installed. Certificate warnings should be gone on the next browser launch."

run-web-caddy: _ensure-dirs
	$(call _check-running,web-api)
	$(call _check-running,web-next)
	$(call _check-running,caddy)
	$(call _check-port,$(WEB_API_PORT))
	$(call _check-port,$(WEB_NEXT_PORT))
	$(call _check-port,$(CADDY_PORT))
	@# NEXT_PUBLIC_API_PORT is empty → Next.js uses same-origin WS (proxied by Caddy)
	@printf "NEXT_PUBLIC_API_PORT=\n" > client-web/web/.env.local
	@printf "CORE_WS_URL=ws://localhost:$(CORE_WS_PORT)/ws/stream\nCORS_ORIGINS=*\n" > client-web/api/.env
	@echo "Starting FastAPI proxy (port $(WEB_API_PORT)) and Next.js (port $(WEB_NEXT_PORT))…"
	cd client-web/api && $(UV) run uvicorn speechmux_api.main:app --host 0.0.0.0 --port $(WEB_API_PORT) --reload --ws-per-message-deflate false >> $(LOGS_DIR)/web-api.log 2>&1 & echo $$! > $(PIDS_DIR)/web-api.pid
	@echo "FastAPI started (pid=$$(cat $(PIDS_DIR)/web-api.pid), log=$(LOGS_DIR)/web-api.log)"
	cd client-web/web && npm run dev -- --port $(WEB_NEXT_PORT) >> $(LOGS_DIR)/web-next.log 2>&1 & echo $$! > $(PIDS_DIR)/web-next.pid
	@echo "Next.js started (pid=$$(cat $(PIDS_DIR)/web-next.pid), log=$(LOGS_DIR)/web-next.log)"
	CADDY_PORT=$(CADDY_PORT) WEB_API_PORT=$(WEB_API_PORT) WEB_NEXT_PORT=$(WEB_NEXT_PORT) \
		$(CADDY) run --config client-web/Caddyfile --adapter caddyfile >> $(LOGS_DIR)/caddy.log 2>&1 & echo $$! > $(PIDS_DIR)/caddy.pid
	@echo "Caddy started (pid=$$(cat $(PIDS_DIR)/caddy.pid), log=$(LOGS_DIR)/caddy.log)"
	@echo "Open https://localhost:$(CADDY_PORT) in your browser (mic access enabled)."
	@echo "Tip: run 'make caddy-trust' once if you see certificate warnings."

stop-caddy:
	@if [ -f $(PIDS_DIR)/caddy.pid ]; then \
		pid=$$(cat $(PIDS_DIR)/caddy.pid); \
		kill $$pid 2>/dev/null || true; \
		rm -f $(PIDS_DIR)/caddy.pid; \
		echo "caddy: stopped"; \
	fi
	@lsof -ti :$(CADDY_PORT) | xargs kill 2>/dev/null || true

run-all-caddy: run run-web-caddy
	@echo "Full stack started with HTTPS (backend + web + caddy). Use 'make status' to check."

run-all-tailscale: run _ensure-dirs
	$(call _check-running,web-api)
	$(call _check-running,web-next)
	$(call _check-running,caddy)
	$(call _check-port,$(WEB_API_PORT))
	$(call _check-port,$(WEB_NEXT_PORT))
	$(call _check-port,$(CADDY_NOTLS_PORT))
	@# NEXT_PUBLIC_API_PORT is empty → Next.js uses same-origin wss:// (Tailscale hostname, port 443)
	@printf "NEXT_PUBLIC_API_PORT=\n" > client-web/web/.env.local
	@printf "CORE_WS_URL=ws://localhost:$(CORE_WS_PORT)/ws/stream\nCORS_ORIGINS=*\n" > client-web/api/.env
	cd client-web/api && $(UV) run uvicorn speechmux_api.main:app --host 0.0.0.0 --port $(WEB_API_PORT) --reload --ws-per-message-deflate false >> $(LOGS_DIR)/web-api.log 2>&1 & echo $$! > $(PIDS_DIR)/web-api.pid
	@echo "FastAPI started (pid=$$(cat $(PIDS_DIR)/web-api.pid), log=$(LOGS_DIR)/web-api.log)"
	cd client-web/web && npm run dev -- --port $(WEB_NEXT_PORT) >> $(LOGS_DIR)/web-next.log 2>&1 & echo $$! > $(PIDS_DIR)/web-next.pid
	@echo "Next.js started (pid=$$(cat $(PIDS_DIR)/web-next.pid), log=$(LOGS_DIR)/web-next.log)"
	@# Caddy as plain HTTP router — Tailscale terminates TLS, so no tls internal here
	CADDY_NOTLS_PORT=$(CADDY_NOTLS_PORT) WEB_API_PORT=$(WEB_API_PORT) WEB_NEXT_PORT=$(WEB_NEXT_PORT) \
		$(CADDY) run --config client-web/Caddyfile.proxy --adapter caddyfile >> $(LOGS_DIR)/caddy.log 2>&1 & echo $$! > $(PIDS_DIR)/caddy.pid
	@echo "Caddy (plain HTTP router) started (pid=$$(cat $(PIDS_DIR)/caddy.pid), log=$(LOGS_DIR)/caddy.log)"
	$(TAILSCALE) serve --bg --https 8444 http://localhost:$(CADDY_NOTLS_PORT)
	@echo "Tailscale HTTPS proxy started."
	@echo "Access from phone: https://kelvin.wind-rankine.ts.net:8444"

stop-tailscale:
	$(TAILSCALE) serve --bg --https 8444 off 2>/dev/null || true

# ── Clean ──

clean: stop stop-web
	rm -rf core/bin
	rm -rf $(SOCKET_DIR)
