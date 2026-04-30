"""SherpaOnnxEngine: StreamingInferenceEngine for sherpa-onnx Zipformer."""

from __future__ import annotations

import logging
from collections.abc import Generator, Iterator
from typing import Any

import numpy as np
import sherpa_onnx
from speechmux_plugin_stt.engine.base import StreamingInferenceEngine
from stt_proto.inference.v1 import inference_pb2

from .config import load_config_from_dict
from .recognizer import LanguageRecognizers

logger = logging.getLogger(__name__)


def _int16_to_float32(pcm_bytes: bytes) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Convert raw int16 LE PCM bytes to a float32 numpy array normalised to [-1, 1].

    Args:
        pcm_bytes: Raw PCM S16LE byte buffer from Core.

    Returns:
        Float32 numpy array with sample values in [-1.0, 1.0].
        Returns an empty array when *pcm_bytes* is empty.
    """
    num_samples = len(pcm_bytes) // 2
    if num_samples == 0:
        return np.empty(0, dtype=np.float32)
    samples = np.frombuffer(pcm_bytes[: num_samples * 2], dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def _force_finalize(
    recognizer: sherpa_onnx.OnlineRecognizer,
    stream: sherpa_onnx.OnlineStream,
) -> Generator[inference_pb2.StreamResponse, None, None]:
    """Emit the current hypothesis as is_final and reset the stream.

    This is the sole reset point when endpointing_source=core. Core's VAD+EPD
    logic sends KIND_FINALIZE_UTTERANCE when it detects sufficient trailing
    silence; the plugin emits is_final and resets the recognizer so the next
    utterance starts from a clean state.

    input_finished() is called before get_result() to flush the model's
    attention-sink lookahead buffer — identical to _flush. Without this,
    tokens still in the unstable region are silently dropped from the final
    hypothesis (the "unstable tail disappears at finalization" bug).

    Args:
        recognizer: Shared OnlineRecognizer for the current session language.
        stream: Per-session OnlineStream.

    Yields:
        One StreamResponse with current text marked is_final=True.
    """
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    text: str = recognizer.get_result(stream)
    yield inference_pb2.StreamResponse(
        hypothesis=inference_pb2.StreamHypothesis(text=text, is_final=True)
    )
    recognizer.reset(stream)


def _flush(
    recognizer: sherpa_onnx.OnlineRecognizer,
    stream: sherpa_onnx.OnlineStream,
) -> Generator[inference_pb2.StreamResponse, None, None]:
    """Flush remaining buffered speech after Core half-closes the stream.

    Args:
        recognizer: Shared OnlineRecognizer for the current session language.
        stream: Per-session OnlineStream.

    Yields:
        One StreamResponse with remaining text marked is_final=True, or nothing
        when the buffer is empty after input_finished().
    """
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    text: str = recognizer.get_result(stream)
    if text:
        yield inference_pb2.StreamResponse(
            hypothesis=inference_pb2.StreamHypothesis(text=text, is_final=True)
        )


class SherpaOnnxEngine(StreamingInferenceEngine):
    """Zipformer streaming STT engine using sherpa-onnx.

    Implements StreamingInferenceEngine. gRPC framing, HealthCheck, semaphore,
    and GetCapabilities are handled by plugin-stt's InferencePluginServicer.

    Thread safety: each concurrent session operates on its own OnlineStream; the
    shared OnlineRecognizers are read-only after startup and safe for concurrent
    decode_stream() calls with different OnlineStream instances.
    """

    engine_name: str = "sherpa_onnx_zipformer"
    streaming_mode: int = inference_pb2.StreamingMode.STREAMING_MODE_NATIVE
    endpointing_capability: int = (
        inference_pb2.EndpointingCapability.ENDPOINTING_CAPABILITY_AUTO_FINALIZE
    )

    def __init__(
        self,
        recognizers: LanguageRecognizers,
        max_concurrent_sessions: int = 4,
    ) -> None:
        """Initialise the engine.

        Args:
            recognizers: Pre-initialised LanguageRecognizers (one per language).
            max_concurrent_sessions: Default session concurrency limit; overridden
                by ``server.max_concurrent_sessions`` in inference.yaml.
        """
        self._recognizers = recognizers
        self.supported_languages = recognizers.supported_languages
        self.max_concurrent_sessions = max_concurrent_sessions

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SherpaOnnxEngine:
        """Construct from the ``engine.sherpa_onnx_zipformer`` config dict.

        Called by plugin-stt's registry when the engine entry-point is loaded.

        Args:
            config: Contents of the ``engine.sherpa_onnx_zipformer`` YAML section.

        Returns:
            A SherpaOnnxEngine with LanguageRecognizers initialised from config.
        """
        cfg = load_config_from_dict(config)
        recognizers = LanguageRecognizers(cfg)
        return cls(recognizers=recognizers)

    def load(self) -> None:
        """No-op: LanguageRecognizers loads model weights in __init__."""

    def stream(
        self,
        request_iterator: Iterator[inference_pb2.StreamRequest],
        session_config: inference_pb2.StreamStartConfig,
    ) -> Generator[inference_pb2.StreamResponse, None, None]:
        """Handle one TranscribeStream bidi session.

        The servicer has already consumed the first (StreamStartConfig) message.
        *request_iterator* yields the remaining AudioChunk / StreamControl messages.

        Args:
            request_iterator: Remaining request messages after StreamStartConfig.
            session_config: Parsed StreamStartConfig from the first message.

        Yields:
            StreamResponse messages (partial and final hypotheses).
        """
        language_code: str = session_config.language_code or ""
        session_id: str = session_config.session_id or ""
        sample_rate: int = session_config.sample_rate or 16000
        logger.info("stream started session_id=%s language=%s", session_id, language_code)

        recognizer = self._recognizers.get(language_code)
        online_stream = recognizer.create_stream()
        last_text = ""

        try:
            for request in request_iterator:
                if request.HasField("audio"):
                    pcm_float32 = _int16_to_float32(request.audio.audio_data)
                    online_stream.accept_waveform(sample_rate, pcm_float32)

                    while recognizer.is_ready(online_stream):
                        recognizer.decode_stream(online_stream)

                    text: str = recognizer.get_result(online_stream)
                    if text and text != last_text:
                        last_text = text
                        logger.debug(
                            "raw_engine_partial session_id=%s text=%s",
                            session_id,
                            repr(text[:80]),
                        )
                        yield inference_pb2.StreamResponse(
                            hypothesis=inference_pb2.StreamHypothesis(
                                text=text, is_final=False
                            )
                        )

                    # is_endpoint() is intentionally NOT checked here.
                    # endpointing_source=core: Core sends KIND_FINALIZE_UTTERANCE
                    # to drive utterance boundaries. Checking is_endpoint() here
                    # would emit spurious is_final=True on every silent frame
                    # (is_endpoint fires repeatedly without reset), creating
                    # multiple fake utterances from a single speech segment.
                    # endpointing_source=engine: would require passing the mode
                    # in StreamStartConfig; deferred until that proto field exists.

                elif request.HasField("control"):
                    kind = request.control.kind
                    if kind == inference_pb2.StreamControl.KIND_FINALIZE_UTTERANCE:
                        for resp in _force_finalize(recognizer, online_stream):
                            if resp.HasField("hypothesis") and resp.hypothesis.is_final:
                                logger.info(
                                    "raw_engine_final session_id=%s text=%s",
                                    session_id,
                                    repr(resp.hypothesis.text[:120]),
                                )
                            yield resp
                        last_text = ""
                    elif kind == inference_pb2.StreamControl.KIND_CANCEL:
                        recognizer.reset(online_stream)
                        last_text = ""

        except Exception:
            logger.exception("error in stream session_id=%s", session_id)
            return

        yield from _flush(recognizer, online_stream)
        logger.info("stream finished session_id=%s", session_id)
