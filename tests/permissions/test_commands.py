# Copyright (c) 2026-present Half_nothing.

"""内置权限管理命令的端到端测试。"""

from __future__ import annotations

from qbotsdk.commands import Router
from qbotsdk.permissions import (
    Grant,
    MemoryPermissionStorage,
    PermissionChecker,
    Role,
    install_permission_commands,
)
from tests.commands.support import FakeApi, c2c_event, group_event

OWNER = "group:group-1:member-1"


async def build() -> tuple[Router, MemoryPermissionStorage]:
    store = MemoryPermissionStorage()
    router = Router(checker=PermissionChecker(store))
    install_permission_commands(router, store)
    await store.grant(OWNER, Grant("permission.*"))
    return router, store


async def reply_of(event: object) -> str:
    assert isinstance(event.api, FakeApi)  # type: ignore[attr-defined]
    return str(event.api.group.calls[0]["content"])  # type: ignore[attr-defined]


async def test_show_is_open_to_the_caller() -> None:
    store = MemoryPermissionStorage()
    router = Router(checker=PermissionChecker(store))
    install_permission_commands(router, store)
    event = group_event("/permission show")

    await router.handle(event)

    assert await reply_of(event) == "No permissions are granted."


async def test_show_lists_granted_keys() -> None:
    router, _ = await build()
    event = group_event("/permission show")

    await router.handle(event)

    assert await reply_of(event) == (
        "Your permissions:\n"
        "group:group-1:member-1\n"
        "  scope: group group-1\n"
        "  direct: permission.*\n"
        "  roles: none\n"
        "user:member-1\n"
        "  scope: user, applies in every scene\n"
        "  direct: none\n"
        "  roles: none"
    )


async def test_show_describes_roles_and_their_grants() -> None:
    router, store = await build()
    await store.save_role(
        Role(
            "admin",
            grants=(Grant("demo.*"), Grant("demo.admin", allow=False)),
            parents=("base",),
        )
    )
    await store.save_role(Role("base", grants=(Grant("demo.ping"),)))
    await store.assign("group:group-1:member-2", "admin")
    event = group_event("/permission show <@member-2>")

    await router.handle(event)

    assert await reply_of(event) == (
        "group:group-1:member-2\n"
        "  scope: group group-1\n"
        "  direct: none\n"
        "  roles:\n"
        "    admin\n"
        "      grants: demo.*, -demo.admin\n"
        "      inherits: base\n"
        "user:member-2\n"
        "  scope: user, applies in every scene\n"
        "  direct: none\n"
        "  roles: none"
    )


async def test_show_marks_a_missing_role_definition() -> None:
    router, store = await build()
    await store.assign("group:group-1:member-2", "ghost")
    event = group_event("/permission show <@member-2>")

    await router.handle(event)

    assert "    ghost\n      definition is missing" in await reply_of(event)


async def test_grant_to_scene_member() -> None:
    router, store = await build()
    event = group_event("/permission grant member-2 demo.stop")

    await router.handle(event)

    assert await reply_of(event) == "Granted demo.stop to group:group-1:member-2."
    assert await store.grants("group:group-1:member-2") == frozenset({Grant("demo.stop")})


async def test_grant_keeps_explicit_prefix_and_global_flag() -> None:
    router, store = await build()
    event = group_event("/permission grant user:u9 demo.stop --global")

    await router.handle(event)

    assert await reply_of(event) == "Granted demo.stop to user:u9."
    assert await store.grants("user:u9") == frozenset({Grant("demo.stop")})


async def test_grant_resolves_a_rendered_mention() -> None:
    router, store = await build()
    event = group_event(
        "/permission grant <@member-2> demo.stop",
        mentions=[{"id": "m2", "member_openid": "member-2", "username": "bob"}],
    )

    await router.handle(event)

    assert await reply_of(event) == "Granted demo.stop to group:group-1:member-2."
    assert await store.grants("group:group-1:member-2") == frozenset({Grant("demo.stop")})


async def test_grant_rejects_the_at_all_tag() -> None:
    router, _ = await build()
    event = group_event("/permission grant <@all> demo.stop")

    await router.handle(event)

    assert await reply_of(event) == "@all is not a single member"


async def test_grant_resolves_a_raw_mention_token() -> None:
    router, store = await build()
    event = group_event("/permission grant <@6FB39F2CDD76ED6E5533B269C71FAC7F> demo.stop")

    await router.handle(event)

    assert await reply_of(event) == (
        "Granted demo.stop to group:group-1:6FB39F2CDD76ED6E5533B269C71FAC7F."
    )
    assert Grant("demo.stop") in await store.grants(
        "group:group-1:6FB39F2CDD76ED6E5533B269C71FAC7F"
    )


async def test_grant_mention_token_honours_the_global_flag() -> None:
    router, store = await build()
    event = group_event("/permission grant <@!member-2> demo.stop --global")

    await router.handle(event)

    assert await reply_of(event) == "Granted demo.stop to user:member-2."
    assert await store.grants("user:member-2") == frozenset({Grant("demo.stop")})


async def test_grant_mention_token_in_direct_message() -> None:
    router, store = await build()
    await store.grant("c2c:user-1", Grant("permission.grant"))
    event = c2c_event("/permission grant @member-2 demo.stop", openid="user-1")

    await router.handle(event)

    assert isinstance(event.api, FakeApi)
    assert event.api.user_message.calls[0]["content"] == ("Granted demo.stop to c2c:member-2.")
    assert Grant("demo.stop") in await store.grants("c2c:member-2")


async def test_show_resolves_a_raw_mention_token() -> None:
    router, store = await build()
    await store.grant("group:group-1:member-2", Grant("demo.stop"))
    event = group_event("/permission show <@member-2>")

    await router.handle(event)

    assert await reply_of(event) == (
        "group:group-1:member-2\n"
        "  scope: group group-1\n"
        "  direct: demo.stop\n"
        "  roles: none\n"
        "user:member-2\n"
        "  scope: user, applies in every scene\n"
        "  direct: none\n"
        "  roles: none"
    )


async def test_authorization_code_flow() -> None:
    router, store = await build()
    issued = group_event("/permission grant demo.stop --code")

    await router.handle(issued)

    text = await reply_of(issued)
    code = text.split("Authorization code ")[1].split(" ")[0]
    assert code.count("-") == 1

    claimed = group_event(f"/permission claim {code}")
    await router.handle(claimed)

    assert await reply_of(claimed) == "Granted demo.stop to group:group-1:member-1."
    assert Grant("demo.stop") in await store.grants("group:group-1:member-1")

    reused = group_event(f"/permission claim {code}")
    await router.handle(reused)
    assert await reply_of(reused) == "This authorization code is invalid, expired or already used."


async def test_group_code_cannot_be_claimed_in_private_chat() -> None:
    router, _ = await build()
    issued = group_event("/permission grant demo.stop --code")
    await router.handle(issued)
    text = await reply_of(issued)
    code = text.split("Authorization code ")[1].split(" ")[0]

    claimed = c2c_event(f"/permission claim {code}")
    await router.handle(claimed)

    assert isinstance(claimed.api, FakeApi)
    assert claimed.api.user_message.calls[0]["content"] == (
        "This authorization code can only be claimed in a group."
    )


async def test_claim_needs_no_permission() -> None:
    router, store = await build()
    issued = group_event("/permission grant demo.stop --code")
    await router.handle(issued)
    code = (await reply_of(issued)).split("Authorization code ")[1].split(" ")[0]

    claimed = group_event(f"/permission claim {code}", openid="member-3")
    await router.handle(claimed)

    assert await reply_of(claimed) == "Granted demo.stop to group:group-1:member-3."
    assert Grant("demo.stop") in await store.grants("group:group-1:member-3")


async def test_revoke_reports_missing_grant() -> None:
    router, _ = await build()
    event = group_event("/permission revoke member-2 demo.stop")

    await router.handle(event)

    assert await reply_of(event) == "group:group-1:member-2 does not have demo.stop"


async def test_whoami_prints_both_levels() -> None:
    router, _ = await build()
    event = group_event("/permission whoami")

    await router.handle(event)

    assert await reply_of(event) == "principal: group:group-1:member-1\naccount: user:member-1"


async def test_role_lifecycle() -> None:
    router, store = await build()

    saved = group_event("/permission role save admin demo.stop demo.start")
    await router.handle(saved)
    assert await reply_of(saved) == "Saved role admin."

    listed = group_event("/permission role list")
    await router.handle(listed)
    assert await reply_of(listed) == "admin"

    shown = group_event("/permission role show admin")
    await router.handle(shown)
    assert await reply_of(shown) == "admin\ndemo.stop\ndemo.start"

    assigned = group_event("/permission role assign member-2 admin")
    await router.handle(assigned)
    assert await reply_of(assigned) == "Assigned admin to group:group-1:member-2."
    assert await store.roles("group:group-1:member-2") == frozenset({"admin"})

    unassigned = group_event("/permission role unassign member-2 admin")
    await router.handle(unassigned)
    assert await reply_of(unassigned) == "Unassigned admin from group:group-1:member-2."

    deleted = group_event("/permission role delete admin")
    await router.handle(deleted)
    assert await reply_of(deleted) == "Deleted role admin."


async def test_unknown_role_and_missing_arguments() -> None:
    router, _ = await build()

    unknown = group_event("/permission role show ghost")
    await router.handle(unknown)
    assert await reply_of(unknown) == "Unknown role: ghost"

    bare = group_event("/permission role bogus")
    await router.handle(bare)
    assert await reply_of(bare) == "Unknown role action: bogus"


async def test_each_management_command_needs_its_own_key() -> None:
    store = MemoryPermissionStorage()
    router = Router(checker=PermissionChecker(store))
    install_permission_commands(router, store)
    await store.grant(OWNER, Grant("permission.grant"))

    granted = group_event("/permission grant member-2 demo.stop")
    await router.handle(granted)
    assert await reply_of(granted) == "Granted demo.stop to group:group-1:member-2."

    revoked = group_event("/permission revoke member-2 demo.stop")
    await router.handle(revoked)
    assert await reply_of(revoked) == "You do not have permission to use this command."

    roles = group_event("/permission role list")
    await router.handle(roles)
    assert await reply_of(roles) == "You do not have permission to use this command."

    viewed = group_event("/permission show member-2")
    await router.handle(viewed)
    assert await reply_of(viewed) == "You do not have permission to use this command."


async def test_show_of_another_principal_lists_their_keys() -> None:
    router, store = await build()
    await store.grant("group:group-1:member-2", Grant("demo.stop"))
    event = group_event("/permission show member-2")

    await router.handle(event)

    assert await reply_of(event) == (
        "group:group-1:member-2\n"
        "  scope: group group-1\n"
        "  direct: demo.stop\n"
        "  roles: none\n"
        "user:member-2\n"
        "  scope: user, applies in every scene\n"
        "  direct: none\n"
        "  roles: none"
    )
