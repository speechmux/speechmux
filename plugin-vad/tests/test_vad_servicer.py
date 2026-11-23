"""Tests for VADPluginServicer protocol with the Dummy engine."""

from __future__ import annotations

import struct
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from speechmux_plugin_vad.engine.dummy import DummyVADEngine
from speechmux_plugin_vad.service.vad_servicer import VADPluginServicer
from google.protobuf import empty_pb2
from stt_proto.common.v1 import common_pb2
from stt_proto.vad.v1 import vad_pb2


def _pcm_bytes(n_samples: int = 160, value: int = 1000) -> bytes:
    """Create PCM S16LE bytes filled with a constant value."""
    return struct.pack(f"<{n_samples}h", *([value] * n_samples))


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.abort.side_effect = RuntimeError("abort called")
    return ctx


def _session_start_msg(session_id: str = "s1", threshold: float = 0.5) -> vad_pb2.VADRequest:
    return vad_pb2.VADRequest(
        session_start=vad_pb2.SessionStart(session_id=session_id, threshold=threshold)
    )


def _audio_msg(pcm: bytes, seq: int = 0) -> vad_pb2.VADRequest:
    return vad_pb2.VADRequest(pcm_data=pcm, sample_rate=16000, sequence_number=seq)


def _session_end_msg() -> vad_pb2.VADRequest:
    return vad_pb2.VADRequest(session_end=vad_pb2.SessionEnd())


# ── basic protocol ─────────────────────────────────────────────────────────

def test_stream_vad_returns_response_per_audio_frame():
    engine = DummyVADEngine(speech_prob=0.9)
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    frames = [
        _session_start_msg("s1", threshold=0.5),
        _audio_msg(_pcm_bytes(), seq=1),
        _audio_msg(_pcm_bytes(), seq=2),
        _session_end_msg(),
    ]
    responses = list(svc.StreamVAD(iter(frames), ctx))

    assert len(responses) == 2
    assert all(r.is_speech for r in responses)
    assert all(r.speech_probability == pytest.approx(0.9) for r in responses)


def test_sequence_number_echoed():
    engine = DummyVADEngine(speech_prob=0.8)
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    frames = [
        _session_start_msg(),
        _audio_msg(_pcm_bytes(), seq=42),
        _session_end_msg(),
    ]
    responses = list(svc.StreamVAD(iter(frames), ctx))
    assert responses[0].sequence_number == 42


def test_active_count_decremented_after_stream():
    engine = DummyVADEngine()
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    frames = [_session_start_msg(), _audio_msg(_pcm_bytes()), _session_end_msg()]
    list(svc.StreamVAD(iter(frames), ctx))

    health = svc.HealthCheck(empty_pb2.Empty(), ctx)
    assert health.active == 0


def test_capacity_limit_aborts_stream():
    engine = DummyVADEngine()
    engine.max_concurrent_sessions = 1
    svc = VADPluginServicer(engine)

    # Open first stream and consume its first audio response so the slot is held.
    # The generator is suspended at the `yield` with _active == 1.
    ctx1 = _make_context()
    stream1: Iterator = svc.StreamVAD(
        iter([_session_start_msg("s1"), _audio_msg(_pcm_bytes())]), ctx1
    )
    next(stream1)  # first VADResponse — generator suspended, _active == 1

    # Second stream should abort with RESOURCE_EXHAUSTED.
    ctx2 = MagicMock()
    ctx2.abort.side_effect = RuntimeError("aborted")
    with pytest.raises(RuntimeError, match="aborted"):
        list(svc.StreamVAD(iter([_session_start_msg("s2")]), ctx2))

    import grpc as grpc_mod
    ctx2.abort.assert_called_once_with(
        grpc_mod.StatusCode.RESOURCE_EXHAUSTED, "VAD plugin at session capacity"
    )


def test_audio_before_session_start_is_ignored():
    engine = DummyVADEngine()
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    # No session_start — audio frames should produce no responses.
    frames = [_audio_msg(_pcm_bytes(), seq=1), _audio_msg(_pcm_bytes(), seq=2)]
    responses = list(svc.StreamVAD(iter(frames), ctx))
    assert responses == []


def test_chunk_duration_computed_correctly():
    engine = DummyVADEngine()
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    # 320 samples @ 16kHz → 20ms = 0.02s
    frames = [_session_start_msg(), _audio_msg(_pcm_bytes(320), seq=1), _session_end_msg()]
    responses = list(svc.StreamVAD(iter(frames), ctx))
    assert responses[0].chunk_duration_sec == pytest.approx(0.02)


# ── GetCapabilities ────────────────────────────────────────────────────────

def test_get_capabilities():
    engine = DummyVADEngine()
    svc = VADPluginServicer(engine)
    ctx = _make_context()
    caps = svc.GetCapabilities(empty_pb2.Empty(), ctx)
    assert caps.model_name == "dummy_vad"
    assert caps.optimal_frame_ms > 0
    assert len(caps.supported_sample_rates) > 0


# ── HealthCheck ────────────────────────────────────────────────────────────

def test_health_check_initial():
    engine = DummyVADEngine()
    svc = VADPluginServicer(engine)
    ctx = _make_context()
    health = svc.HealthCheck(empty_pb2.Empty(), ctx)
    assert health.state == common_pb2.PLUGIN_STATE_READY
    assert health.active == 0


def test_health_message_ok():
    svc = VADPluginServicer(DummyVADEngine())
    ctx = _make_context()
    health = svc.HealthCheck(empty_pb2.Empty(), ctx)
    assert health.message == "ok"


# ── threshold override ─────────────────────────────────────────────────────

def test_threshold_below_prob_gives_is_speech():
    engine = DummyVADEngine(speech_prob=0.6)
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    frames = [_session_start_msg(threshold=0.3), _audio_msg(_pcm_bytes()), _session_end_msg()]
    responses = list(svc.StreamVAD(iter(frames), ctx))
    assert responses[0].is_speech is True


def test_threshold_above_prob_gives_not_speech():
    engine = DummyVADEngine(speech_prob=0.4)
    svc = VADPluginServicer(engine)
    ctx = _make_context()

    frames = [_session_start_msg(threshold=0.8), _audio_msg(_pcm_bytes()), _session_end_msg()]
    responses = list(svc.StreamVAD(iter(frames), ctx))
    assert responses[0].is_speech is False
