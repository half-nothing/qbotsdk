# Copyright (c) 2026-present Half_nothing.

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QQModel(BaseModel):
    """所有 API 返回对象的基类。

    每个模型都带一份 raw。
    官方新增而SDK尚未建模的字段原样留在里面, 接口改字段时可以先 model.raw["新字段"]取用
    raw 不参与序列化, 也不会带上任何请求
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)

    raw: dict[str, Any] | None = Field(alias="__raw__", default=None, exclude=True, repr=False)

    @model_validator(mode="before")
    @classmethod
    def _take_raw(cls, data: Any) -> Any:
        """把解析用的 dict 本身留一份给 raw, 不做任何序列化。"""

        if not isinstance(data, dict):
            return data
        return {**data, "__raw__": data}
