"""Dummy VAD engine for load testing — no ML model required."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

from speechmux_plugin_vad.engine.base import VADEngine


@dataclass
class _DummyState:
    """Per-session state for the dummy VAD engine."""

    threshold: float
    frame_count: int = field(default=0)


class DummyVADEngine(VADEngine):
    """Dummy VAD engine that simulates speech/silence cycles.

    Useful for load testing and CI without a GPU or model weights.

    When ``speech_ms`` and ``silence_ms`` are both zero (default), the engine
    returns ``speech_prob`` for every frame (legacy fixed-probability mode).

    When ``speech_ms > 0``, the engine cycles: speech for ``speech_ms``
    milliseconds then silence for ``silence_ms`` milliseconds, repeating for
    the lifetime of the session.  This ensures the EPD controller sees
    speech→silence transitions and emits decode tasks, exercising the full
    pipeline during load tests.

    Args:
        speech_prob: Fixed speech probability returned per frame (0.0–1.0).
            Clamped to the valid range.
        latency_ms: Artificial per-frame delay in milliseconds. Set to 0 to disable.
        speech_ms: Cycle mode speech window duration in milliseconds. 0 = fixed mode.
        silence_ms: Cycle mode silence window duration in milliseconds. 0 = fixed mode.
    """

    model_name: str = "dummy_vad"
    optimal_frame_ms: int = 20
    supported_sample_rates: list[int] = None  # type: ignore[assignment]
    max_concurrent_sessions: int = 1000

    def __init__(
        self,
        speech_prob: float = 0.8,
        latency_ms: float = 0.0,
        speech_ms: int = 0,
        silence_ms: int = 0,
    ) -> None:
        self.speech_prob = max(0.0, min(1.0, speech_prob))
        self.latency_ms = max(0.0, latency_ms)
        # Cycle-mode parameters (frames = ms / optimal_frame_ms).
        self._speech_frames = max(0, speech_ms // self.optimal_frame_ms)
        self._silence_frames = max(0, silence_ms // self.optimal_frame_ms)
        self._cycle_frames = self._speech_frames + self._silence_frames
        self.supported_sample_rates = [8000, 16000, 48000]

    def create_session_state(self, threshold: float) -> _DummyState:
        """Create a dummy session state.

        Args:
            threshold: Speech probability threshold (0.0-1.0).

        Returns:
            A ``_DummyState`` instance.
        """
        return _DummyState(threshold=threshold)

    def process_frame(
        self,
        session_state: object,
        pcm_data: bytes,
        sample_rate: int,
    ) -> tuple[bool, float, float]:
        """Return a speech probability for the given audio frame.

        In fixed mode (``speech_ms == 0``) every frame returns ``speech_prob``.
        In cycle mode the probability alternates between ``speech_prob`` during
        the speech window and ``0.0`` during the silence window so that the EPD
        controller fires at each cycle boundary.

        Args:
            session_state: State object returned by ``create_session_state``.
            pcm_data: Raw PCM S16LE audio bytes.
            sample_rate: Sample rate in Hz (unused by dummy engine).

        Returns:
            A ``(is_speech, speech_probability, chunk_rms)`` tuple.
        """
        state = session_state  # protocol requires object; runtime type is _DummyState
        assert isinstance(state, _DummyState)

        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        rms = _pcm16_rms(pcm_data)

        if self._cycle_frames > 0:
            position = state.frame_count % self._cycle_frames
            probability = self.speech_prob if position < self._speech_frames else 0.0
        else:
            probability = self.speech_prob

        state.frame_count += 1
        is_speech = probability >= state.threshold
        return is_speech, probability, rms


def _pcm16_rms(pcm_data: bytes) -> float:
    """Return the RMS amplitude of a PCM S16LE byte buffer, normalised to [0, 1].

    Args:
        pcm_data: Raw PCM S16LE byte buffer to measure.

    Returns:
        RMS value in [0.0, 1.0] where 1.0 is full-scale (32767).
    """
    if not pcm_data:
        return 0.0
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{num_samples}h", pcm_data[:num_samples * 2])
    sq_sum: int = sum(sample * sample for sample in samples)
    return float((sq_sum / num_samples) ** 0.5 / 32768.0)
