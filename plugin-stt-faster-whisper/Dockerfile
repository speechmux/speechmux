# Build context: workspace root (required for proto/ and plugin-stt/).
# Requires: nvidia-container-toolkit on the host; CUDA 12.4+ driver.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-dev python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir uv

# Install plugin-stt framework base dependencies from lockfile (cached layer).
# Reuses plugin-stt's uv.lock — faster-whisper does not need a separate lockfile.
COPY plugin-stt/pyproject.toml plugin-stt/uv.lock ./
RUN uv sync --frozen --no-dev

# Install proto package and faster-whisper engine adapter.
# plugin-stt is copied to /tmp/plugin-stt so that the [tool.uv.sources] path reference
# in plugin-stt-faster-whisper/pyproject.toml (../plugin-stt) resolves correctly.
COPY proto/gen/python/ /tmp/proto/
COPY plugin-stt/ /tmp/plugin-stt/
COPY plugin-stt-faster-whisper/ /tmp/plugin-stt-faster-whisper/
RUN uv pip install /tmp/proto/ /tmp/plugin-stt-faster-whisper/

# Re-install plugin-stt source in editable mode so imports resolve to /app/src/.
COPY plugin-stt/src/ src/
RUN uv pip install --no-deps -e .

# Models are mounted at /models at runtime — no model files baked into the image.
VOLUME ["/models"]

EXPOSE 50062

ENTRYPOINT ["uv", "run", "python3", "-m", "speechmux_plugin_stt.main"]
CMD ["--config", "/etc/speechmux/inference.yaml"]
