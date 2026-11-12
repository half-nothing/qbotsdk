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

"""富媒体(图片 / 语音 / 视频 / 文件)模型。

参考文档: https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_files.post.html
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from .base import QQModel

__all__ = [
    "FileType",
    "MediaInfo",
    "UploadConfig",
    "UploadPart",
    "UploadPrepare",
    "UploadedFile",
]


class FileType(IntEnum):
    """富媒体文件类型, 对应官方 file_type 字段。"""

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


class UploadPart(QQModel):
    """预上传返回的一个分片。

    `presigned_url` 是 COS 的预签名地址, PUT 时不能带 QQ 的鉴权头。
    `block_size` 由服务端给出, 最后一片可能小于它。
    """

    index: int = Field(alias="index")
    presigned_url: str = Field(alias="presigned_url")
    block_size: int = Field(alias="block_size")


class UploadConfig(QQModel):
    """预上传返回的上传建议: 并发上限与重试节奏。"""

    concurrency: int = Field(alias="concurrency", default=1)
    retry_timeout: int = Field(alias="retry_timeout", default=300)
    retry_delay: int = Field(alias="retry_delay", default=1)


class UploadPrepare(QQModel):
    """预上传响应, 分片上传的起点。"""

    upload_id: str = Field(alias="upload_id")
    block_size: int = Field(alias="block_size")
    parts: list[UploadPart] = Field(alias="parts", default_factory=list)
    upload_config: UploadConfig = Field(alias="upload_config", default_factory=UploadConfig)
