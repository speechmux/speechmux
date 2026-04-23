"""Configuration dataclasses and YAML loaders for the sherpa-onnx plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelConfig:
    """Paths to the four ONNX model files for one language.

    Attributes:
        encoder: Path to the Zipformer encoder ONNX file.
        decoder: Path to the prediction network ONNX file.
        joiner: Path to the joint network ONNX file.
        tokens: Path to the vocabulary tokens.txt file.
    """

    encoder: str
    decoder: str
    joiner: str
    tokens: str


@dataclass
class EndpointConfig:
    """sherpa-onnx built-in endpoint detection rules.

    sherpa-onnx evaluates all three rules after each decoded chunk.
    An endpoint fires when ANY rule is satisfied.

    Attributes:
        rule1_min_trailing_silence: Seconds of silence required after any speech
            (no minimum utterance length).
        rule2_min_trailing_silence: Seconds of silence required after ≥1.0 s of
            confirmed speech.
        rule3_min_utterance_length: Force-finalize when the utterance exceeds
            this many seconds regardless of silence.
    """

    rule1_min_trailing_silence: float = 2.4
    rule2_min_trailing_silence: float = 1.2
    rule3_min_utterance_length: float = 20.0


@dataclass
class RecognizerConfig:
    """OnlineRecognizer construction parameters.

    Attributes:
        num_threads: ONNX Runtime intra-op threads per recognizer.
        sample_rate: PCM sample rate in Hz (must match Core's codec.target_sample_rate).
        feature_dim: Mel-filterbank bins (must match model training; 80 for most Zipformer).
    """

    num_threads: int = 2
    sample_rate: int = 16000
    feature_dim: int = 80


@dataclass
class ModelsConfig:
    """Language-to-model mapping.

    Attributes:
        default_language: BCP-47 code used when the session language is absent
            or unsupported.
        languages: Map from BCP-47 code to ModelConfig.
    """

    default_language: str = "ko"
    languages: dict[str, ModelConfig] = field(default_factory=dict)


@dataclass
class SherpaOnnxConfig:
    """Engine-level configuration for the sherpa-onnx Zipformer plugin.

    Attributes:
        models: Language model paths and default language selection.
        recognizer: OnlineRecognizer construction parameters.
        endpoint_detection: Built-in endpoint detection rule thresholds.
    """

    models: ModelsConfig
    recognizer: RecognizerConfig
    endpoint_detection: EndpointConfig


def _parse_languages(languages_raw: dict[str, Any]) -> dict[str, ModelConfig]:
    languages: dict[str, ModelConfig] = {}
    for language_code, language_cfg in languages_raw.items():
        if not isinstance(language_cfg, dict):
            raise ValueError(f"models.languages.{language_code} must be a mapping")
        languages[str(language_code)] = ModelConfig(
            encoder=str(language_cfg["encoder"]),
            decoder=str(language_cfg["decoder"]),
            joiner=str(language_cfg["joiner"]),
            tokens=str(language_cfg["tokens"]),
        )
    return languages


def load_config_from_dict(config: dict[str, Any]) -> SherpaOnnxConfig:
    """Deserialise the engine config dict from plugin-stt's inference.yaml.

    *config* is the ``engine.sherpa_onnx_zipformer`` section dict, containing
    ``recognizer``, ``endpoint_detection``, and ``models`` keys.

    Args:
        config: Engine config dict (value of ``engine.sherpa_onnx_zipformer``).

    Returns:
        Parsed SherpaOnnxConfig.

    Raises:
        ValueError: When required model fields are missing or malformed.
    """
    models_section: dict[str, Any] = config.get("models") or {}
    recognizer_section: dict[str, Any] = config.get("recognizer") or {}
    endpoint_section: dict[str, Any] = config.get("endpoint_detection") or {}

    languages = _parse_languages(models_section.get("languages") or {})

    return SherpaOnnxConfig(
        models=ModelsConfig(
            default_language=str(models_section.get("default_language") or "ko"),
            languages=languages,
        ),
        recognizer=RecognizerConfig(
            num_threads=int(recognizer_section.get("num_threads") or 2),
            sample_rate=int(recognizer_section.get("sample_rate") or 16000),
            feature_dim=int(recognizer_section.get("feature_dim") or 80),
        ),
        endpoint_detection=EndpointConfig(
            rule1_min_trailing_silence=float(
                endpoint_section.get("rule1_min_trailing_silence") or 2.4
            ),
            rule2_min_trailing_silence=float(
                endpoint_section.get("rule2_min_trailing_silence") or 1.2
            ),
            rule3_min_utterance_length=float(
                endpoint_section.get("rule3_min_utterance_length") or 20.0
            ),
        ),
    )


def load_config(path: str) -> SherpaOnnxConfig:
    """Load and deserialise a standalone plugin YAML config file.

    This function supports direct YAML files (for development / manual testing).
    In production, use ``load_config_from_dict`` with the dict from plugin-stt's
    ``inference.yaml``.

    Args:
        path: Filesystem path to an inference YAML config.

    Returns:
        Parsed SherpaOnnxConfig.

    Raises:
        FileNotFoundError: When *path* does not exist.
        ValueError: When required fields are missing.
    """
    import yaml  # pyyaml — dev dependency only; not required for production path

    with open(path) as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file)

    return load_config_from_dict(raw)
