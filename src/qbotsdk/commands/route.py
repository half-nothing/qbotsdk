# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""路由条目, 事件类型、触发器与签名校验。

一条路由由三个部分组成, 分别是事件类型、触发器和处理器。
事件类型决定这条路由在哪些事件上可见。
触发器决定一条事件能否命中它。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from inspect import Parameter, Signature, iscoroutinefunction, signature
from typing import TYPE_CHECKING, Any, Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from qbotsdk.model import EventModel

from .context import Context
from .convert import DEFAULT_CONVERTERS, Converter, accepts_annotation
from .reply import Reply
from .template import PathTemplate

if TYPE_CHECKING:
    from .router import Guard, Middleware

__all__ = [
    "AckPolicy",
    "Binding",
    "CallbackHandler",
    "CommandHandler",
    "PayloadTrigger",
    "Route",
    "TextTrigger",
    "Trigger",
    "action_of",
    "build_binding",
    "check_callback_handler",
    "event_types",
]

CommandHandler = Callable[..., Awaitable[object]]
CallbackHandler = Callable[..., Awaitable[object]]

AckPolicy = Literal["pre", "post", "none"]

EventType = type[EventModel]

Spec = EventType | Iterable[EventType]


@dataclass(frozen=True, slots=True)
class Binding:
    """handler 签名与模板、选项的对照结果, 注册期算一次。"""

    ctx_param: str | None
    kwargs: tuple[str, ...] = ()
    argv_param: str | None = None
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TextTrigger:
    """文本触发器: 命令模板与是否绑定参数。"""

    template: PathTemplate
    bind_args: bool = True

    @property
    def name(self) -> str:
        return self.template.source


@dataclass(frozen=True, slots=True)
class PayloadTrigger:
    """按钮触发器: 载荷模型、字面量或前缀。"""

    key: str
    model: type[BaseModel] | None = None
    prefix: bool = False


Trigger = TextTrigger | PayloadTrigger


@dataclass(frozen=True, slots=True)
class Route:
    """一条注册好的路由。"""

    on: frozenset[EventType]
    trigger: Trigger
    handler: CommandHandler | CallbackHandler
    binding: Binding | None = None
    permission: str | None = None
    description: str = ""
    usage: str | None = None
    hidden: bool = False
    ack: AckPolicy = "pre"
    mention: bool | None = None
    options: Mapping[str, type] = field(default_factory=dict)
    guards: tuple[Guard, ...] = ()
    middlewares: tuple[Middleware, ...] = ()

    @property
    def name(self) -> str:
        """文本命令的完整路径, 或按钮触发器的键。"""

        return self.trigger.name if isinstance(self.trigger, TextTrigger) else self.trigger.key

    @property
    def is_command(self) -> bool:
        return isinstance(self.trigger, TextTrigger)


def event_types(spec: Spec, *, parameter: str = "on") -> frozenset[EventType]:
    """把 `on=` 归一成事件类型集合, 并校验它确实是事件模型。"""

    items: tuple[object, ...] = (spec,) if isinstance(spec, type) else tuple(spec)
    if not items:
        raise TypeError(f"{parameter} must name at least one event type")
    checked: list[EventType] = []
    for item in items:
        if not (isinstance(item, type) and issubclass(item, EventModel)):
            raise TypeError(f"{parameter} must be an event model class, got {item!r}")
        checked.append(item)
    return frozenset(checked)


def _callable_hints(handler: Callable[..., object]) -> dict[str, Any]:
    try:
        return get_type_hints(handler)
    except Exception:
        return {}


def _is_context(annotation: object) -> bool:
    if annotation is Parameter.empty:
        return False
    if isinstance(annotation, str):
        return annotation == "Context" or annotation.endswith(".Context")
    return isinstance(annotation, type) and issubclass(annotation, Context)


def _is_string_list(annotation: object) -> bool:
    if annotation is Parameter.empty:
        return True
    if isinstance(annotation, str):
        return annotation in {"list[str]", "List[str]", "Sequence[str]"}
    return get_origin(annotation) is list and get_args(annotation) == (str,)


def _check_callable(handler: Callable[..., object]) -> list[Parameter]:
    if not iscoroutinefunction(handler):
        raise TypeError("command handlers must be an async function")
    sig = signature(handler)
    _check_return_type(sig.return_annotation)
    parameters = list(sig.parameters.values())
    for parameter in parameters:
        if parameter.kind is Parameter.POSITIONAL_ONLY:
            raise TypeError(f"parameter {parameter.name!r} must not be positional-only")
        if parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            raise TypeError(f"parameter {parameter.name!r} is a variadic parameter")
    return parameters


def _check_return_type(annotation: object) -> None:
    """handler 只允许返回 :class:`Reply` 。"""

    if annotation is Signature.empty:
        return
    if annotation is Reply:
        return
    # 检查被引号包裹的Reply
    if isinstance(annotation, str) and annotation.rsplit(".", 1)[-1] == "Reply":
        return
    raise TypeError(f"handlers must be annotated to return Reply, got {annotation!r}")


def build_binding(
    handler: CommandHandler,
    template: PathTemplate,
    *,
    bind_args: bool,
    converters: Mapping[str, type[Converter]] | None = None,
    options: Mapping[str, type] | None = None,
) -> Binding:
    """把 handler 签名与模板、选项对照好, 不合规直接抛 `TypeError`。"""

    if converters is None:
        converters = DEFAULT_CONVERTERS
    parameters = _check_callable(handler)
    hints = _callable_hints(handler)

    ctx_params: list[str] = []
    others: list[Parameter] = []
    for parameter in parameters:
        annotation = hints.get(parameter.name, parameter.annotation)
        if _is_context(annotation):
            ctx_params.append(parameter.name)
        else:
            others.append(parameter)
    if len(ctx_params) > 1:
        raise TypeError("only one context parameter is allowed")
    ctx_param = ctx_params[0] if ctx_params else None

    if not bind_args:
        if len(others) != 1:
            raise TypeError("with bind_args=False the handler must take exactly one argv parameter")
        argv = others[0]
        annotation = hints.get(argv.name, argv.annotation)
        if not _is_string_list(annotation):
            raise TypeError(
                f"parameter {argv.name!r} of a bind_args=False handler must be list[str]"
            )
        return Binding(
            ctx_param=ctx_param,
            argv_param=argv.name,
            options=_bind_options(others, options or {}),
        )

    named = {parameter.name: parameter for parameter in others}
    names = {placeholder.name: placeholder for placeholder in template.placeholders}

    for parameter in others:
        if parameter.name in names or parameter.name in _option_names(options or {}):
            continue
        if parameter.default is Parameter.empty:
            raise TypeError(f"parameter {parameter.name!r} is not defined in the command template")

    for name, placeholder in names.items():
        if name not in named:
            raise TypeError(f"template placeholder {name!r} has no matching parameter")
        annotation = hints.get(name, named[name].annotation)
        if annotation is Parameter.empty:
            continue
        if placeholder.converter == "rest":
            if not _is_string_sequence(annotation):
                raise TypeError(f"parameter {name!r} of a rest placeholder must be tuple[str, ...]")
            continue
        converter = converters[placeholder.converter]
        if not accepts_annotation(converter, annotation):
            raise TypeError(
                f"converter {placeholder.converter!r} for {name!r} "
                f"does not match annotation {annotation!r}"
            )

    kwargs = tuple(placeholder.name for placeholder in template.placeholders)
    return Binding(
        ctx_param=ctx_param,
        kwargs=kwargs,
        options=_bind_options(others, options or {}),
    )


def _is_string_sequence(annotation: object) -> bool:
    if isinstance(annotation, str):
        return annotation in {"tuple[str, ...]", "Sequence[str]", "list[str]", "List[str]"}
    return (
        get_origin(annotation) in (tuple, list) and get_args(annotation) == (str, Ellipsis)
    ) or (get_origin(annotation) is list and get_args(annotation) == (str,))


def _option_names(options: Mapping[str, type]) -> set[str]:
    names: set[str] = set()
    for name in options:
        names.add(name)
        names.add(f"{name}_")
    return names


def _bind_options(
    parameters: list[Parameter], options: Mapping[str, type]
) -> tuple[tuple[str, str], ...]:
    """把声明的选项按名字绑到形参, `global` 可以写成 `global_`。"""

    by_name = {parameter.name: parameter for parameter in parameters}
    pairs: list[tuple[str, str]] = []
    for name, kind in options.items():
        if not name or not name.replace("-", "").isidentifier():
            raise TypeError(f"option name {name!r} is not a valid identifier")
        if kind not in (bool, int, float, str):
            raise TypeError(f"option {name!r} must be bool, int, float or str")
        param = by_name.get(name) or by_name.get(f"{name}_")
        if param is None:
            raise TypeError(f"option {name!r} has no matching parameter")
        if kind is not bool and param.default is Parameter.empty:
            raise TypeError(f"option {name!r} must have a default value")
        pairs.append((name, param.name))
    return tuple(pairs)


def check_callback_handler(handler: CallbackHandler) -> None:
    """回调 handler 只要求是协程函数, 签名由路由器按路由类型拼。"""

    _ = _check_callable(handler)


def action_of(model: type[BaseModel]) -> str:
    """从载荷模型的 `action` 字段取出唯一字面量。"""

    field_info = model.model_fields.get("action")
    if field_info is None:
        raise ValueError("callback payload must declare an action field")
    annotation = field_info.annotation
    if get_origin(annotation) is Literal:
        args = get_args(annotation)
        if len(args) == 1 and isinstance(args[0], str):
            return args[0]
    raise ValueError("callback payload action must be a single Literal string")
