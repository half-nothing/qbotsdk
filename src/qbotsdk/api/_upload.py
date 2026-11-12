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

"""富媒体上传的家务事: 文件源、摘要、分片与合并。

调用方只给 url 或文件; 直传还是分片、摘要怎么算、分片怎么并发都在这里决定。
群聊与单聊只差路径前缀, 因此共用同一套实现。
"""

from __future__ import annotations

from asyncio import Lock, Semaphore, gather, get_running_loop, sleep, to_thread
from base64 import b64encode
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from hashlib import md5, sha1
from pathlib import Path
from typing import BinaryIO

from qbotsdk.exceptions import APIError, TransportError
from qbotsdk.model import FileType, UploadedFile, UploadPart, UploadPrepare
from qbotsdk.module import HttpClient

from ._parse import expect_object

__all__ = [
    "DIRECT_UPLOAD_LIMIT",
    "FileSource",
    "open_source",
    "upload_file_content",
    "upload_file_url",
]

# file_data 字段本身的限制, 超过就走预上传分片
DIRECT_UPLOAD_LIMIT = 5 * 1024 * 1024
# md5_10m 覆盖前 10002432 字节
_MD5_10M_BYTES = 10_002_432
_READ_BLOCK = 1024 * 1024

ProgressCallback = Callable[[int, int], None]


@dataclass(slots=True)
class FileSource:
    """待上传文件的统一视图, 支持 bytes、路径与已打开的文件对象。"""

    name: str
    size: int
    _path: Path | None = None
    _data: bytes | None = None
    _handle: BinaryIO | None = None
    _lock: Lock = field(default_factory=Lock)

    async def read_at(self, offset: int, length: int) -> bytes:
        """读指定区间; 文件对象用锁串行化 seek 与 read, 路径每次新开句柄。"""

        if self._data is not None:
            return self._data[offset : offset + length]
        if self._path is not None:
            return await to_thread(_read_path, self._path, offset, length)
        handle = self._handle
        if handle is None:
            return b""
        async with self._lock:
            return await to_thread(_read_handle, handle, offset, length)

    async def read_all(self) -> bytes:
        """整段读入内存, 只在不超过直传上限时使用。"""

        return await self.read_at(0, self.size)

    def close(self) -> None:
        """释放引用; 调用方传进来的文件句柄由调用方负责关闭。"""

        self._handle = None


def open_source(file: str | Path | BinaryIO | bytes, file_name: str | None) -> FileSource:
    """把调用方给的文件整理成可随机读取的源, 并校验体积与名字。"""

    if isinstance(file, bytes):
        source = FileSource(name=file_name or "", size=len(file), _data=file)
    elif isinstance(file, (str, Path)):
        path = Path(file)
        if not path.is_file():
            raise ValueError(f"file {path} does not exist")
        source = FileSource(name=file_name or path.name, size=path.stat().st_size, _path=path)
    else:
        if not file.seekable():
            raise ValueError("file must be seekable")
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        source = FileSource(name=file_name or _handle_name(file), size=size, _handle=file)
    if source.size == 0:
        raise ValueError("file must not be empty")
    if not source.name:
        raise ValueError("file needs file_name so the server can infer the type")
    return source


async def upload_file_url(
    http: HttpClient,
    *,
    files_path: str,
    file_type: FileType,
    url: str,
    srv_send_msg: bool,
) -> UploadedFile:
    """让服务端自己下载 URL。"""

    payload = await http.post(
        files_path,
        json={
            "file_type": int(file_type),
            "url": url,
            "srv_send_msg": srv_send_msg,
        },
    )
    return UploadedFile.model_validate(expect_object(payload, files_path))


async def upload_file_content(
    http: HttpClient,
    *,
    prefix: str,
    files_path: str,
    file_type: FileType,
    source: FileSource,
    srv_send_msg: bool,
    progress: ProgressCallback | None = None,
) -> UploadedFile:
    """按体积自动选择 base64 直传或预上传分片, 最后登记文件。"""

    if source.size <= DIRECT_UPLOAD_LIMIT:
        data = await source.read_all()
        payload = await http.post(
            files_path,
            json={
                "file_type": int(file_type),
                "file_data": b64encode(data).decode("ascii"),
                "file_name": source.name,
                "srv_send_msg": srv_send_msg,
            },
        )
        return UploadedFile.model_validate(expect_object(payload, files_path))

    prepare = await _prepare(http, prefix=prefix, file_type=file_type, source=source)
    await _upload_parts(http, prefix=prefix, source=source, prepare=prepare, progress=progress)

    config = prepare.upload_config
    payload = await _retry(
        lambda: http.post(
            files_path,
            json={
                "file_type": int(file_type),
                "file_name": source.name,
                "upload_id": prepare.upload_id,
                "srv_send_msg": srv_send_msg,
            },
        ),
        timeout=config.retry_timeout,
        delay=config.retry_delay,
    )
    return UploadedFile.model_validate(expect_object(payload, files_path))


async def _prepare(
    http: HttpClient,
    *,
    prefix: str,
    file_type: FileType,
    source: FileSource,
) -> UploadPrepare:
    """算三个摘要并换回 upload_id 与分片清单。"""

    md5, sha1, md5_10m = await _digests(source)
    path = f"{prefix}/upload_prepare"
    payload = await http.post(
        path,
        json={
            "file_type": int(file_type),
            "file_size": str(source.size),
            "file_name": source.name,
            "md5": md5,
            "sha1": sha1,
            "md5_10m": md5_10m,
        },
    )
    return UploadPrepare.model_validate(expect_object(payload, path))


async def _upload_parts(
    http: HttpClient,
    *,
    prefix: str,
    source: FileSource,
    prepare: UploadPrepare,
    progress: ProgressCallback | None,
) -> None:
    """并发上传分片; 并发上限取本地配置与服务端下发值的较小者。"""

    config = prepare.upload_config
    limit = http.options.upload_concurrency
    if config.concurrency > 0:
        limit = min(limit, config.concurrency)
    semaphore = Semaphore(max(1, limit))
    done = 0
    offset = 0

    async def one(part: UploadPart, start: int) -> None:
        nonlocal done
        length = min(part.block_size, source.size - start)
        data = await source.read_at(start, length)
        async with semaphore:
            await _retry(
                lambda: http.put_bytes(part.presigned_url, data),
                timeout=config.retry_timeout,
                delay=config.retry_delay,
            )
            await _retry(
                lambda: _finish_part(
                    http,
                    prefix=prefix,
                    upload_id=prepare.upload_id,
                    part=part,
                    length=length,
                    data=data,
                ),
                timeout=config.retry_timeout,
                delay=config.retry_delay,
            )
        done += length
        if progress is not None:
            progress(done, source.size)

    tasks: list[Awaitable[None]] = []
    for part in prepare.parts:
        tasks.append(one(part, offset))
        offset += part.block_size

    results = await gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result


async def _finish_part(
    http: HttpClient,
    *,
    prefix: str,
    upload_id: str,
    part: UploadPart,
    length: int,
    data: bytes,
) -> None:
    await http.post(
        f"{prefix}/upload_part_finish",
        json={
            "upload_id": upload_id,
            "part_index": part.index,
            "block_size": length,
            "md5": md5(data, usedforsecurity=False).hexdigest(),
        },
    )


async def _digests(source: FileSource) -> tuple[str, str, str]:
    """单遍流式算出 md5、sha1 与前 10MB 的 md5, 不从调用方接收。"""

    md5_full = md5(usedforsecurity=False)
    sha1_full = sha1(usedforsecurity=False)
    md5_10m = md5(usedforsecurity=False)
    offset = 0
    remaining = _MD5_10M_BYTES
    while offset < source.size:
        chunk = await source.read_at(offset, min(_READ_BLOCK, source.size - offset))
        if not chunk:
            break
        md5_full.update(chunk)
        sha1_full.update(chunk)
        if remaining > 0:
            head = chunk[:remaining]
            md5_10m.update(head)
            remaining -= len(head)
        offset += len(chunk)
    return md5_full.hexdigest(), sha1_full.hexdigest(), md5_10m.hexdigest()


async def _retry[T](action: Callable[[], Awaitable[T]], *, timeout: float, delay: float) -> T:
    """按服务端给的 retry_timeout 与 retry_delay 重试可重试的失败。"""

    loop = get_running_loop()
    deadline = loop.time() + max(0.0, timeout)
    while True:
        try:
            return await action()
        except (APIError, TransportError) as exc:
            if not _retryable(exc) or loop.time() + delay > deadline:
                raise
            await sleep(delay)


def _retryable(exc: APIError | TransportError) -> bool:
    if isinstance(exc, TransportError):
        return True
    return exc.retryable


def _read_path(path: Path, offset: int, length: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read(length)


def _read_handle(handle: BinaryIO, offset: int, length: int) -> bytes:
    handle.seek(offset)
    return handle.read(length)


def _handle_name(file: BinaryIO) -> str:
    name = getattr(file, "name", None)
    if isinstance(name, str):
        return Path(name).name
    return ""
