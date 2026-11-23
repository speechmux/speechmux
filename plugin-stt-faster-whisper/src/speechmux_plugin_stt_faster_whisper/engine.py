"""FasterWhisperEngine — CTranslate2-based faster-whisper inference engine."""

from __future__ import annotations

import logging
import math
import struct
import time
from typing import Any

import numpy as np
from numpy.typing import NDArray

from speechmux_plugin_stt.engine.base import InferenceEngine, TranscribeResult

logger = logging.getLogger(__name__)

_FLOAT16_ALIASES = {"float16", "fp16", "half"}

# Languages supported by Whisper.
_SUPPORTED_LANGUAGES = [
    "af", "ar", "hy", "az", "be", "bs", "bg", "ca", "zh", "hr", "cs", "da",
    "nl", "en", "et", "fi", "fr", "gl", "de", "el", "he", "hi", "hu", "is",
    "id", "it", "ja", "kn", "kk", "ko", "lv", "lt", "mk", "ms", "mr", "mi",
    "ne", "no", "fa", "pl", "pt", "ro", "ru", "sr", "sk", "sl", "es", "sw",
    "sv", "tl", "ta", "th", "tr", "uk", "ur", "vi", "cy",
]


def _pcm16_to_float32(pcm_data: bytes) -> NDArray[np.float32]:
    """Convert PCM S16LE bytes to a float32 numpy array in [-1, 1].

    Args:
        pcm_data: Raw PCM S16LE byte buffer.

    Returns:
        Numpy float32 array with sample values normalised to [-1, 1].
    """
    n = len(pcm_data) // 2
    if n == 0:
        return np.empty(0, dtype=np.float32)
    samples = np.array(struct.unpack(f"<{n}h", pcm_data[: n * 2]), dtype=np.float32)
    return samples / 32768.0


def _resample(
    audio: NDArray[np.float32], src_rate: int, dst_rate: int
) -> NDArray[np.float32]:
    """Resample a float32 numpy array from src_rate to dst_rate using scipy.

    Args:
        audio: Input float32 audio samples.
        src_rate: Source sample rate in Hz.
        dst_rate: Target sample rate in Hz.

    Returns:
        Resampled float32 numpy array.
    """
    from scipy.signal import resample_poly

    gcd = math.gcd(src_rate, dst_rate)
    up, down = dst_rate // gcd, src_rate // gcd
    resampled: NDArray[np.float32] = resample_poly(audio, up, down).astype("float32")
    return resampled


class FasterWhisperEngine(InferenceEngine):
    """CTranslate2-based faster-whisper engine (CPU / CUDA).

    Loads the model eagerly during construction. Supports batched inference via
    ``BatchedInferencePipeline`` when ``batch_size > 1`` is requested.
    """

    engine_name: str = "faster_whisper"
    device: str = "cpu"
    supported_languages: list[str] = _SUPPORTED_LANGUAGES
    max_concurrent_requests: int = 4  # CTranslate2 supports concurrent execution
    supports_partial_decode: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> FasterWhisperEngine:
        """Construct from an ``inference.yaml`` ``engine.faster_whisper`` section.

        Args:
            config: Dict with keys ``model`` (model size or HuggingFace ID),
                ``device`` (``cpu`` | ``cuda`` | ``auto``, default ``cpu``),
                ``compute_type`` (``float16`` | ``int8_float16`` | ``int8``,
                default ``int8``).  Unknown keys are ignored.

        Returns:
            A fully initialised ``FasterWhisperEngine``.
        """
        model = str(config.get("model") or "small")
        device = str(config.get("device") or "cpu")
        compute_type = str(config.get("compute_type") or "int8")
        return cls(model_size=model, device=device, compute_type=compute_type)

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.transcribe import BatchedInferencePipeline
        except ImportError as exc:
            raise ImportError(
                "faster_whisper is not installed; run: pip install faster-whisper"
            ) from exc

        self.model_size = model_size
        self.device = device
        self._compute_type = compute_type

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._batched = BatchedInferencePipeline(self._model)
        logger.info(
            "FasterWhisperEngine loaded model=%s device=%s compute_type=%s",
            model_size,
            device,
            compute_type,
        )

    def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int,
        language_code: str,
        task: str,
        decode_options: dict[str, float | int | bool],
        is_final: bool,
        is_partial: bool,
    ) -> TranscribeResult:
        """Run faster-whisper inference on a PCM S16LE audio segment.

        Args:
            audio_data: Raw PCM S16LE byte buffer.
            sample_rate: Sample rate of the input audio in Hz.
            language_code: BCP-47 language code (e.g. ``"en"``, ``"ko"``).
            task: ``"transcribe"`` or ``"translate"``.
            decode_options: Engine-specific decoding parameters.
            is_final: Whether this is the final chunk of the utterance.
            is_partial: Whether this is a partial/interim decode request.

        Returns:
            A ``TranscribeResult`` with text, timing, and segment details.
        """
        if not sample_rate or sample_rate <= 0:
            sample_rate = 16000

        audio_f32 = _pcm16_to_float32(audio_data)
        if sample_rate != 16000:
            audio_f32 = _resample(audio_f32, sample_rate, 16000)

        n_samples = len(audio_data) // 2
        audio_duration_sec = n_samples / sample_rate

        opts, batch_size = self._build_opts(decode_options, language_code, task)

        t0 = time.perf_counter()
        if batch_size is not None and batch_size > 1:
            segments_iter, info = self._batched.transcribe(
                audio_f32, batch_size=batch_size, **opts
            )
        else:
            segments_iter, info = self._model.transcribe(audio_f32, **opts)
        # Consume the lazy generator — inference runs here.
        raw_segments = list(segments_iter)
        inference_sec = time.perf_counter() - t0

        rtf = inference_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0

        detected_lang: str = info.language if info and info.language else (language_code or "en")
        if not isinstance(detected_lang, str):
            detected_lang = str(detected_lang)

        no_speech_thresh: float = float(opts.get("no_speech_threshold", 0.6))
        segments: list[dict[str, str | float]] = []
        for seg in raw_segments:
            seg_no_speech = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
            if seg_no_speech > no_speech_thresh:
                logger.debug(
                    "Dropping hallucinated segment (no_speech_prob=%.3f): %s",
                    seg_no_speech,
                    str(getattr(seg, "text", ""))[:80],
                )
                continue
            segments.append(
                {
                    "text": str(getattr(seg, "text", "") or ""),
                    "start_sec": float(getattr(seg, "start", 0.0) or 0.0),
                    "end_sec": float(getattr(seg, "end", 0.0) or 0.0),
                    "avg_log_prob": float(getattr(seg, "avg_logprob", 0.0) or 0.0),
                    "no_speech_prob": seg_no_speech,
                }
            )

        text = "".join(str(seg["text"]) for seg in segments).strip() if segments else ""
        no_speech = not text.strip()

        return TranscribeResult(
            text=text,
            language_code=detected_lang,
            inference_sec=inference_sec,
            audio_duration_sec=audio_duration_sec,
            real_time_factor=rtf,
            segments=segments,
            no_speech_detected=no_speech,
        )

    def _build_opts(
        self,
        decode_options: dict[str, float | int | bool],
        language_code: str,
        task: str,
    ) -> tuple[dict[str, str | float | int | bool], int | None]:
        """Build faster-whisper transcribe keyword arguments.

        Args:
            decode_options: Caller-provided decoding parameters.
            language_code: BCP-47 language code.
            task: ``"transcribe"`` or ``"translate"``.

        Returns:
            A ``(opts, batch_size)`` tuple where ``opts`` is passed directly to
            ``WhisperModel.transcribe`` / ``BatchedInferencePipeline.transcribe``
            and ``batch_size`` is extracted separately (it is a pipeline-level
            argument, not a model argument).
        """
        opts: dict[str, str | float | int | bool] = {}

        if language_code:
            opts["language"] = language_code
        if task and task != "transcribe":
            opts["task"] = task

        # Anti-hallucination defaults.
        opts["no_speech_threshold"] = 0.6
        opts["log_prob_threshold"] = -1.0
        opts["compression_ratio_threshold"] = 2.4
        opts["condition_on_previous_text"] = False

        # Map proto DecodeOptions fields to faster-whisper kwargs.
        key_map = {
            "temperature": "temperature",
            "compression_ratio_threshold": "compression_ratio_threshold",
            "no_speech_threshold": "no_speech_threshold",
            "log_prob_threshold": "log_prob_threshold",
            "length_penalty": "length_penalty",
            "beam_size": "beam_size",
            "best_of": "best_of",
        }
        for src, dst in key_map.items():
            if decode_options.get(src):
                opts[dst] = decode_options[src]

        if decode_options.get("without_timestamps"):
            opts["word_timestamps"] = False

        # batch_size is a BatchedInferencePipeline argument, not a model argument.
        batch_size: int | None = None
        raw_batch = decode_options.get("batch_size")
        if raw_batch is not None and not isinstance(raw_batch, bool):
            try:
                parsed = int(raw_batch)
                if parsed > 1:
                    batch_size = parsed
            except (TypeError, ValueError):
                pass

        return opts, batch_size
