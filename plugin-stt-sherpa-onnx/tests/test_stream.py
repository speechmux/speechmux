"""Integration tests for the SherpaOnnxEngine.stream() bidi-streaming logic.

Tests drive engine.stream() directly (the servicer has already consumed the
first StreamStartConfig message). No model files are required.
"""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import MagicMock

from stt_proto.inference.v1 import inference_pb2

# ── Helpers ───────────────────────────────────────────────────────────────────


def _pcm_bytes(n_samples: int = 160, amplitude: int = 8000) -> bytes:
    """Create PCM S16LE bytes filled with a constant non-zero amplitude.

    Args:
        n_samples: Number of 16-bit samples.
        amplitude: Sample amplitude value.

    Returns:
        Raw PCM bytes.
    """
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def _make_start_config(language_code: str = "ko") -> inference_pb2.StreamStartConfig:
    """Build a StreamStartConfig proto (already extracted from first message).

    Args:
        language_code: BCP-47 language code for the session.

    Returns:
        StreamStartConfig proto.
    """
    return inference_pb2.StreamStartConfig(
        session_id="test-session",
        language_code=language_code,
        sample_rate=16000,
    )


def _make_start_request(language_code: str = "ko") -> inference_pb2.StreamRequest:
    """Build a StreamRequest with StreamStartConfig payload.

    Args:
        language_code: BCP-47 language code for the session.

    Returns:
        StreamRequest proto.
    """
    return inference_pb2.StreamRequest(
        start=inference_pb2.StreamStartConfig(
            session_id="test-session",
            language_code=language_code,
            sample_rate=16000,
        )
    )


def _make_audio_request(sequence_number: int = 1) -> inference_pb2.StreamRequest:
    """Build a StreamRequest with an AudioChunk payload.

    Args:
        sequence_number: Monotonically increasing sequence counter.

    Returns:
        StreamRequest proto containing 10 ms of 16 kHz PCM.
    """
    return inference_pb2.StreamRequest(
        audio=inference_pb2.AudioChunk(
            sequence_number=sequence_number,
            audio_data=_pcm_bytes(160),
        )
    )


def _make_finalize_request() -> inference_pb2.StreamRequest:
    """Build a StreamRequest with KIND_FINALIZE_UTTERANCE control payload.

    Returns:
        StreamRequest proto.
    """
    return inference_pb2.StreamRequest(
        control=inference_pb2.StreamControl(
            kind=inference_pb2.StreamControl.KIND_FINALIZE_UTTERANCE,
        )
    )


def _make_cancel_request() -> inference_pb2.StreamRequest:
    """Build a StreamRequest with KIND_CANCEL control payload.

    Returns:
        StreamRequest proto.
    """
    return inference_pb2.StreamRequest(
        control=inference_pb2.StreamControl(
            kind=inference_pb2.StreamControl.KIND_CANCEL,
        )
    )


def _build_engine(mock_sherpa_onnx: MagicMock, text: str = "hello") -> Any:
    """Construct a SherpaOnnxEngine backed by the given mock.

    Args:
        mock_sherpa_onnx: The mocked sherpa_onnx module from the conftest fixture.
        text: Text that the mock recognizer will return.

    Returns:
        Configured SherpaOnnxEngine.
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

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.get_result.return_value = text
    mock_recognizer.is_ready.return_value = False

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


def _run_stream(
    engine: Any,
    requests: list[Any],
    language_code: str = "ko",
) -> list[inference_pb2.StreamResponse]:
    """Drive one stream() session and collect all responses.

    Extracts the StreamStartConfig from the first request (simulating what the
    servicer does) and calls engine.stream() with the remaining iterator.

    Args:
        engine: SherpaOnnxEngine instance.
        requests: List of StreamRequest protos (first must be StreamStartConfig).
        language_code: Fallback language when requests list is empty.

    Returns:
        List of StreamResponse protos emitted by the engine.
    """
    if not requests or not requests[0].HasField("start"):
        session_config = _make_start_config(language_code)
        rest: list[Any] = requests
    else:
        session_config = requests[0].start
        rest = requests[1:]
    return list(engine.stream(iter(rest), session_config))


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_partial_then_final(mock_sherpa_onnx: MagicMock) -> None:
    """At least one partial must be emitted before the is_final response."""
    engine = _build_engine(mock_sherpa_onnx, text="hello")

    call_counter = {"count": 0}

    def _is_endpoint(_stream: object) -> bool:
        call_counter["count"] += 1
        return call_counter["count"] >= 3

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.side_effect = _is_endpoint

    requests = [_make_start_request()] + [_make_audio_request(i) for i in range(1, 5)]
    responses = _run_stream(engine, requests)

    partials = [r for r in responses if not r.hypothesis.is_final]
    finals = [r for r in responses if r.hypothesis.is_final]

    assert len(partials) >= 1, "expected at least one partial hypothesis"
    assert len(finals) >= 1, "expected at least one final hypothesis"

    first_partial_index = next(i for i, r in enumerate(responses) if not r.hypothesis.is_final)
    first_final_index = next(i for i, r in enumerate(responses) if r.hypothesis.is_final)
    assert first_partial_index < first_final_index


def test_two_utterances(mock_sherpa_onnx: MagicMock) -> None:
    """Two distinct utterances must each produce an is_final response."""
    engine = _build_engine(mock_sherpa_onnx, text="utterance")

    call_counter = {"count": 0}

    def _is_endpoint(_stream: object) -> bool:
        call_counter["count"] += 1
        return call_counter["count"] in (3, 6)

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.side_effect = _is_endpoint

    requests = [_make_start_request()] + [_make_audio_request(i) for i in range(1, 9)]
    responses = _run_stream(engine, requests)

    finals = [r for r in responses if r.hypothesis.is_final]
    assert len(finals) >= 2, f"expected 2 finals, got {len(finals)}: {responses}"


def test_flush_on_stream_close(mock_sherpa_onnx: MagicMock) -> None:
    """Remaining speech must be flushed with is_final=True when the stream closes."""
    engine = _build_engine(mock_sherpa_onnx, text="flush me")

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.return_value = False

    requests = [_make_start_request()] + [_make_audio_request(i) for i in range(1, 4)]
    responses = _run_stream(engine, requests)

    finals = [r for r in responses if r.hypothesis.is_final]
    assert len(finals) >= 1, "expected flush to emit is_final on stream close"
    assert finals[-1].hypothesis.text == "flush me"


def test_text_resets_after_final(mock_sherpa_onnx: MagicMock) -> None:
    """After each is_final, the next partial must start fresh."""
    engine = _build_engine(mock_sherpa_onnx, text="first")

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value

    call_counter = {"count": 0}
    first_final_sent = {"value": False}

    def _is_endpoint(_stream: object) -> bool:
        call_counter["count"] += 1
        if call_counter["count"] == 2 and not first_final_sent["value"]:
            first_final_sent["value"] = True
            return True
        return False

    mock_recognizer.is_endpoint.side_effect = _is_endpoint

    texts = {"value": "first"}

    def _get_result(_stream: object) -> str:
        return texts["value"]

    def _reset(_stream: object) -> None:
        texts["value"] = "second"

    mock_recognizer.get_result.side_effect = _get_result
    mock_recognizer.reset.side_effect = _reset

    requests = [_make_start_request()] + [_make_audio_request(i) for i in range(1, 6)]
    responses = _run_stream(engine, requests)

    finals = [r for r in responses if r.hypothesis.is_final]
    assert len(finals) >= 1

    post_final_partials = []
    saw_first_final = False
    for response in responses:
        if response.hypothesis.is_final and not saw_first_final:
            saw_first_final = True
            continue
        if saw_first_final and not response.hypothesis.is_final:
            post_final_partials.append(response.hypothesis.text)

    for text in post_final_partials:
        assert not text.startswith("first"), (
            f"partial after reset should not start with 'first': {text!r}"
        )


def test_force_finalize_via_control_message(mock_sherpa_onnx: MagicMock) -> None:
    """KIND_FINALIZE_UTTERANCE must emit is_final=True even without auto-endpoint."""
    engine = _build_engine(mock_sherpa_onnx, text="forced")

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.return_value = False

    current_text: dict[str, str] = {"value": "forced"}

    def _get_result(_stream: object) -> str:
        return current_text["value"]

    def _reset(_stream: object) -> None:
        current_text["value"] = ""

    mock_recognizer.get_result.side_effect = _get_result
    mock_recognizer.reset.side_effect = _reset

    requests = [
        _make_start_request(),
        _make_audio_request(1),
        _make_finalize_request(),
    ]
    responses = _run_stream(engine, requests)

    finals = [r for r in responses if r.hypothesis.is_final]
    assert len(finals) == 1
    assert finals[0].hypothesis.text == "forced"
    mock_recognizer.reset.assert_called()


def test_cancel_does_not_emit_final(mock_sherpa_onnx: MagicMock) -> None:
    """KIND_CANCEL must reset the stream without emitting any hypothesis."""
    engine = _build_engine(mock_sherpa_onnx, text="cancelled")

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.return_value = False
    call_count = {"n": 0}

    def _get_result(_stream: object) -> str:
        call_count["n"] += 1
        return "cancelled" if call_count["n"] <= 1 else ""

    mock_recognizer.get_result.side_effect = _get_result

    requests = [
        _make_start_request(),
        _make_audio_request(1),
        _make_cancel_request(),
    ]
    responses = _run_stream(engine, requests)

    finals = [r for r in responses if r.hypothesis.is_final]
    assert len(finals) == 0, f"cancel must not produce a final hypothesis: {finals}"


def test_empty_stream_returns_cleanly(mock_sherpa_onnx: MagicMock) -> None:
    """An empty request iterator (after start removed) must yield nothing."""
    engine = _build_engine(mock_sherpa_onnx, text="")
    session_config = _make_start_config()
    responses = list(engine.stream(iter([]), session_config))
    assert responses == []


def test_endpoint_with_empty_text_does_not_emit_final(mock_sherpa_onnx: MagicMock) -> None:
    """is_endpoint with empty text must reset the stream but not emit any hypothesis."""
    engine = _build_engine(mock_sherpa_onnx, text="")

    mock_recognizer = mock_sherpa_onnx.OnlineRecognizer.from_transducer.return_value
    mock_recognizer.is_endpoint.return_value = True

    requests = [_make_start_request(), _make_audio_request(1)]
    responses = _run_stream(engine, requests)

    assert responses == [], f"empty-text endpoint must not emit any response: {responses}"
    mock_recognizer.reset.assert_called()
