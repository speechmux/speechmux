from stt_proto.common.v1 import common_pb2 as _common_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Task(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_UNSPECIFIED: _ClassVar[Task]
    TASK_TRANSCRIBE: _ClassVar[Task]
    TASK_TRANSLATE: _ClassVar[Task]
TASK_UNSPECIFIED: Task
TASK_TRANSCRIBE: Task
TASK_TRANSLATE: Task

class TranscribeRequest(_message.Message):
    __slots__ = ("request_id", "session_id", "audio_data", "sample_rate", "language_code", "task", "decode_options", "is_final", "is_partial")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    AUDIO_DATA_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_CODE_FIELD_NUMBER: _ClassVar[int]
    TASK_FIELD_NUMBER: _ClassVar[int]
    DECODE_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    IS_FINAL_FIELD_NUMBER: _ClassVar[int]
    IS_PARTIAL_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    session_id: str
    audio_data: bytes
    sample_rate: int
    language_code: str
    task: Task
    decode_options: DecodeOptions
    is_final: bool
    is_partial: bool
    def __init__(self, request_id: _Optional[str] = ..., session_id: _Optional[str] = ..., audio_data: _Optional[bytes] = ..., sample_rate: _Optional[int] = ..., language_code: _Optional[str] = ..., task: _Optional[_Union[Task, str]] = ..., decode_options: _Optional[_Union[DecodeOptions, _Mapping]] = ..., is_final: bool = ..., is_partial: bool = ...) -> None: ...

class TranscribeResponse(_message.Message):
    __slots__ = ("request_id", "session_id", "text", "language_code", "inference_sec", "audio_duration_sec", "real_time_factor", "segments", "no_speech_detected", "error_code")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_CODE_FIELD_NUMBER: _ClassVar[int]
    INFERENCE_SEC_FIELD_NUMBER: _ClassVar[int]
    AUDIO_DURATION_SEC_FIELD_NUMBER: _ClassVar[int]
    REAL_TIME_FACTOR_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_FIELD_NUMBER: _ClassVar[int]
    NO_SPEECH_DETECTED_FIELD_NUMBER: _ClassVar[int]
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    session_id: str
    text: str
    language_code: str
    inference_sec: float
    audio_duration_sec: float
    real_time_factor: float
    segments: _containers.RepeatedCompositeFieldContainer[Segment]
    no_speech_detected: bool
    error_code: _common_pb2.PluginErrorCode
    def __init__(self, request_id: _Optional[str] = ..., session_id: _Optional[str] = ..., text: _Optional[str] = ..., language_code: _Optional[str] = ..., inference_sec: _Optional[float] = ..., audio_duration_sec: _Optional[float] = ..., real_time_factor: _Optional[float] = ..., segments: _Optional[_Iterable[_Union[Segment, _Mapping]]] = ..., no_speech_detected: bool = ..., error_code: _Optional[_Union[_common_pb2.PluginErrorCode, str]] = ...) -> None: ...

class DecodeOptions(_message.Message):
    __slots__ = ("beam_size", "best_of", "temperature", "length_penalty", "without_timestamps", "compression_ratio_threshold", "no_speech_threshold", "log_prob_threshold")
    BEAM_SIZE_FIELD_NUMBER: _ClassVar[int]
    BEST_OF_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    LENGTH_PENALTY_FIELD_NUMBER: _ClassVar[int]
    WITHOUT_TIMESTAMPS_FIELD_NUMBER: _ClassVar[int]
    COMPRESSION_RATIO_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    NO_SPEECH_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    LOG_PROB_THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    beam_size: int
    best_of: int
    temperature: float
    length_penalty: float
    without_timestamps: bool
    compression_ratio_threshold: float
    no_speech_threshold: float
    log_prob_threshold: float
    def __init__(self, beam_size: _Optional[int] = ..., best_of: _Optional[int] = ..., temperature: _Optional[float] = ..., length_penalty: _Optional[float] = ..., without_timestamps: bool = ..., compression_ratio_threshold: _Optional[float] = ..., no_speech_threshold: _Optional[float] = ..., log_prob_threshold: _Optional[float] = ...) -> None: ...

class Segment(_message.Message):
    __slots__ = ("text", "start_sec", "end_sec", "avg_log_prob", "no_speech_prob")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    START_SEC_FIELD_NUMBER: _ClassVar[int]
    END_SEC_FIELD_NUMBER: _ClassVar[int]
    AVG_LOG_PROB_FIELD_NUMBER: _ClassVar[int]
    NO_SPEECH_PROB_FIELD_NUMBER: _ClassVar[int]
    text: str
    start_sec: float
    end_sec: float
    avg_log_prob: float
    no_speech_prob: float
    def __init__(self, text: _Optional[str] = ..., start_sec: _Optional[float] = ..., end_sec: _Optional[float] = ..., avg_log_prob: _Optional[float] = ..., no_speech_prob: _Optional[float] = ...) -> None: ...

class InferenceCapabilities(_message.Message):
    __slots__ = ("engine_name", "model_size", "device", "supported_languages", "max_concurrent_requests", "supports_partial_decode")
    ENGINE_NAME_FIELD_NUMBER: _ClassVar[int]
    MODEL_SIZE_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_LANGUAGES_FIELD_NUMBER: _ClassVar[int]
    MAX_CONCURRENT_REQUESTS_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_PARTIAL_DECODE_FIELD_NUMBER: _ClassVar[int]
    engine_name: str
    model_size: str
    device: str
    supported_languages: _containers.RepeatedScalarFieldContainer[str]
    max_concurrent_requests: int
    supports_partial_decode: bool
    def __init__(self, engine_name: _Optional[str] = ..., model_size: _Optional[str] = ..., device: _Optional[str] = ..., supported_languages: _Optional[_Iterable[str]] = ..., max_concurrent_requests: _Optional[int] = ..., supports_partial_decode: bool = ...) -> None: ...
