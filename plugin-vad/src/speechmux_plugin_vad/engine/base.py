"""VADEngine Protocol — interface all VAD engine implementations must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VADEngine(Protocol):
    """Interface for VAD engine backends.

    A VADEngine is stateless with respect to sessions; per-session state is
    created via ``create_session_state`` and passed back on each ``process_frame``
    call.  This allows one engine instance to serve many concurrent sessions.
    """

    #: Human-readable engine name returned in GetCapabilities.
    model_name: str

    #: Optimal audio frame size in milliseconds for this engine.
    optimal_frame_ms: int

    #: List of supported sample rates (Hz).
    supported_sample_rates: list[int]

    #: Maximum number of concurrent sessions this engine can serve.
    max_concurrent_sessions: int

    def create_session_state(self, threshold: float) -> object:
        """Create and return a fresh per-session state object.

        Args:
            threshold: Speech probability threshold (0.0–1.0).

        Returns:
            An opaque session state object passed to every ``process_frame`` call.
            Concrete type is defined by each engine implementation.
        """
        ...

    def process_frame(
        self,
        session_state: object,
        pcm_data: bytes,
        sample_rate: int,
    ) -> tuple[bool, float, float]:
        """Process one audio frame and return VAD results.

        Args:
            session_state: The state object returned by ``create_session_state``.
            pcm_data: Raw PCM S16LE audio bytes.
            sample_rate: Sample rate of the audio in Hz.

        Returns:
            A ``(is_speech, speech_probability, chunk_rms)`` tuple.
        """
        ...
