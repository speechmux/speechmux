"""LanguageRecognizers: one sherpa-onnx OnlineRecognizer per language, shared across sessions."""

from __future__ import annotations

import logging

import sherpa_onnx

from .config import SherpaOnnxConfig

logger = logging.getLogger(__name__)


class LanguageRecognizers:
    """Holds one OnlineRecognizer per language, initialized at startup and shared across sessions.

    ONNX Runtime's InferenceSession.Run() is safe to call concurrently from multiple threads
    with different input tensors. Each session receives its own OnlineStream, so concurrent
    decode() calls on the shared recognizer are safe without additional locking.

    The _recognizers dict is read-only after __init__, so no locking is required for lookups.
    """

    def __init__(self, cfg: SherpaOnnxConfig) -> None:
        """Initialise one OnlineRecognizer per configured language.

        Args:
            cfg: Plugin configuration containing model paths and recognizer parameters.

        Raises:
            RuntimeError: When no languages are configured.
        """
        if not cfg.models.languages:
            raise RuntimeError("no languages configured in models.languages")

        self._default_language = cfg.models.default_language
        self._recognizers: dict[str, sherpa_onnx.OnlineRecognizer] = {}
        endpoint = cfg.endpoint_detection
        recognizer_cfg = cfg.recognizer

        for language_code, model in cfg.models.languages.items():
            logger.info(
                "Loading sherpa-onnx recognizer for language=%s encoder=%s",
                language_code,
                model.encoder,
            )
            self._recognizers[language_code] = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=model.tokens,
                encoder=model.encoder,
                decoder=model.decoder,
                joiner=model.joiner,
                num_threads=recognizer_cfg.num_threads,
                sample_rate=recognizer_cfg.sample_rate,
                feature_dim=recognizer_cfg.feature_dim,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=endpoint.rule1_min_trailing_silence,
                rule2_min_trailing_silence=endpoint.rule2_min_trailing_silence,
                rule3_min_utterance_length=endpoint.rule3_min_utterance_length,
            )
            logger.info("Recognizer ready for language=%s", language_code)

        if self._default_language not in self._recognizers:
            # Fall back to the first available language so the plugin can still serve requests.
            first_language = next(iter(self._recognizers))
            logger.warning(
                "default_language=%s not in configured languages; falling back to %s",
                self._default_language,
                first_language,
            )
            self._default_language = first_language

    def get(self, language_code: str) -> sherpa_onnx.OnlineRecognizer:
        """Return the recognizer for *language_code*, or the default if empty.

        The servicer validates language_code before calling this method; reaching
        the fallback branch here indicates a programming error.

        Args:
            language_code: BCP-47 language code (e.g. "ko"), or empty string for default.

        Returns:
            The OnlineRecognizer for the requested language, or the default-language
            recognizer when *language_code* is empty.
        """
        recognizer = self._recognizers.get(language_code)
        if recognizer is not None:
            return recognizer
        logger.warning(
            "language_code=%r not found; falling back to default %s",
            language_code,
            self._default_language,
        )
        return self._recognizers[self._default_language]

    @property
    def supported_languages(self) -> list[str]:
        """BCP-47 codes for all configured languages."""
        return list(self._recognizers.keys())
