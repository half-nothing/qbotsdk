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

"""关系库存储。"""

from __future__ import annotations

from .backend import SqlBackend as SqlBackend
from .base import SqlPermissionStorage as SqlPermissionStorage
from .mysql import MysqlPermissionStorage as MysqlPermissionStorage
from .postgres import PostgresPermissionStorage as PostgresPermissionStorage
from .schema import PermissionSchema as PermissionSchema
from .sqlite import SqlitePermissionStorage as SqlitePermissionStorage

__all__ = [
    "MysqlPermissionStorage",
    "PermissionSchema",
    "PostgresPermissionStorage",
    "SqlBackend",
    "SqlPermissionStorage",
    "SqlitePermissionStorage",
]
