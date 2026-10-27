# Copyright (c) 2026-present Half_nothing.

"""消息按钮 (keyboard) 模型测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qbotsdk.model import (
    Button,
    ButtonAction,
    ButtonActionType,
    ButtonPermission,
    ButtonPermissionType,
    ButtonRenderData,
    ButtonStyle,
    Keyboard,
    KeyboardContent,
    KeyboardRow,
)


def make_button(button_id: str = "1") -> Button:
    return Button(
        id=button_id,
        render_data=ButtonRenderData(label="点赞", visited_label="已赞", style=ButtonStyle.GREY),
        action=ButtonAction(
            type=ButtonActionType.CALLBACK,
            data="like",
            permission=ButtonPermission(type=ButtonPermissionType.EVERYONE),
        ),
    )


def test_keyboard_serializes_api_names() -> None:
    keyboard = Keyboard(content=KeyboardContent(rows=[KeyboardRow(buttons=[make_button()])]))
    payload = keyboard.model_dump(by_alias=True, exclude_none=True)

    assert payload == {
        "content": {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "1",
                            "render_data": {"label": "点赞", "visited_label": "已赞", "style": 0},
                            "action": {
                                "type": 1,
                                "data": "like",
                                "permission": {"type": 2},
                                # 官方表格里是必填, 模型给了默认值
                                "unsupport_tips": "此操作暂不支持",
                                "reply": False,
                                "enter": False,
                            },
                        }
                    ]
                }
            ]
        }
    }


def test_keyboard_id_or_content() -> None:
    with pytest.raises(ValidationError, match="either id or content"):
        Keyboard()

    with pytest.raises(ValidationError, match="either id or content"):
        Keyboard(id="k1", content=KeyboardContent(rows=[]))

    assert Keyboard(id="k1").id == "k1"


def test_keyboard_limits() -> None:
    rows = [KeyboardRow(buttons=[make_button(str(index))]) for index in range(5)]
    assert len(KeyboardContent(rows=rows).rows) == 5

    with pytest.raises(ValidationError):
        KeyboardContent(rows=[*rows, KeyboardRow(buttons=[make_button("6")])])

    with pytest.raises(ValidationError):
        KeyboardRow(buttons=[make_button(str(index)) for index in range(6)])
