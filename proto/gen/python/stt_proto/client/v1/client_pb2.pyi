from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AudioEncoding(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUDIO_ENCODING_UNSPECIFIED: _ClassVar[AudioEncoding]
    AUDIO_ENCODING_PCM_S16LE: _ClassVar[AudioEncoding]
    AUDIO_ENCODING_ALAW: _ClassVar[AudioEncoding]
    AUDIO_ENCODING_MULAW: _ClassVar[AudioEncoding]
    AUDIO_ENCODING_WAV: _ClassVar[AudioEncoding]
    AUDIO_ENCODING_OGG_OPUS: _ClassVar[AudioEncoding]

class Task(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_UNSPECIFIED: _ClassVar[Task]
    TASK_TRANSCRIBE: _ClassVar[Task]
    TASK_TRANSLATE: _ClassVar[Task]

class DecodeProfile(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DECODE_PROFILE_UNSPECIFIED: _ClassVar[DecodeProfile]
    DECODE_PROFILE_REALTIME: _ClassVar[DecodeProfile]
    DECODE_PROFILE_ACCURATE: _ClassVar[DecodeProfile]

class StreamMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STREAM_MODE_UNSPECIFIED: _ClassVar[StreamMode]
    STREAM_MODE_REALTIME: _ClassVar[StreamMode]
    STREAM_MODE_BATCH: _ClassVar[StreamMode]

class VADMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VAD_MODE_UNSPECIFIED: _ClassVar[VADMode]
    VAD_MODE_CONTINUE: _ClassVar[VADMode]
    VAD_MODE_AUTO_END: _ClassVar[VADMode]
AUDIO_ENCODING_UNSPECIFIED: AudioEncoding
AUDIO_ENCODING_PCM_S16LE: AudioEncoding
AUDIO_ENCODING_ALAW: AudioEncoding
AUDIO_ENCODING_MULAW: AudioEncoding
AUDIO_ENCODING_WAV: AudioEncoding
AUDIO_ENCODING_OGG_OPUS: AudioEncoding
TASK_UNSPECIFIED: Task
TASK_TRANSCRIBE: Task
TASK_TRANSLATE: Task
DECODE_PROFILE_UNSPECIFIED: DecodeProfile
DECODE_PROFILE_REALTIME: DecodeProfile
DECODE_PROFILE_ACCURATE: DecodeProfile
STREAM_MODE_UNSPECIFIED: StreamMode
STREAM_MODE_REALTIME: StreamMode
STREAM_MODE_BATCH: StreamMode
VAD_MODE_UNSPECIFIED: VADMode
VAD_MODE_CONTINUE: VADMode
VAD_MODE_AUTO_END: VADMode

class StreamingRecognizeRequest(_message.Message):
    __slots__ = ("session_config", "audio", "signal")
    SESSION_CONFIG_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    SIGNAL_FIELD_NUMBER: _ClassVar[int]
    session_config: SessionConfig
    audio: bytes
    signal: StreamSignal
    def __init__(self, session_config: _Optional[_Union[SessionConfig, _Mapping]] = ..., audio: _Optional[bytes] = ..., signal: _Optional[_Union[StreamSignal, _Mapping]] = ...) -> None: ...

class SessionConfig(_message.Message):
    __slots__ = ("session_id", "attributes", "audio_config", "recognition_config", "vad_config", "api_key", "stream_mode")
    class AttributesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTES_FIELD_NUMBER: _ClassVar[int]
    AUDIO_CONFIG_FIELD_NUMBER: _ClassVar[int]
    RECOGNITION_CONFIG_FIELD_NUMBER: _ClassVar[int]
    VAD_CONFIG_FIELD_NUMBER: _ClassVar[int]
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    STREAM_MODE_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    attributes: _containers.ScalarMap[str, str]
    audio_config: AudioConfig
    recognition_config: RecognitionConfig
    vad_config: VADConfig
    api_key: str
    stream_mode: StreamMode
    def __init__(self, session_id: _Optional[str] = ..., attributes: _Optional[_Mapping[str, str]] = ..., audio_config: _Optional[_Union[AudioConfig, _Mapping]] = ..., recognition_config: _Optional[_Union[RecognitionConfig, _Mapping]] = ..., vad_config: _Optional[_Union[VADConfig, _Mapping]] = ..., api_key: _Optional[str] = ..., stream_mode: _Optional[_Union[StreamMode, str]] = ...) -> None: ...

class StreamSignal(_message.Message):
    __slots__ = ("is_last",)
    IS_LAST_FIELD_NUMBER: _ClassVar[int]
    is_last: bool
    def __init__(self, is_last: bool = ...) -> None: ...

class StreamingRecognizeResponse(_message.Message):
    __slots__ = ("session_created", "result", "error")
    SESSION_CREATED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    session_created: SessionCreated
    result: RecognitionResult
    error: StreamError
    def __init__(self, session_created: _Optional[_Union[SessionCreated, _Mapping]] = ..., result: _Optional[_Union[RecognitionResult, _Mapping]] = ..., error: _Optional[_Union[StreamError, _Mapping]] = ...) -> None: ...

class SessionCreated(_message.Message):
    __slots__ = ("session_id", "token", "negotiated_audio", "negotiated_recognition", "negotiated_vad")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATED_AUDIO_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATED_RECOGNITION_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATED_VAD_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    token: str
    negotiated_audio: AudioConfig
    negotiated_recognition: RecognitionConfig
    negotiated_vad: VADConfig
    def __init__(self, session_id: _Optional[str] = ..., token: _Optional[str] = ..., negotiated_audio: _Optional[_Union[AudioConfig, _Mapping]] = ..., negotiated_recognition: _Optional[_Union[RecognitionConfig, _Mapping]] = ..., negotiated_vad: _Optional[_Union[VADConfig, _Mapping]] = ...) -> None: ...

class StreamError(_message.Message):
    __slots__ = ("error_code", "message", "retryable")
    ERROR_CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    error_code: str
    message: str
    retryable: bool
    def __init__(self, error_code: _Optional[str] = ..., message: _Optional[str] = ..., retryable: bool = ...) -> None: ...

class AudioConfig(_message.Message):
    __slots__ = ("encoding", "sample_rate", "channels")
    ENCODING_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    CHANNELS_FIELD_NUMBER: _ClassVar[int]
    encoding: AudioEncoding
    sample_rate: int
    channels: int
    def __init__(self, encoding: _Optional[_Union[AudioEncoding, str]] = ..., sample_rate: _Optional[int] = ..., channels: _Optional[int] = ...) -> None: ...

class RecognitionConfig(_message.Message):
    __slots__ = ("language_code", "task", "decode_profile", "engine_hint")
    LANGUAGE_CODE_FIELD_NUMBER: _ClassVar[int]
    TASK_FIELD_NUMBER: _ClassVar[int]
    DECODE_PROFILE_FIELD_NUMBER: _ClassVar[int]
    ENGINE_HINT_FIELD_NUMBER: _ClassVar[int]
    language_code: str
    task: Task
    decode_profile: DecodeProfile
    engine_hint: str
    def __init__(self, language_code: _Optional[str] = ..., task: _Optional[_Union[Task, str]] = ..., decode_profile: _Optional[_Union[DecodeProfile, str]] = ..., engine_hint: _Optional[str] = ...) -> None: ...

class VADConfig(_message.Message):
    __slots__ = ("mode", "silence_duration", "threshold", "threshold_override")
    MODE_FIELD_NUMBER: _ClassVar[int]
    SILENCE_DURATION_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_FIELD_NUMBER: _ClassVar[int]
    THRESHOLD_OVERRIDE_FIELD_NUMBER: _ClassVar[int]
    mode: VADMode
    silence_duration: float
    threshold: float
    threshold_override: float
    def __init__(self, mode: _Optional[_Union[VADMode, str]] = ..., silence_duration: _Optional[float] = ..., threshold: _Optional[float] = ..., threshold_override: _Optional[float] = ...) -> None: ...

class RecognitionResult(_message.Message):
    __slots__ = ("is_final", "text", "committed_text", "unstable_text", "audio_duration", "language_code", "meta", "start_sec", "end_sec")
    IS_FINAL_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    COMMITTED_TEXT_FIELD_NUMBER: _ClassVar[int]
    UNSTABLE_TEXT_FIELD_NUMBER: _ClassVar[int]
    AUDIO_DURATION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_CODE_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    START_SEC_FIELD_NUMBER: _ClassVar[int]
    END_SEC_FIELD_NUMBER: _ClassVar[int]
    is_final: bool
    text: str
    committed_text: str
    unstable_text: str
    audio_duration: float
    language_code: str
    meta: ResultMeta
    start_sec: float
    end_sec: float
    def __init__(self, is_final: bool = ..., text: _Optional[str] = ..., committed_text: _Optional[str] = ..., unstable_text: _Optional[str] = ..., audio_duration: _Optional[float] = ..., language_code: _Optional[str] = ..., meta: _Optional[_Union[ResultMeta, _Mapping]] = ..., start_sec: _Optional[float] = ..., end_sec: _Optional[float] = ...) -> None: ...

class ResultMeta(_message.Message):
    __slots__ = ("latency_sec", "real_time_factor", "utterance_index")
    LATENCY_SEC_FIELD_NUMBER: _ClassVar[int]
    REAL_TIME_FACTOR_FIELD_NUMBER: _ClassVar[int]
    UTTERANCE_INDEX_FIELD_NUMBER: _ClassVar[int]
    latency_sec: float
    real_time_factor: float
    utterance_index: int
    def __init__(self, latency_sec: _Optional[float] = ..., real_time_factor: _Optional[float] = ..., utterance_index: _Optional[int] = ...) -> None: ...
