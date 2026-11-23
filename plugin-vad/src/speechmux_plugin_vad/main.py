"""VAD Plugin gRPC server entrypoint."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from concurrent import futures
from typing import Any, cast

import grpc  # type: ignore[import-untyped]

from stt_proto.vad.v1 import vad_pb2_grpc  # type: ignore[import-untyped]

from speechmux_plugin_vad.engine.base import VADEngine
from speechmux_plugin_vad.engine.registry import get_engine, list_engines
from speechmux_plugin_vad.service.vad_servicer import VADPluginServicer

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the VAD Plugin server.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]`` when ``None``.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(description="SpeechMux VAD Plugin")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to vad.yaml config file (required)",
    )
    return parser.parse_args(argv)


def _load_yaml_config(config_path: str) -> dict[str, Any]:
    """Load and validate the YAML config file at *config_path*.

    Args:
        config_path: Filesystem path to the VAD YAML config.

    Returns:
        Parsed config dict.

    Raises:
        SystemExit: When the file cannot be read or is not a valid mapping.
    """
    try:
        import yaml  # pyyaml — listed in pyproject.toml dependencies

        with open(config_path) as f:
            result = yaml.safe_load(f)
        if not isinstance(result, dict):
            print(f"ERROR: config file {config_path!r} is not a YAML mapping", file=sys.stderr)
            sys.exit(1)
        return result
    except FileNotFoundError:
        print(f"ERROR: config file not found: {config_path!r}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: failed to load config {config_path!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def _require_server_field(config: dict[str, Any], key: str) -> str:
    """Return config.server.<key> as a string, or exit with a clear error.

    Args:
        config: Top-level parsed YAML dict.
        key: Key name under the ``server`` section.

    Returns:
        The string value for the requested key.

    Raises:
        SystemExit: When the key is absent or empty.
    """
    value = (config.get("server") or {}).get(key)
    if not value:
        print(f"ERROR: missing required config key: server.{key}", file=sys.stderr)
        sys.exit(1)
    return str(value)


def _load_engine(engine_name: str, config: dict[str, Any]) -> VADEngine:
    """Instantiate the VAD engine registered under *engine_name*.

    Args:
        engine_name: Entry-point name from the ``speechmux.vad_engine`` group.
        config: Top-level parsed YAML dict (engine section is read from here).

    Returns:
        An initialised ``VADEngine`` instance.

    Raises:
        SystemExit: When the engine name is not found in registered entry-points.
    """
    if engine_name == "dummy":
        dummy_cfg: dict[str, Any] = (config.get("engine") or {}).get("dummy") or {}
        from speechmux_plugin_vad.engine.dummy import DummyVADEngine

        return cast(
            VADEngine,
            DummyVADEngine(
                speech_prob=float(dummy_cfg.get("speech_prob") or 0.8),
                latency_ms=float(dummy_cfg.get("latency_ms") or 0.0),
                speech_ms=int(dummy_cfg.get("speech_ms") or 0),
                silence_ms=int(dummy_cfg.get("silence_ms") or 0),
            ),
        )
    engine_config: dict[str, Any] = (config.get("engine") or {}).get(engine_name) or {}
    try:
        return get_engine(engine_name, engine_config if engine_config else None)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Available engines: {list_engines()}", file=sys.stderr)
        sys.exit(1)


def serve(argv: list[str] | None = None) -> None:
    """Start the VAD Plugin gRPC server and block until stopped."""
    args = _parse_args(argv)
    config = _load_yaml_config(args.config)

    server_cfg: dict[str, Any] = config.get("server") or {}
    engine_name = _require_server_field(config, "engine")
    socket_path: str = str(server_cfg.get("socket") or "")
    tcp_address: str = str(server_cfg.get("address") or "")
    log_level = str(server_cfg.get("log_level") or "INFO").upper()

    if not socket_path and not tcp_address:
        print("ERROR: server.socket or server.address must be set", file=sys.stderr)
        sys.exit(1)
    if socket_path and tcp_address:
        print("ERROR: server.socket and server.address are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    engine = _load_engine(engine_name, config)

    # Allow server.max_concurrent_sessions from YAML to override the engine default.
    yaml_max_sessions = server_cfg.get("max_concurrent_sessions")
    if yaml_max_sessions is not None:
        engine.max_concurrent_sessions = int(yaml_max_sessions)

    logger.info("Loaded VAD engine: %s (model=%s)", engine_name, engine.model_name)

    servicer = VADPluginServicer(engine)

    # max_workers = max_concurrent_sessions + 4 to prevent hidden queueing.
    # See design doc §10.13: if workers == sessions, the health-check RPC
    # can starve waiting for a worker while all are occupied by VAD streams.
    max_workers = engine.max_concurrent_sessions + 4
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    vad_pb2_grpc.add_VADPluginServicer_to_server(servicer, server)

    if tcp_address:
        addr = tcp_address          # TCP: "0.0.0.0:50060"
    else:
        addr = f"unix://{socket_path}"  # UDS: "unix:///tmp/speechmux/vad.sock"
    server.add_insecure_port(addr)
    server.start()
    logger.info("VAD Plugin listening on %s (engine=%s)", addr, engine_name)

    def _handle_stop(signum: int, frame: object) -> None:
        logger.info("Received signal %d, stopping…", signum)
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    server.wait_for_termination()
    logger.info("VAD Plugin stopped")


if __name__ == "__main__":
    serve()
