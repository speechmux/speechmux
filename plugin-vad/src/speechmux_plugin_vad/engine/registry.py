"""Engine discovery via Python entry_points."""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from speechmux_plugin_vad.engine.base import VADEngine

_ENTRY_POINT_GROUP = "speechmux.vad_engine"


def get_engine(name: str, config: dict[str, Any] | None = None) -> "VADEngine":
    """Load and return the VAD engine registered under *name*.

    If *config* is provided and the engine class exposes a ``from_config``
    classmethod, the engine is constructed via ``cls.from_config(config)``
    so that YAML settings (thresholds, frame sizes, etc.) are applied.
    Otherwise ``cls()`` is called with no arguments.

    Engines register themselves via ``pyproject.toml``::

        [project.entry-points."speechmux.vad_engine"]
        my_engine = "my_package:MyVADEngine"

    Args:
        name: The entry-point name (e.g. ``"dummy"``, ``"silero"``).
        config: Engine-specific config dict from vad.yaml (e.g. the
            ``engine.silero`` section).  Pass ``None`` to use defaults.

    Returns:
        An instantiated ``VADEngine``.

    Raises:
        KeyError: If no engine with that name is installed.
    """
    eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    matches = [ep for ep in eps if ep.name == name]
    if not matches:
        available = sorted(ep.name for ep in eps)
        raise KeyError(
            f"VAD engine {name!r} not found. "
            f"Installed engines: {available or ['(none)']}"
        )
    engine_class = matches[0].load()
    if config is not None and hasattr(engine_class, "from_config"):
        return cast("VADEngine", engine_class.from_config(config))
    return cast("VADEngine", engine_class())


def list_engines() -> list[str]:
    """Return names of all installed VAD engines."""
    eps = importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP)
    return sorted(ep.name for ep in eps)
