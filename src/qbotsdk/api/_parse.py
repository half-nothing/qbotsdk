# Copyright (c) 2026-present Half_nothing.

"""响应形状校验。
资源层只认对象与数组，形状不符说明接口契约变了，直接抛TransportError并带上 path。
"""

from __future__ import annotations

from qbotsdk.exceptions import TransportError


def expect_object(payload: object, path: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TransportError(
            f"expected a JSON object from {path}, got {type(payload).__name__}",
            method="GET",
            path=path,
        )
    return payload


def expect_list(payload: object, path: str) -> list[object]:
    if not isinstance(payload, list):
        raise TransportError(
            f"expected a JSON array from {path}, got {type(payload).__name__}",
            method="GET",
            path=path,
        )
    return payload
