"""MlxWhisperEngine — mlx-whisper inference engine for Apple Silicon."""

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

# Map standard Whisper model-size names to mlx-community HuggingFace repos.
_MODEL_REPO_MAP: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "tiny.en": "mlx-community/whisper-tiny.en-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "base.en": "mlx-community/whisper-base.en-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "small.en": "mlx-community/whisper-small.en-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "medium.en": "mlx-community/whisper-medium.en-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v1": "mlx-community/whisper-large-v1-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

_FLOAT16_ALIASES = {"float16", "fp16", "half"}

# Languages supported by Whisper (abridged; full list in mlx-whisper).
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
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return np.empty(0, dtype=np.float32)
    samples = np.array(struct.unpack(f"<{num_samples}h", pcm_data[: num_samples * 2]), dtype=np.float32)
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
    from scipy.signal import resample_poly  # type: ignore[import-untyped]

    gcd = math.gcd(src_rate, dst_rate)
    up, down = dst_rate // gcd, src_rate // gcd
    return resample_poly(audio, up, down).astype("float32")


class MlxWhisperEngine(InferenceEngine):
    """MLX Whisper engine for Apple Silicon (M-series chips).

    Model weights are loaded eagerly in ``load()``, which is called once at
    startup before the gRPC server starts. This prevents the first
    ``transcribe`` call from triggering a slow model download or disk load.

    Args:
        model_size: Whisper model size alias (e.g. ``"small"``, ``"large-v3-turbo"``)
            or a full HuggingFace repo path (e.g. ``"mlx-community/whisper-large-v3-turbo"``).
        compute_type: MLX compute dtype — ``"float16"`` (default, Metal fp16) or
            ``"float32"`` (fallback for unsupported operations).
    """

    engine_name: str = "mlx_whisper"
    device: str = "mlx"
    supported_languages: list[str] = _SUPPORTED_LANGUAGES
    max_concurrent_requests: int = 1  # MLX is single-threaded on the GPU
    supports_partial_decode: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> MlxWhisperEngine:
        """Construct from an ``inference.yaml`` ``engine.mlx_whisper`` section.

        Args:
            config: Dict with keys ``model`` (HuggingFace repo or size alias),
                ``compute_type`` (default ``float16``).  Unknown keys are ignored.

        Returns:
            A fully initialised ``MlxWhisperEngine``.
        """
        model = str(config.get("model") or "small")
        compute_type = str(config.get("compute_type") or "float16")
        return cls(model_size=model, compute_type=compute_type)

    def __init__(
        self,
        model_size: str = "small",
        compute_type: str = "float16",
    ) -> None:
        self.model_size = model_size
        self._compute_type = compute_type
        # Accept either a model-size alias or a full HuggingFace repo path.
        if "/" in model_size:
            self._model_repo = model_size
        else:
            self._model_repo = _MODEL_REPO_MAP.get(
                model_size, f"mlx-community/whisper-{model_size}-mlx"
            )
        logger.info(
            "MlxWhisperEngine initialised repo=%s compute_type=%s",
            self._model_repo,
            compute_type,
        )

    def load(self) -> None:
        """Eagerly load model weights into MLX unified memory.

        Downloads the model from HuggingFace Hub if not already cached, then
        loads the weights via ``ModelHolder.get_model()``. After this call,
        subsequent ``transcribe`` calls reuse the cached model with no
        additional disk or network I/O.

        Returns:
            None
        """
        try:
            import mlx.core as mx  # type: ignore[import-untyped]
            from mlx_whisper.transcribe import ModelHolder  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "mlx_whisper is not installed; run: pip install mlx-whisper"
            ) from exc

        dtype = mx.float16 if self._compute_type in _FLOAT16_ALIASES else mx.float32
        logger.info(
            "Loading model %s into memory (dtype=%s, may download on first run)…",
            self._model_repo,
            dtype,
        )
        ModelHolder.get_model(self._model_repo, dtype)
        logger.info("Model %s ready.", self._model_repo)

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
        """Run mlx-whisper inference on a PCM S16LE audio segment.

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
        try:
            import mlx_whisper  # type: ignore[import-untyped]  # lazy import — only needed at inference time
        except ImportError as exc:
            raise ImportError(
                "mlx_whisper is not installed; run: pip install mlx-whisper"
            ) from exc

        if not sample_rate or sample_rate <= 0:
            sample_rate = 16000

        audio_f32 = _pcm16_to_float32(audio_data)
        if sample_rate != 16000:
            audio_f32 = _resample(audio_f32, sample_rate, 16000)

        n_samples = len(audio_data) // 2
        audio_duration_sec = n_samples / sample_rate

        opts = self._build_opts(decode_options, language_code, task)

        inference_start_time = time.perf_counter()
        result = mlx_whisper.transcribe(
            audio_f32,
            path_or_hf_repo=self._model_repo,
            **opts,
        )
        inference_sec = time.perf_counter() - inference_start_time

        real_time_factor = inference_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0
        text: str = result.get("text") or ""
        detected_language: str = result.get("language") or language_code or "en"
        if not isinstance(detected_language, str):
            detected_language = str(detected_language)

        raw_segments: list[dict[str, str | float]] = result.get("segments") or []
        segments: list[dict[str, str | float]] = []
        no_speech_threshold = float(opts.get("no_speech_threshold", 0.6))
        for segment in raw_segments:
            if not isinstance(segment, dict):
                continue
            segment_no_speech = float(segment.get("no_speech_prob") or 0.0)
            # Skip segments that Whisper itself considers non-speech.
            if segment_no_speech > no_speech_threshold:
                logger.debug(
                    "Dropping hallucinated segment (no_speech_prob=%.3f): %s",
                    segment_no_speech,
                    str(segment.get("text") or "")[:80],
                )
                continue
            segments.append(
                {
                    "text": str(segment.get("text") or ""),
                    "start_sec": float(segment.get("start") or 0.0),
                    "end_sec": float(segment.get("end") or 0.0),
                    "avg_log_prob": float(segment.get("avg_logprob") or 0.0),
                    "no_speech_prob": segment_no_speech,
                }
            )

        # Rebuild text from surviving segments only.
        if segments:
            text = "".join(str(seg["text"]) for seg in segments).strip()
        else:
            text = ""

        no_speech = not text.strip()

        return TranscribeResult(
            text=text,
            language_code=detected_language,
            inference_sec=inference_sec,
            audio_duration_sec=audio_duration_sec,
            real_time_factor=real_time_factor,
            segments=segments,
            no_speech_detected=no_speech,
        )

    def _build_opts(
        self,
        decode_options: dict[str, float | int | bool],
        language_code: str,
        task: str,
    ) -> dict[str, str | float | int | bool]:
        """Build mlx_whisper.transcribe keyword arguments.

        Args:
            decode_options: Caller-provided decoding parameters.
            language_code: BCP-47 language code.
            task: ``"transcribe"`` or ``"translate"``.

        Returns:
            Merged options dict with anti-hallucination defaults applied.
        """
        opts: dict[str, str | float | int | bool] = {}

        if language_code:
            opts["language"] = language_code
        if task and task != "transcribe":
            opts["task"] = task

        # Anti-hallucination defaults (Whisper standard values).
        # Segments with no_speech_prob above this threshold are suppressed.
        opts["no_speech_threshold"] = 0.6
        # Segments with avg log probability below this are discarded.
        opts["logprob_threshold"] = -1.0
        # Segments with compression ratio above this are discarded (repetition).
        opts["compression_ratio_threshold"] = 2.4
        # Do not condition on previous text to avoid cascading hallucinations
        # in streaming/partial decode scenarios.
        opts["condition_on_previous_text"] = False

        # Map proto DecodeOptions fields to mlx_whisper kwargs.
        # Caller-provided values override defaults above.
        key_map = {
            "temperature": "temperature",
            "compression_ratio_threshold": "compression_ratio_threshold",
            "no_speech_threshold": "no_speech_threshold",
            "log_prob_threshold": "logprob_threshold",
            "length_penalty": "length_penalty",
        }
        for src, dst in key_map.items():
            if decode_options.get(src):
                opts[dst] = decode_options[src]

        if decode_options.get("without_timestamps"):
            opts["word_timestamps"] = False

        # beam_size is not yet supported by mlx-whisper; omit silently.
        # best_of maps to nothing in greedy mode; omit silently.

        opts["fp16"] = self._compute_type in _FLOAT16_ALIASES
        return opts
