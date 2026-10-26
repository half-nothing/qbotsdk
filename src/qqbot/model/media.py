# Copyright (c) 2026-present Half_nothing.

"""富媒体（图片 / 语音 / 视频 / 文件）模型。

参考文档：https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_files.post.html
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from .base import QQModel


class FileType(IntEnum):
    """富媒体文件类型，对应官方 file_type 字段。"""

    IMAGE = 1  # 图片, png / jpg
    VIDEO = 2  # 视频, mp4
    VOICE = 3  # 语音, silk
    FILE = 4  # 文件


class MediaInfo(QQModel):
    """发送富媒体消息时 media 字段的内容。"""

    file_info: str = Field(alias="file_info")


class UploadedFile(QQModel):
    """上传富媒体的响应对象。

    id 只在 srv_send_msg=true 时返回
    raw_url 只在分片上传合并后且 file_type 属于图片 / 视频 / 语音时返回。
    """

    file_uuid: str = Field(alias="file_uuid")
    file_info: str = Field(alias="file_info")
    ttl: int = Field(alias="ttl")
    id: str | None = Field(alias="id", default=None)
    raw_url: str | None = Field(alias="raw_url", default=None)
