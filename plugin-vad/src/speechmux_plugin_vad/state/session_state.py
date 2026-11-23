"""Per-session VAD state container."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field


@dataclass
class SessionVADState:
    """Holds engine-specific hidden state for a single VAD session.

    Each StreamVAD stream owns one instance; engine implementations
    store their mutable model state (hidden tensors, frame buffers)
    inside the ``engine_state`` field.
    """

    # engine_state is opaque to the servicer — each engine defines its own type.
    engine_state: object

    # Threshold from the SessionStart message (or engine default).
    threshold: float

    # Rolling frame buffer for engines that need to accumulate samples
    # before processing (e.g. Silero requires 512-sample windows).
    frame_buffer: collections.deque[bytes] = field(default_factory=collections.deque)
    buffered_samples: int = 0
