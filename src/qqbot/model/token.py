# Copyright (c) 2026-present Half_nothing.

from pydantic import BaseModel, Field


class Token(BaseModel):
    # alias 钉住 QQ 接口字段名；字段名本身是 SDK 对外稳定接口
    access_token: str = Field(alias="access_token")
    expires_in: int = Field(alias="expires_in", gt=0)
