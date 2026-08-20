from pydantic import BaseModel, Field


class User(BaseModel):
    # union_* 字段需平台特殊申请才返回，缺省时给空串兜底
    id: str = Field(alias="id")
    username: str = Field(alias="username")
    avatar: str = Field(alias="avatar")
    bot: bool = Field(alias="bot")
    union_openid: str = Field(alias="union_openid", default="")
    union_user_account: str = Field(alias="union_user_account", default="")
