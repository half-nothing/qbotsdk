# Copyright (c) 2026-present Half_nothing.

from pydantic import BaseModel, ConfigDict


class QQModel(BaseModel):
    """所有 API 返回对象的基类"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True)
