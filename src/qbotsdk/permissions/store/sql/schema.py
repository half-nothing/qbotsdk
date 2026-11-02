# Copyright (c) 2026-present Half_nothing.

"""SQL 存储的表结构。"""

from __future__ import annotations

from sqlalchemy import Column, Float, MetaData, String, Table, Text


class PermissionSchema:
    """一组带前缀的权限表。"""

    __slots__ = ("grants", "metadata", "pending", "roles")

    def __init__(self, prefix: str = "qbotsdk_") -> None:
        if not prefix:
            raise ValueError("table_prefix must not be empty")
        self.metadata = MetaData()
        self.grants = Table(
            f"{prefix}permission_grants",
            self.metadata,
            Column("principal", String(191), primary_key=True),
            Column("permissions", Text, nullable=False),
            Column("roles", Text, nullable=False),
        )
        self.roles = Table(
            f"{prefix}permission_roles",
            self.metadata,
            Column("name", String(191), primary_key=True),
            Column("parents", Text, nullable=False),
            Column("permissions", Text, nullable=False),
        )
        self.pending = Table(
            f"{prefix}permission_pending",
            self.metadata,
            Column("code", String(191), primary_key=True),
            Column("permission", String(191), nullable=False),
            Column("scope", String(16), nullable=False),
            Column("group_openid", String(191), nullable=True),
            Column("expires_at", Float, nullable=False),
        )
