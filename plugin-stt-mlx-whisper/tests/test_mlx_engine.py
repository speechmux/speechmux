"""Tests for MlxWhisperEngine.

mlx_whisper is not installed in CI.  We mock the entire module via sys.modules
before importing MlxWhisperEngine, mirroring the pattern used by the Silero
test suite.
"""

from __future__ import annotations

import struct
import sys
from unittest.mock import MagicMock

import pytest


def _pcm_bytes(n_samples: int = 512, amplitude: int = 8000) -> bytes:
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def _silence_bytes(n_samples: int = 512) -> bytes:
    return bytes(n_samples * 2)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_mlx_whisper():
    """Inject a mock mlx_whisper module before any test imports the engine."""
    mod = MagicMock()
    mod.transcribe.return_value = {
        "text": " hello world",
        "language": "en",
        "segments": [
            {
                "text": " hello world",
                "start": 0.0,
                "end": 0.064,
                "avg_logprob": -0.3,
                "no_speech_prob": 0.01,
            }
        ],
    }
    sys.modules["mlx_whisper"] = mod
    yield mod
    sys.modules.pop("mlx_whisper", None)
    # Force reimport of the engine to clear the cached lazy import.
    sys.modules.pop("speechmux_plugin_stt_mlx_whisper.engine", None)


@pytest.fixture()
def engine(mock_mlx_whisper):
    from speechmux_plugin_stt_mlx_whisper.engine import MlxWhisperEngine
    return MlxWhisperEngine(model_size="small")


# ── transcribe ────────────────────────────────────────────────────────────────

def test_transcribe_returns_result(engine):
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


def test_transcribe_result_is_namedtuple(engine):
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


def test_transcribe_audio_duration_computed(engine):
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


def test_transcribe_segments_mapped(engine):
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


def test_transcribe_calls_mlx_whisper_with_repo(mock_mlx_whisper):
    sys.modules.pop("speechmux_plugin_stt_mlx_whisper.engine", None)
    from speechmux_plugin_stt_mlx_whisper.engine import MlxWhisperEngine

    eng = MlxWhisperEngine(model_size="tiny")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="en",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    mock_mlx_whisper.transcribe.assert_called_once()
    _, kwargs = mock_mlx_whisper.transcribe.call_args
    assert "mlx-community/whisper-tiny" in kwargs.get("path_or_hf_repo", "")


# ── option mapping ────────────────────────────────────────────────────────────

def test_language_passed_to_mlx(mock_mlx_whisper):
    sys.modules.pop("speechmux_plugin_stt_mlx_whisper.engine", None)
    from speechmux_plugin_stt_mlx_whisper.engine import MlxWhisperEngine

    eng = MlxWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="ko",
        task="transcribe",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    _, kwargs = mock_mlx_whisper.transcribe.call_args
    assert kwargs.get("language") == "ko"


def test_translate_task_passed(mock_mlx_whisper):
    sys.modules.pop("speechmux_plugin_stt_mlx_whisper.engine", None)
    from speechmux_plugin_stt_mlx_whisper.engine import MlxWhisperEngine

    eng = MlxWhisperEngine(model_size="small")
    eng.transcribe(
        audio_data=_pcm_bytes(512),
        sample_rate=16000,
        language_code="ja",
        task="translate",
        decode_options={},
        is_final=True,
        is_partial=False,
    )
    _, kwargs = mock_mlx_whisper.transcribe.call_args
    assert kwargs.get("task") == "translate"


# ── engine metadata ────────────────────────────────────────────────────────────

def test_engine_name(engine):
    assert engine.engine_name == "mlx_whisper"


def test_max_concurrent_requests(engine):
    assert engine.max_concurrent_requests == 1


def test_supported_languages_includes_common(engine):
    for lang in ("en", "ko", "ja", "zh"):
        assert lang in engine.supported_languages
