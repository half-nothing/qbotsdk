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

"""权限声明、判定与存储。"""

from .builtin import PermissionCommands as PermissionCommands
from .builtin import install_permission_commands as install_permission_commands
from .checker import PermissionChecker as PermissionChecker
from .checker import account_of as account_of
from .checker import candidates as candidates
from .grant import Grant as Grant
from .grant import PendingGrant as PendingGrant
from .grant import Role as Role
from .grant import Scope as Scope
from .node import Permission as Permission
from .node import PermissionGroup as PermissionGroup
from .node import PermissionRegistry as PermissionRegistry
from .node import permission_registry as permission_registry
from .node import validate_key as validate_key

__all__ = [
    "Grant",
    "PendingGrant",
    "Permission",
    "PermissionChecker",
    "PermissionCommands",
    "PermissionGroup",
    "PermissionRegistry",
    "Role",
    "Scope",
    "account_of",
    "candidates",
    "install_permission_commands",
    "permission_registry",
    "validate_key",
]
