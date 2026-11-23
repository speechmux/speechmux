"""Shared test fixtures for the sherpa-onnx plugin test suite.

sherpa-onnx is not installed in CI and requires downloaded model files. All tests
mock the sherpa_onnx module before any plugin code is imported.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


def _make_mock_recognizer(
    result_text: str = "hello",
) -> MagicMock:
    """Build a mock OnlineRecognizer that never auto-finalizes by default.

    Args:
        result_text: Text returned by get_result() (str, not .text attribute).

    Returns:
        MagicMock configured to behave like sherpa_onnx.OnlineRecognizer.
    """
    recognizer = MagicMock()
    stream = MagicMock()
    recognizer.create_stream.return_value = stream
    recognizer.get_result.return_value = result_text  # str directly (sherpa-onnx v1.12.39+)
    recognizer.is_ready.return_value = False
    recognizer.is_endpoint.return_value = False

    return recognizer


def _purge_plugin_modules() -> None:
    """Remove all cached sherpa-onnx plugin modules from sys.modules.

    Must be called both before injecting the mock (so re-import picks up the mock)
    and after each test (so the next test starts clean).
    """
    sys.modules.pop("sherpa_onnx", None)
    for key in list(sys.modules):
        if key.startswith("speechmux_plugin_stt_sherpa_onnx"):
            sys.modules.pop(key, None)


@pytest.fixture()
def mock_sherpa_onnx() -> MagicMock:
    """Inject a mock sherpa_onnx module so no model files are needed.

    Purges previously cached plugin modules before and after each test so that
    the mock takes effect even when the real sherpa_onnx package is installed.

    Yields:
        MagicMock standing in for the sherpa_onnx module.
    """
    _purge_plugin_modules()

    module = MagicMock()
    mock_recognizer = _make_mock_recognizer()
    module.OnlineRecognizer.from_transducer.return_value = mock_recognizer

    sys.modules["sherpa_onnx"] = module  # type: ignore[assignment]
    yield module

    _purge_plugin_modules()
