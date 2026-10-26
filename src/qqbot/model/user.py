# Copyright (c) 2026-present Half_nothing.

from pydantic import BaseModel, Field


class User(BaseModel):
    id: str = Field(alias="id")
    username: str = Field(alias="username")
    avatar: str = Field(alias="avatar")
    # 不知为何, 虽然官方文档里面写了bot这个字段, 但API返回值里面没有
    # 所以给bot字段默认值True, 你都用这个库了怎么可能不是机器人
    bot: bool = Field(alias="bot", default=True)
    union_openid: str = Field(alias="union_openid", default="")
    union_user_account: str = Field(alias="union_user_account", default="")
    welcome_msg: str = Field(alias="welcome_msg", default="")
