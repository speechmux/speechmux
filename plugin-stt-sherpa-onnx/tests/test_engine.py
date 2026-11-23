"""Unit tests for SherpaOnnxEngine and module-level helpers.

Tests cover PCM conversion, engine attributes, language fallback, and the
module-level _force_finalize / _flush helpers. All tests mock sherpa_onnx so
no model files are required.
"""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import MagicMock

import numpy as np

# ── PCM conversion ────────────────────────────────────────────────────────────


def test_int16_to_float32_range() -> None:
    """Output values must be in [-1, 1] for any int16 input."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _int16_to_float32

    samples = [0, 32767, -32768, 1000, -1000]
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    result = _int16_to_float32(pcm)
    assert result.dtype == np.float32
    assert np.all(result >= -1.0)
    assert np.all(result <= 1.0)


def test_int16_to_float32_zero_bytes() -> None:
    """Empty input must return an empty float32 array without raising."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _int16_to_float32

    result = _int16_to_float32(b"")
    assert result.dtype == np.float32
    assert len(result) == 0


def test_int16_to_float32_shape_preserved() -> None:
    """Output length must equal number of int16 samples in the input."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _int16_to_float32

    n_samples = 512
    pcm = struct.pack(f"<{n_samples}h", *([1000] * n_samples))
    result = _int16_to_float32(pcm)
    assert len(result) == n_samples


def test_int16_to_float32_odd_bytes_truncated() -> None:
    """An odd trailing byte must be silently ignored (floor division)."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _int16_to_float32

    pcm = struct.pack("<2h", 100, 200) + b"\xff"  # 5 bytes total
    result = _int16_to_float32(pcm)
    assert len(result) == 2


# ── Engine attribute checks ───────────────────────────────────────────────────


def _make_engine(mock_sherpa_onnx: MagicMock) -> Any:
    """Construct a SherpaOnnxEngine with a single Korean language configuration.

    Args:
        mock_sherpa_onnx: The mocked sherpa_onnx module fixture.

    Returns:
        Configured SherpaOnnxEngine instance.
    """
    from speechmux_plugin_stt_sherpa_onnx.config import (
        EndpointConfig,
        ModelConfig,
        ModelsConfig,
        RecognizerConfig,
        SherpaOnnxConfig,
    )
    from speechmux_plugin_stt_sherpa_onnx.engine import SherpaOnnxEngine
    from speechmux_plugin_stt_sherpa_onnx.recognizer import LanguageRecognizers

    cfg = SherpaOnnxConfig(
        models=ModelsConfig(
            default_language="ko",
            languages={
                "ko": ModelConfig(
                    encoder="enc.onnx",
                    decoder="dec.onnx",
                    joiner="joi.onnx",
                    tokens="tok.txt",
                )
            },
        ),
        recognizer=RecognizerConfig(num_threads=1, sample_rate=16000, feature_dim=80),
        endpoint_detection=EndpointConfig(),
    )
    recognizers = LanguageRecognizers(cfg)
    return SherpaOnnxEngine(recognizers=recognizers, max_concurrent_sessions=4)


def test_engine_name(mock_sherpa_onnx: MagicMock) -> None:
    """engine_name must be 'sherpa_onnx_zipformer'."""
    engine = _make_engine(mock_sherpa_onnx)
    assert engine.engine_name == "sherpa_onnx_zipformer"


def test_engine_streaming_mode_native(mock_sherpa_onnx: MagicMock) -> None:
    """streaming_mode must equal STREAMING_MODE_NATIVE."""
    from stt_proto.inference.v1 import inference_pb2

    engine = _make_engine(mock_sherpa_onnx)
    assert engine.streaming_mode == inference_pb2.StreamingMode.STREAMING_MODE_NATIVE


def test_engine_endpointing_auto_finalize(mock_sherpa_onnx: MagicMock) -> None:
    """endpointing_capability must equal ENDPOINTING_CAPABILITY_AUTO_FINALIZE."""
    from stt_proto.inference.v1 import inference_pb2

    engine = _make_engine(mock_sherpa_onnx)
    assert (
        engine.endpointing_capability
        == inference_pb2.EndpointingCapability.ENDPOINTING_CAPABILITY_AUTO_FINALIZE
    )


def test_engine_supported_languages(mock_sherpa_onnx: MagicMock) -> None:
    """supported_languages must list all configured language codes."""
    engine = _make_engine(mock_sherpa_onnx)
    assert "ko" in engine.supported_languages


def test_engine_max_concurrent_sessions(mock_sherpa_onnx: MagicMock) -> None:
    """max_concurrent_sessions must reflect the constructor argument."""
    engine = _make_engine(mock_sherpa_onnx)
    assert engine.max_concurrent_sessions == 4


def test_engine_implements_streaming_protocol(mock_sherpa_onnx: MagicMock) -> None:
    """SherpaOnnxEngine must satisfy the StreamingInferenceEngine Protocol."""
    from speechmux_plugin_stt.engine.base import StreamingInferenceEngine

    engine = _make_engine(mock_sherpa_onnx)
    assert isinstance(engine, StreamingInferenceEngine)


# ── Language fallback ─────────────────────────────────────────────────────────


def test_language_fallback_unknown(mock_sherpa_onnx: MagicMock) -> None:
    """An unknown language_code must fall back to the default recognizer."""
    from speechmux_plugin_stt_sherpa_onnx.config import (
        EndpointConfig,
        ModelConfig,
        ModelsConfig,
        RecognizerConfig,
        SherpaOnnxConfig,
    )
    from speechmux_plugin_stt_sherpa_onnx.recognizer import LanguageRecognizers

    cfg = SherpaOnnxConfig(
        models=ModelsConfig(
            default_language="ko",
            languages={
                "ko": ModelConfig(
                    encoder="enc.onnx",
                    decoder="dec.onnx",
                    joiner="joi.onnx",
                    tokens="tok.txt",
                )
            },
        ),
        recognizer=RecognizerConfig(),
        endpoint_detection=EndpointConfig(),
    )
    recognizers = LanguageRecognizers(cfg)
    ko_recognizer = recognizers.get("ko")
    unknown_recognizer = recognizers.get("zh")  # not configured
    assert unknown_recognizer is ko_recognizer


def test_language_fallback_empty_code(mock_sherpa_onnx: MagicMock) -> None:
    """An empty language_code string must fall back to the default recognizer."""
    from speechmux_plugin_stt_sherpa_onnx.config import (
        EndpointConfig,
        ModelConfig,
        ModelsConfig,
        RecognizerConfig,
        SherpaOnnxConfig,
    )
    from speechmux_plugin_stt_sherpa_onnx.recognizer import LanguageRecognizers

    cfg = SherpaOnnxConfig(
        models=ModelsConfig(
            default_language="ko",
            languages={
                "ko": ModelConfig(
                    encoder="enc.onnx",
                    decoder="dec.onnx",
                    joiner="joi.onnx",
                    tokens="tok.txt",
                )
            },
        ),
        recognizer=RecognizerConfig(),
        endpoint_detection=EndpointConfig(),
    )
    recognizers = LanguageRecognizers(cfg)
    ko_recognizer = recognizers.get("ko")
    empty_recognizer = recognizers.get("")
    assert empty_recognizer is ko_recognizer


# ── _force_finalize ───────────────────────────────────────────────────────────


def test_force_finalize_emits_final(mock_sherpa_onnx: MagicMock) -> None:
    """_force_finalize must yield exactly one is_final=True response."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _force_finalize

    mock_recognizer = MagicMock()
    mock_stream = MagicMock()
    mock_recognizer.get_result.return_value = "안녕하세요"

    responses = list(_force_finalize(mock_recognizer, mock_stream))
    assert len(responses) == 1
    assert responses[0].hypothesis.is_final is True
    assert responses[0].hypothesis.text == "안녕하세요"


def test_force_finalize_calls_reset(mock_sherpa_onnx: MagicMock) -> None:
    """_force_finalize must call recognizer.reset() to prepare for the next utterance."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _force_finalize

    mock_recognizer = MagicMock()
    mock_stream = MagicMock()
    mock_recognizer.get_result.return_value = "test"

    list(_force_finalize(mock_recognizer, mock_stream))
    mock_recognizer.reset.assert_called_once_with(mock_stream)


# ── _flush ────────────────────────────────────────────────────────────────────


def test_flush_emits_final_when_text_remains(mock_sherpa_onnx: MagicMock) -> None:
    """_flush must emit is_final=True when decoded text remains after input_finished."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _flush

    mock_recognizer = MagicMock()
    mock_stream = MagicMock()
    mock_recognizer.is_ready.return_value = False
    mock_recognizer.get_result.return_value = "remaining speech"

    responses = list(_flush(mock_recognizer, mock_stream))
    assert len(responses) == 1
    assert responses[0].hypothesis.is_final is True
    mock_stream.input_finished.assert_called_once()


def test_flush_emits_nothing_when_empty(mock_sherpa_onnx: MagicMock) -> None:
    """_flush must yield nothing when the buffer is empty after input_finished."""
    from speechmux_plugin_stt_sherpa_onnx.engine import _flush

    mock_recognizer = MagicMock()
    mock_stream = MagicMock()
    mock_recognizer.is_ready.return_value = False
    mock_recognizer.get_result.return_value = ""

    responses = list(_flush(mock_recognizer, mock_stream))
    assert len(responses) == 0
