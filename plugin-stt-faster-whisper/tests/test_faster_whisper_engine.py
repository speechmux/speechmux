"""Tests for FasterWhisperEngine.

faster_whisper is not installed in CI. We mock the entire module via sys.modules
before importing FasterWhisperEngine, mirroring the pattern used by the mlx
test suite.
"""

from __future__ import annotations

import struct
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _pcm_bytes(n_samples: int = 512, amplitude: int = 8000) -> bytes:
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def _silence_bytes(n_samples: int = 512) -> bytes:
    return bytes(n_samples * 2)


def _make_segment(
    text: str = " hello world",
    start: float = 0.0,
    end: float = 0.064,
    avg_logprob: float = -0.3,
    no_speech_prob: float = 0.01,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        start=start,
        end=end,
        avg_logprob=avg_logprob,
        no_speech_prob=no_speech_prob,
    )


def _make_info(language: str = "en", language_probability: float = 0.99) -> SimpleNamespace:
    return SimpleNamespace(language=language, language_probability=language_probability)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_faster_whisper() -> Any:
    """Inject mock faster_whisper and faster_whisper.transcribe modules."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (
        iter([_make_segment()]),
        _make_info(),
    )

    mock_batched = MagicMock()
    mock_batched.transcribe.return_value = (
        iter([_make_segment()]),
        _make_info(),
    )

    mock_fw = MagicMock()
    mock_fw.WhisperModel.return_value = mock_model

    mock_fw_transcribe = MagicMock()
    mock_fw_transcribe.BatchedInferencePipeline.return_value = mock_batched

    sys.modules["faster_whisper"] = mock_fw
    sys.modules["faster_whisper.transcribe"] = mock_fw_transcribe
    yield mock_fw, mock_model, mock_batched

    sys.modules.pop("faster_whisper", None)
    sys.modules.pop("faster_whisper.transcribe", None)
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)


@pytest.fixture()
def engine(mock_faster_whisper: Any) -> Any:
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine
    return FasterWhisperEngine(model_size="small", device="cpu", compute_type="int8")


# ── transcribe ────────────────────────────────────────────────────────────────

def test_transcribe_returns_result(engine: Any) -> None:
    result = engine.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert result.text == "hello world"
    assert result.language_code == "en"


def test_transcribe_result_fields(engine: Any) -> None:
    result = engine.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert isinstance(result.inference_sec, float)
    assert isinstance(result.audio_duration_sec, float)
    assert isinstance(result.real_time_factor, float)


def test_transcribe_audio_duration_computed(engine: Any) -> None:
    # 512 samples @ 16 kHz = 0.032 s
    result = engine.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert result.audio_duration_sec == pytest.approx(0.032)


def test_transcribe_segments_mapped(engine: Any) -> None:
    result = engine.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert "text" in seg
    assert "start_sec" in seg
    assert "end_sec" in seg
    assert "avg_log_prob" in seg
    assert "no_speech_prob" in seg


def test_transcribe_hallucination_filter(mock_faster_whisper: Any) -> None:
    """Segments with no_speech_prob > 0.6 are filtered out."""
    _, mock_model, _ = mock_faster_whisper
    mock_model.transcribe.return_value = (
        iter([_make_segment(no_speech_prob=0.9)]),
        _make_info(),
    )
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine

    eng = FasterWhisperEngine(model_size="small")
    result = eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert result.no_speech_detected is True
    assert result.text == ""
    assert result.segments == []


def test_transcribe_zero_length_audio(engine: Any) -> None:
    result = engine.transcribe(
        audio_data=b"",
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    # Should not raise; RTF is 0.0 for zero-duration audio.
    assert result.real_time_factor == pytest.approx(0.0)


def test_transcribe_invalid_sample_rate_defaults_to_16k(engine: Any) -> None:
    """sample_rate <= 0 must be treated as 16000."""
    result = engine.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=0,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    assert result.audio_duration_sec == pytest.approx(0.032)


# ── option mapping ────────────────────────────────────────────────────────────

def test_language_passed_to_model(mock_faster_whisper: Any) -> None:
    _, mock_model, _ = mock_faster_whisper
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine

    eng = FasterWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="ko",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    _, kwargs = mock_model.transcribe.call_args
    assert kwargs.get("language") == "ko"


def test_translate_task_passed(mock_faster_whisper: Any) -> None:
    _, mock_model, _ = mock_faster_whisper
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine

    eng = FasterWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="ja",
        task="translate",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    _, kwargs = mock_model.transcribe.call_args
    assert kwargs.get("task") == "translate"


def test_batch_size_uses_batched_pipeline(mock_faster_whisper: Any) -> None:
    """batch_size > 1 must route through BatchedInferencePipeline."""
    _, mock_model, mock_batched = mock_faster_whisper
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine

    eng = FasterWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={"batch_size": 8},
        is_final=True,
        is_partial=False,
    )
    mock_batched.transcribe.assert_called_once()
    mock_model.transcribe.assert_not_called()


def test_beam_size_forwarded(mock_faster_whisper: Any) -> None:
    _, mock_model, _ = mock_faster_whisper
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine

    eng = FasterWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={"beam_size": 5},
        is_final=True,
        is_partial=False,
    )
    _, kwargs = mock_model.transcribe.call_args
    assert kwargs.get("beam_size") == 5


# ── engine metadata ────────────────────────────────────────────────────────────

def test_engine_name(engine: Any) -> None:
    assert engine.engine_name == "faster_whisper"


def test_max_concurrent_requests(engine: Any) -> None:
    assert engine.max_concurrent_requests == 4


def test_supported_languages_includes_common(engine: Any) -> None:
    for lang in ("en", "ko", "ja", "zh"):
        assert lang in engine.supported_languages


def test_import_error_without_faster_whisper() -> None:
    """FasterWhisperEngine constructor must raise ImportError when faster_whisper is absent."""
    sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
    with patch.dict(sys.modules, {"faster_whisper": None, "faster_whisper.transcribe": None}):
        sys.modules.pop("speechmux_plugin_stt_faster_whisper.engine", None)
        from speechmux_plugin_stt_faster_whisper.engine import FasterWhisperEngine
        with pytest.raises(ImportError, match="faster_whisper is not installed"):
            FasterWhisperEngine(model_size="small")
