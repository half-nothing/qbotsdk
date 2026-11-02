# Copyright (c) 2026-present Half_nothing.

"""存储层共用的记录模型。"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer, RootModel

from qbotsdk.permissions.grant import Grant, PendingGrant, Role, Scope


def _coerce_grant(value: Any) -> Grant:
    if isinstance(value, Grant):
        return value
    if isinstance(value, str):
        return Grant.decode(value)
    raise TypeError("grant entries must be encoded strings")


def _serialize_grant(grant: Grant) -> str:
    return grant.encoded


GrantField = Annotated[
    Grant,
    BeforeValidator(_coerce_grant),
    PlainSerializer(_serialize_grant, return_type=str),
]

_CONFIG = ConfigDict(arbitrary_types_allowed=True)


class GrantList(RootModel[tuple[GrantField, ...]]):
    """一组授予的存储形态。"""

    model_config = _CONFIG

    def as_map(self) -> dict[str, Grant]:
        """按权限键索引, 后写的覆盖先写的。"""

        return {grant.permission: grant for grant in self.root}


class NameList(RootModel[tuple[str, ...]]):
    """一组名字的存储形态。"""

    model_config = _CONFIG


class RoleRecord(BaseModel):
    """角色在键值存储里的形态。"""

    model_config = _CONFIG

    name: str
    grants: tuple[GrantField, ...] = ()
    parents: tuple[str, ...] = ()

    @classmethod
    def of(cls, role: Role) -> RoleRecord:
        return cls(name=role.name, grants=tuple(role.grants), parents=tuple(role.parents))

    def to_role(self) -> Role:
        return Role(self.name, grants=tuple(self.grants), parents=tuple(self.parents))


class PendingRecord(BaseModel):
    """授权码在存储里的形态。"""

    permission: str
    scope: Scope = "group"
    group_openid: str | None = None

    @classmethod
    def of(cls, pending: PendingGrant) -> PendingRecord:
        return cls(
            permission=pending.permission,
            scope=pending.scope,
            group_openid=pending.group_openid,
        )

    def to_pending(self) -> PendingGrant:
        return PendingGrant(
            self.permission,
            scope=self.scope,
            group_openid=self.group_openid,
        )
