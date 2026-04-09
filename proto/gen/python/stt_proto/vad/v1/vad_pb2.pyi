from stt_proto.common.v1 import common_pb2 as _common_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class VADRequest(_message.Message):
    __slots__ = ("pcm_data", "sample_rate", "sequence_number", "session_start", "session_end")
    PCM_DATA_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_NUMBER_FIELD_NUMBER: _ClassVar[int]
    SESSION_START_FIELD_NUMBER: _ClassVar[int]
    SESSION_END_FIELD_NUMBER: _ClassVar[int]
    pcm_data: bytes
    sample_rate: int
    sequence_number: int
    session_start: SessionStart
    session_end: SessionEnd
    def __init__(self, pcm_data: _Optional[bytes] = ..., sample_rate: _Optional[int] = ..., sequence_number: _Optional[int] = ..., session_start: _Optional[_Union[SessionStart, _Mapping]] = ..., session_end: _Optional[_Union[SessionEnd, _Mapping]] = ...) -> None: ...

class SessionStart(_message.Message):
    __slots__ = ("session_id", "threshold", "sample_rate")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    threshold: float
    sample_rate: int
    def __init__(self, session_id: _Optional[str] = ..., threshold: _Optional[float] = ..., sample_rate: _Optional[int] = ...) -> None: ...

class SessionEnd(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class VADResponse(_message.Message):
    __slots__ = ("is_speech", "speech_probability", "chunk_rms", "chunk_duration_sec", "sequence_number", "error_code")
    IS_SPEECH_FIELD_NUMBER: _ClassVar[int]
    SPEECH_PROBABILITY_FIELD_NUMBER: _ClassVar[int]
    CHUNK_RMS_FIELD_NUMBER: _ClassVar[int]
    CHUNK_DURATION_SEC_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_NUMBER_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    is_speech: bool
    speech_probability: float
    chunk_rms: float
    chunk_duration_sec: float
    sequence_number: int
    error_code: _common_pb2.PluginErrorCode
    def __init__(self, is_speech: bool = ..., speech_probability: _Optional[float] = ..., chunk_rms: _Optional[float] = ..., chunk_duration_sec: _Optional[float] = ..., sequence_number: _Optional[int] = ..., error_code: _Optional[_Union[_common_pb2.PluginErrorCode, str]] = ...) -> None: ...

class VADCapabilities(_message.Message):
    __slots__ = ("model_name", "max_concurrent_sessions", "optimal_frame_ms", "supported_sample_rates")
    MODEL_NAME_FIELD_NUMBER: _ClassVar[int]
    MAX_CONCURRENT_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    OPTIMAL_FRAME_MS_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_SAMPLE_RATES_FIELD_NUMBER: _ClassVar[int]
    model_name: str
    max_concurrent_sessions: int
    optimal_frame_ms: int
    supported_sample_rates: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, model_name: _Optional[str] = ..., max_concurrent_sessions: _Optional[int] = ..., optimal_frame_ms: _Optional[int] = ..., supported_sample_rates: _Optional[_Iterable[int]] = ...) -> None: ...
