# Copyright (c) 2026-present Half_nothing.

"""权限声明、授予、判定与内存存储的测试。"""

from __future__ import annotations

import pytest

from qbotsdk.permissions import (
    Grant,
    PendingGrant,
    Permission,
    PermissionChecker,
    PermissionGroup,
    PermissionRegistry,
    Role,
    account_of,
    candidates,
    validate_key,
)
from qbotsdk.permissions.store import MemoryPermissionStorage


class DemoGroup(PermissionGroup, namespace="demo"):
    STOP = Permission("stop", "停止")
    ALL = Permission.wildcard("全部")


class NestedGroup(PermissionGroup, namespace="nested.admin"):
    PUSH = Permission("push")


def test_group_binds_permissions_to_its_namespace() -> None:
    assert DemoGroup.STOP.key == "demo.stop"
    assert DemoGroup.ALL.key == "demo.*"
    assert NestedGroup.PUSH.key == "nested.admin.push"


def test_permission_without_namespace_keeps_its_name() -> None:
    assert Permission("custom.node").key == "custom.node"


@pytest.mark.parametrize(
    "key",
    ["", "A B", "A..B", "*.A", "A.*.B", "1bad", "A.<B>"],
)
def test_invalid_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValueError):
        validate_key(key)


def test_registry_rejects_duplicate_declarations() -> None:
    registry = PermissionRegistry()
    registry.register(Permission("a.b"))

    with pytest.raises(ValueError, match="already declared"):
        registry.register(Permission("a.b"))


def test_registry_lists_and_requires_keys() -> None:
    registry = PermissionRegistry()
    first = Permission("a.one")
    registry.register(first)

    assert "a.one" in registry
    assert registry.require("a.one") is first
    assert registry.keys() == ("a.one",)
    with pytest.raises(ValueError, match="is not declared"):
        registry.require("missing")


def test_grant_encoding_round_trips() -> None:
    allow = Grant("server.stop")
    deny = Grant("server.stop", allow=False)

    assert allow.encoded == "server.stop"
    assert deny.encoded == "-server.stop"
    assert Grant.decode("-server.stop") == deny
    assert Grant.decode("server.stop") == allow
    with pytest.raises(ValueError, match="must not be empty"):
        Grant.decode("")
    with pytest.raises(ValueError, match="must not be empty"):
        Grant("")


def test_pending_grant_requires_group_for_group_scope() -> None:
    with pytest.raises(ValueError, match="needs group_openid"):
        PendingGrant("demo.stop")

    assert PendingGrant("demo.stop", group_openid="g").scope == "group"
    assert PendingGrant("demo.stop", scope="global").group_openid is None


def test_account_of_derives_user_keys() -> None:
    assert account_of("group:g1:m1") == "user:m1"
    assert account_of("c2c:u1") == "user:u1"
    assert account_of("guild:g1:u1") is None


def test_candidates_walk_from_specific_to_broad() -> None:
    assert candidates("server.admin.stop") == (
        "server.admin.stop",
        "server.admin.*",
        "server.*",
        "*",
    )
    assert candidates("server.*") == ("server.*", "*")
    assert candidates("*") == ("*",)


async def test_denied_when_nothing_is_granted() -> None:
    checker = PermissionChecker(MemoryPermissionStorage())

    assert await checker.allows("group:g1:m1", "demo.stop") is False


async def test_specific_allow_beats_broader_deny() -> None:
    store = MemoryPermissionStorage()
    await store.grant("group:g1:m1", Grant("demo.stop"))
    await store.grant("group:g1:m1", Grant("demo.*", allow=False))

    assert await PermissionChecker(store).allows("group:g1:m1", "demo.stop") is True


async def test_specific_deny_beats_broader_allow() -> None:
    store = MemoryPermissionStorage()
    await store.grant("group:g1:m1", Grant("demo.*"))
    await store.grant("group:g1:m1", Grant("demo.stop", allow=False))

    assert await PermissionChecker(store).allows("group:g1:m1", "demo.stop") is False


async def test_account_grants_apply_across_groups_and_c2c() -> None:
    store = MemoryPermissionStorage()
    await store.grant("user:m1", Grant("demo.stop"))
    checker = PermissionChecker(store)

    assert await checker.allows("group:g1:m1", "demo.stop") is True
    assert await checker.allows("c2c:m1", "demo.stop") is True
    assert await checker.allows("group:g2:m2", "demo.stop") is False


async def test_scene_scope_is_checked_before_account_scope() -> None:
    store = MemoryPermissionStorage()
    await store.grant("group:g1:m1", Grant("demo.stop", allow=False))
    await store.grant("user:m1", Grant("demo.stop"))

    assert await PermissionChecker(store).allows("group:g1:m1", "demo.stop") is False


async def test_roles_and_parents_expand_recursively() -> None:
    store = MemoryPermissionStorage()
    await store.save_role(Role("base", grants=(Grant("demo.stop"),)))
    await store.save_role(Role("admin", grants=(Grant("demo.start"),), parents=("base",)))
    await store.assign("group:g1:m1", "admin")

    checker = PermissionChecker(store)

    assert await checker.allows("group:g1:m1", "demo.stop") is True
    assert await checker.allows("group:g1:m1", "demo.start") is True
    assert await checker.allows("group:g1:m1", "demo.other") is False


async def test_role_cycles_terminate() -> None:
    store = MemoryPermissionStorage()
    await store.save_role(Role("a", parents=("b",)))
    await store.save_role(Role("b", parents=("a",), grants=(Grant("demo.stop"),)))
    await store.assign("group:g1:m1", "a")

    assert await PermissionChecker(store).allows("group:g1:m1", "demo.stop") is True


async def test_empty_permission_key_is_rejected() -> None:
    checker = PermissionChecker(MemoryPermissionStorage())

    with pytest.raises(ValueError, match="permission must have a key"):
        await checker.allows("group:g1:m1", "")
