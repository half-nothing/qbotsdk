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

"""响应形状校验。
资源层只认对象与数组, 形状不符说明接口契约变了, 直接抛TransportError并带上 path。
"""

from __future__ import annotations

from qbotsdk.exceptions import TransportError

__all__ = ["expect_list", "expect_object"]


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
