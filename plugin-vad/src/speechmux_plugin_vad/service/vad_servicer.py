"""VAD Plugin gRPC servicer — one StreamVAD stream per session."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING

import grpc  # type: ignore[import-untyped]

from stt_proto.common.v1 import common_pb2  # type: ignore[import-untyped]
from stt_proto.vad.v1 import vad_pb2, vad_pb2_grpc  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from speechmux_plugin_vad.engine.base import VADEngine

logger = logging.getLogger(__name__)


class VADPluginServicer(vad_pb2_grpc.VADPluginServicer):
    """VAD Plugin gRPC service implementation.

    Each ``StreamVAD`` call corresponds to exactly one client session.
    gRPC's thread pool assigns a worker thread per stream, so sessions
    run concurrently without any explicit multiplexing.

    The ``max_concurrent_sessions`` limit is enforced with an atomic counter.
    """

    def __init__(self, engine: "VADEngine") -> None:
        self._engine = engine
        self._active: int = 0
        self._state: int = common_pb2.PLUGIN_STATE_READY
        self._last_error_code: int = common_pb2.PLUGIN_ERROR_UNSPECIFIED
        self._last_error_msg: str = ""
        self._lock = threading.Lock()

    # ── StreamVAD ──────────────────────────────────────────────────────────

    def StreamVAD(
        self,
        request_iterator: Iterator[vad_pb2.VADRequest],
        context: grpc.ServicerContext,
    ) -> Iterator[vad_pb2.VADResponse]:
        """Process a per-session VAD stream.

        First message MUST carry ``session_start``; subsequent messages carry
        ``pcm_data``; a ``session_end`` message terminates the stream cleanly.
        """
        # Debounce thresholds for logging only (do not affect VAD output).
        # Silero raw output flips between speech/silence within an utterance.
        # Require N consecutive same-state frames before logging a transition,
        # so vad.log reflects stable utterance boundaries rather than raw flips.
        _SPEECH_ONSET_FRAMES: int = 3   # ~96 ms at 32 ms/frame → log speech_start
        _SILENCE_ONSET_FRAMES: int = 10  # ~320 ms at 32 ms/frame → log speech_end

        session_state = None
        session_id: str = ""
        logged_is_speech: bool = False   # last transition state that was logged
        prev_raw_is_speech: bool = False  # previous raw frame state (for streak counting)
        consecutive_count: int = 0        # consecutive frames in the current raw state
        speech_frame_count: int = 0       # total speech frames since last speech_start log

        try:
            for request in request_iterator:
                signal = request.WhichOneof("signal")

                # ── session_start ──────────────────────────────────────────
                if signal == "session_start":
                    with self._lock:
                        max_sessions = self._engine.max_concurrent_sessions
                        if max_sessions > 0 and self._active >= max_sessions:
                            context.abort(
                                grpc.StatusCode.RESOURCE_EXHAUSTED,
                                "VAD plugin at session capacity",
                            )
                            return
                        self._active += 1

                    threshold = request.session_start.threshold or 0.5
                    session_id = request.session_start.session_id
                    session_state = self._engine.create_session_state(threshold)
                    logger.info(
                        "session_start session_id=%s threshold=%.3f active=%d",
                        session_id,
                        threshold,
                        self._active,
                    )
                    continue

                # ── session_end ────────────────────────────────────────────
                if signal == "session_end":
                    logger.info("session_end session_id=%s", session_id or "unknown")
                    break

                # ── audio frame ────────────────────────────────────────────
                if session_state is None:
                    # session_start not yet received — skip silently
                    continue

                pcm_data = request.pcm_data
                sample_rate = request.sample_rate if request.sample_rate > 0 else 16000

                try:
                    is_speech, probability, chunk_rms = self._engine.process_frame(
                        session_state,
                        pcm_data,
                        sample_rate,
                    )
                except Exception as exc:
                    logger.exception("engine.process_frame failed")
                    with self._lock:
                        self._last_error_code = common_pb2.PLUGIN_ERROR_INFERENCE_FAILED
                        self._last_error_msg = f"process_frame failed: {exc}"
                    yield vad_pb2.VADResponse(
                        is_speech=False,
                        speech_probability=0.0,
                        chunk_rms=0.0,
                        chunk_duration_sec=0.0,
                        sequence_number=request.sequence_number,
                        error_code=common_pb2.PLUGIN_ERROR_INFERENCE_FAILED,
                    )
                    continue

                # PCM S16LE: 2 bytes per sample
                samples = len(pcm_data) // 2
                chunk_duration = samples / sample_rate if sample_rate > 0 else 0.0

                yield vad_pb2.VADResponse(
                    is_speech=is_speech,
                    speech_probability=probability,
                    chunk_rms=chunk_rms,
                    chunk_duration_sec=chunk_duration,
                    sequence_number=request.sequence_number,
                    error_code=common_pb2.PLUGIN_ERROR_UNSPECIFIED,
                )

                # Debounced speech/silence transition logging.
                # Track streak of consecutive same-state frames; only log when
                # the streak reaches the onset threshold and the logged state differs.
                if is_speech == prev_raw_is_speech:
                    consecutive_count += 1
                else:
                    consecutive_count = 1
                prev_raw_is_speech = is_speech

                if is_speech:
                    speech_frame_count += 1
                    if not logged_is_speech and consecutive_count >= _SPEECH_ONSET_FRAMES:
                        logged_is_speech = True
                        logger.info(
                            "speech_start session_id=%s seq=%d prob=%.3f",
                            session_id,
                            request.sequence_number,
                            probability,
                        )
                else:
                    if logged_is_speech and consecutive_count >= _SILENCE_ONSET_FRAMES:
                        logged_is_speech = False
                        logger.info(
                            "speech_end session_id=%s seq=%d frames=%d",
                            session_id,
                            request.sequence_number,
                            speech_frame_count,
                        )
                        speech_frame_count = 0

        finally:
            # Always release the session slot, whether the stream ended
            # normally, via session_end, or due to an exception.
            if session_state is not None:
                with self._lock:
                    self._active = max(0, self._active - 1)

    # ── GetCapabilities ────────────────────────────────────────────────────

    def GetCapabilities(
        self,
        request: vad_pb2.Empty,
        context: grpc.ServicerContext,
    ) -> vad_pb2.VADCapabilities:
        """Return static capabilities of the loaded engine."""
        return vad_pb2.VADCapabilities(
            model_name=self._engine.model_name,
            max_concurrent_sessions=self._engine.max_concurrent_sessions,
            optimal_frame_ms=self._engine.optimal_frame_ms,
            supported_sample_rates=self._engine.supported_sample_rates,
        )

    # ── HealthCheck ────────────────────────────────────────────────────────

    def HealthCheck(
        self,
        request: vad_pb2.Empty,
        context: grpc.ServicerContext,
    ) -> common_pb2.PluginHealthStatus:
        """Return current plugin health and active session count."""
        with self._lock:
            active = self._active
            state = self._state
            last_error_code = self._last_error_code
            last_error_msg = self._last_error_msg
        return common_pb2.PluginHealthStatus(
            state=state,
            active=active,
            message=last_error_msg if last_error_msg else "ok",
            last_error=last_error_code,
        )
