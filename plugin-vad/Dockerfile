# Build context: workspace root (required for proto/ and plugin-vad-silero/).
FROM python:3.13-slim
WORKDIR /app

RUN pip install --no-cache-dir uv

# Install plugin-vad framework dependencies from lockfile (cached layer).
COPY plugin-vad/pyproject.toml plugin-vad/uv.lock ./
RUN uv sync --frozen --no-dev

# Install proto and Silero engine AFTER sync so sync does not remove them.
# plugin-vad-silero pulls in torch/torchaudio/silero-vad as dependencies.
COPY proto/gen/python/ /tmp/proto/
COPY plugin-vad-silero/ /tmp/plugin-vad-silero/
RUN uv pip install /tmp/proto/ /tmp/plugin-vad-silero/

# Install plugin-vad source in editable mode.
COPY plugin-vad/src/ src/
RUN uv pip install --no-deps -e .

EXPOSE 50060

ENTRYPOINT ["uv", "run", "python", "-m", "speechmux_plugin_vad.main"]
CMD ["--config", "/etc/speechmux/vad.yaml"]
