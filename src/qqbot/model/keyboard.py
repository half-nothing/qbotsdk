# Copyright (c) 2026-present Half_nothing.

"""消息按钮 (keyboard) 模型。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/msg-btn.html

两种形态:

- 申请模版后只传 `{"id": "123"}`;
- 内邀开通后传完整 `content.rows`, 最多 5 行、每行最多 5 个按钮。
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field, model_validator

from .base import QQModel


class ButtonStyle(IntEnum):
    """按钮样式, 四个取值都来自官方 `render_data.style` 表格。"""

    GREY = 0  # 灰色线框
    BLUE = 1  # 蓝色线框
    WHITE_RED_TEXT = 3  # 白色背景 + 红色字体
    BLUE_WHITE_TEXT = 4  # 蓝色背景 + 白色字体


class ButtonActionType(IntEnum):
    """按钮点击行为。"""

    LINK = 0  # 跳转: http 或小程序 scheme
    CALLBACK = 1  # 回调: data 传给后台
    COMMAND = 2  # 指令: 在输入框插入 @bot + data


class ButtonPermissionType(IntEnum):
    """按钮可操作范围。"""

    SPECIFIED_USERS = 0  # 指定用户可操作
    ADMIN_ONLY = 1  # 仅管理者可操作
    EVERYONE = 2  # 所有人可操作
    SPECIFIED_ROLES = 3  # 指定身份组可操作, 仅频道可用


class ButtonPermission(QQModel):
    """按钮权限配置。"""

    type: ButtonPermissionType = Field(alias="type")
    specify_user_ids: list[str] | None = Field(alias="specify_user_ids", default=None)
    specify_role_ids: list[str] | None = Field(alias="specify_role_ids", default=None)


class ButtonRenderData(QQModel):
    """按钮外观。"""

    label: str = Field(alias="label")
    visited_label: str = Field(alias="visited_label")
    style: ButtonStyle = Field(alias="style", default=ButtonStyle.GREY)


class ButtonAction(QQModel):
    """按钮点击后的动作。

    reply / enter / anchor 只在 COMMAND 下有效, 其中 anchor 只支持手机端单聊场景。

    unsupport_tips 在官方表格里是必填, 这里给了默认值, 避免每写一个按钮都要填一句。
    """

    type: ButtonActionType = Field(alias="type")
    data: str = Field(alias="data")
    permission: ButtonPermission = Field(alias="permission")
    unsupport_tips: str = Field(alias="unsupport_tips", default="此操作暂不支持")
    reply: bool = Field(alias="reply", default=False)
    enter: bool = Field(alias="enter", default=False)
    anchor: int | None = Field(alias="anchor", default=None)


class Button(QQModel):
    """消息底部的一个按钮。"""

    # 同一个 keyboard 消息内唯一
    id: str | None = Field(alias="id", default=None)
    render_data: ButtonRenderData = Field(alias="render_data")
    action: ButtonAction = Field(alias="action")


class KeyboardRow(QQModel):
    """一行按钮, 最多 5 个。"""

    buttons: list[Button] = Field(alias="buttons", max_length=5)


class KeyboardContent(QQModel):
    """自定义按钮内容, 最多 5 行。"""

    rows: list[KeyboardRow] = Field(alias="rows", max_length=5)


class Keyboard(QQModel):
    """消息 keyboard 字段。id 与 content 二选一。"""

    id: str | None = Field(alias="id", default=None)
    content: KeyboardContent | None = Field(alias="content", default=None)

    @model_validator(mode="after")
    def _check_shape(self) -> Keyboard:
        if (self.id is None) == (self.content is None):
            raise ValueError("keyboard needs either id or content")
        return self
