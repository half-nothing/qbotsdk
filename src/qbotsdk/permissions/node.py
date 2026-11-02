# Copyright (c) 2026-present Half_nothing.

"""权限节点声明, 显式命名空间加名字。"""

from __future__ import annotations

from re import compile
from typing import ClassVar, Final

_SEGMENT = compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def validate_key(key: str) -> None:
    """校验权限键, 以点分段、不允许空段, `*` 只能出现在末段。"""

    if not key:
        raise ValueError("permission key must not be empty")
    if any(char.isspace() for char in key):
        raise ValueError("permission key must not contain whitespace")
    segments = key.split(".")
    for index, segment in enumerate(segments):
        if not segment:
            raise ValueError(f"permission key {key!r} contains an empty segment")
        if segment == "*":
            if index != len(segments) - 1:
                raise ValueError(f"permission key {key!r} may only end with '*'")
            continue
        if not _SEGMENT.match(segment):
            raise ValueError(f"permission key segment {segment!r} is not a valid name")


class Permission:
    """一个权限节点。"""

    __slots__ = ("_key", "_name", "description")

    def __init__(self, name: str, description: str = "") -> None:
        validate_key(name)
        self._name = name
        self._key: str | None = None
        self.description = description

    @classmethod
    def wildcard(cls, description: str = "") -> Permission:
        """声明一个 命名空间.* 通配节点。"""

        return cls("*", description)

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        """带命名空间的完整键, 未绑定命名空间时就是名字本身。"""

        return self._key if self._key is not None else self._name

    def __repr__(self) -> str:
        return f"Permission({self.key!r})"

    def __str__(self) -> str:
        return self.key

    def _bind(self, namespace: str) -> None:
        namespace = namespace.strip(".")
        if namespace:
            validate_key(namespace)
        self._key = f"{namespace}.{self._name}" if namespace else self._name
        permission_registry.register(self)


class PermissionGroup:
    """权限命名空间, 类体内的 Permission 会按 namespace 绑定。"""

    namespace: ClassVar[str] = ""

    def __init_subclass__(cls, *, namespace: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if namespace is not None:
            cls.namespace = namespace.strip(".")
        elif not cls.namespace:
            cls.namespace = ""
        for value in vars(cls).values():
            if isinstance(value, Permission):
                # noinspection PyProtectedMember
                value._bind(cls.namespace)


class PermissionRegistry:
    """已声明权限键的登记表, 供严格模式与回显使用。"""

    __slots__ = ("_keys",)

    def __init__(self) -> None:
        self._keys: dict[str, Permission] = {}

    def register(self, permission: Permission) -> None:
        existing = self._keys.get(permission.key)
        if existing is not None and existing is not permission:
            raise ValueError(f"permission {permission.key!r} is already declared")
        self._keys[permission.key] = permission

    def require(self, key: str) -> Permission:
        permission = self._keys.get(key)
        if permission is None:
            raise ValueError(f"permission {key!r} is not declared")
        return permission

    def get(self, key: str) -> Permission | None:
        return self._keys.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._keys

    def __len__(self) -> int:
        return len(self._keys)


permission_registry: Final[PermissionRegistry] = PermissionRegistry()
