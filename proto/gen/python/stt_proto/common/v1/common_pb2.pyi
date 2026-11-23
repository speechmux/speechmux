from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PluginState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PLUGIN_STATE_UNSPECIFIED: _ClassVar[PluginState]
    PLUGIN_STATE_LOADING: _ClassVar[PluginState]
    PLUGIN_STATE_READY: _ClassVar[PluginState]
    PLUGIN_STATE_DRAINING: _ClassVar[PluginState]
    PLUGIN_STATE_ERROR: _ClassVar[PluginState]

class PluginErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PLUGIN_ERROR_UNSPECIFIED: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_MODEL_LOADING: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_MODEL_OOM: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_INVALID_AUDIO: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_INFERENCE_FAILED: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_SESSION_NOT_FOUND: _ClassVar[PluginErrorCode]
    PLUGIN_ERROR_CAPACITY_FULL: _ClassVar[PluginErrorCode]
PLUGIN_STATE_UNSPECIFIED: PluginState
PLUGIN_STATE_LOADING: PluginState
PLUGIN_STATE_READY: PluginState
PLUGIN_STATE_DRAINING: PluginState
PLUGIN_STATE_ERROR: PluginState
PLUGIN_ERROR_UNSPECIFIED: PluginErrorCode
PLUGIN_ERROR_MODEL_LOADING: PluginErrorCode
PLUGIN_ERROR_MODEL_OOM: PluginErrorCode
PLUGIN_ERROR_INVALID_AUDIO: PluginErrorCode
PLUGIN_ERROR_INFERENCE_FAILED: PluginErrorCode
PLUGIN_ERROR_SESSION_NOT_FOUND: PluginErrorCode
PLUGIN_ERROR_CAPACITY_FULL: PluginErrorCode

class PluginHealthStatus(_message.Message):
    __slots__ = ("state", "active", "message", "last_error")
    STATE_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    LAST_ERROR_FIELD_NUMBER: _ClassVar[int]
    state: PluginState
    active: int
    message: str
    last_error: PluginErrorCode
    def __init__(self, state: _Optional[_Union[PluginState, str]] = ..., active: _Optional[int] = ..., message: _Optional[str] = ..., last_error: _Optional[_Union[PluginErrorCode, str]] = ...) -> None: ...
