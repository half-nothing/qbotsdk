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

"""内置权限管理命令。"""

from __future__ import annotations

from secrets import choice
from typing import TYPE_CHECKING, Final

from qbotsdk.commands import Context, Reply, UsageError
from qbotsdk.model import (
    C2CMessageCreate,
    ChannelMessageCreate,
    GroupAtMessageCreate,
    GroupMessageCreate,
)

from .checker import account_of
from .grant import Grant, PendingGrant, Role
from .node import Permission, PermissionGroup

if TYPE_CHECKING:
    from qbotsdk.commands import Router
    from qbotsdk.model import EventModel

    from .store import PermissionStorage

__all__ = ["PermissionCommands", "install_permission_commands"]

_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_PREFIXES: Final[tuple[str, ...]] = ("group:", "c2c:", "user:", "guild:")

# 管理命令在三种有主体的消息场景里都可用, 频道不属于权限模型的场景主体
_TEXT_EVENTS: Final[tuple[type[EventModel], ...]] = (
    GroupMessageCreate,
    GroupAtMessageCreate,
    C2CMessageCreate,
    ChannelMessageCreate,
)


class PermissionCommands(PermissionGroup, namespace="permission"):
    """管理命令自身需要的能力。"""

    SHOW = Permission("show", "查看任意主体的权限")
    GRANT = Permission("grant", "授予权限、签发授权码")
    REVOKE = Permission("revoke", "撤销权限")
    ROLE = Permission("role", "管理角色定义与分配")


def _new_code() -> str:
    """`ABCD-2345` 形态, 去掉容易看混的 0/O/1/I。"""

    raw = "".join(choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _group_openid(ctx: Context) -> str:
    """从场景主体键里取群号, 非群聊场景返回空串。"""

    if ctx.kind != "group":
        return ""
    _, _, rest = ctx.principal.partition(":")
    group_openid, _, _ = rest.partition(":")
    return group_openid


def _openid_of(ctx: Context) -> str:
    return ctx.principal.rpartition(":")[2]


def _scene_key(ctx: Context, openid: str, *, global_: bool) -> str:
    """按当前场景把 openid 组成主体键。"""

    if not openid:
        raise UsageError("Target must not be empty")
    if openid == "all":
        raise UsageError("@all is not a single member")
    if global_:
        return f"user:{openid}"
    if ctx.kind == "group":
        return f"group:{_group_openid(ctx)}:{openid}"
    if ctx.kind == "c2c":
        return f"c2c:{openid}"
    raise UsageError(f"Cannot resolve the target {openid!r} in this scene")


def _resolve(ctx: Context, token: str, *, global_: bool) -> str:
    """把命令里写的授权目标变成主体键。

    文本里的 @ 标记已由事件层统一渲染成 `@openid`, 这里剥掉 `@` 即得 openid;
    已经写全场景前缀的键原样保留, 裸值按当前场景补齐。
    """

    if token.startswith("@"):
        return _scene_key(ctx, token[1:], global_=global_)
    if token.startswith(_PREFIXES):
        return token
    return _scene_key(ctx, token, global_=global_)


def _pending_target(ctx: Context, pending: PendingGrant) -> str:
    openid = _openid_of(ctx)
    return f"user:{openid}" if pending.scope == "global" else f"group:{_group_openid(ctx)}:{openid}"


def _scope_of(principal: str) -> str:
    """把主体键翻译成人类可读的作用域。"""

    kind, _, rest = principal.partition(":")
    if kind == "group":
        return f"group {rest.partition(':')[0]}"
    if kind == "c2c":
        return "direct message"
    if kind == "user":
        return "user, applies in every scene"
    if kind == "guild":
        return f"guild {rest.partition(':')[0]}"
    return "custom"


def install_permission_commands(
    router: Router,
    store: PermissionStorage,
    *,
    code_ttl: float = 600.0,
) -> None:
    """为命令路由安装权限管理命令。"""

    async def _describe(principal: str) -> tuple[list[str], bool]:
        """一个主体的作用域、直接授予、被分配的角色与角色权限。"""

        lines = [principal, f"  scope: {_scope_of(principal)}"]
        direct = sorted(await store.grants(principal), key=lambda item: item.permission)
        lines.append("  direct: " + (", ".join(item.encoded for item in direct) or "none"))
        names = sorted(await store.roles(principal))
        if not names:
            lines.append("  roles: none")
            return lines, bool(direct)
        lines.append("  roles:")
        for name in names:
            role_ = await store.role(name)
            lines.append(f"    {name}")
            if role_ is None:
                lines.append("      definition is missing")
                continue
            grants = sorted(role_.grants, key=lambda item: item.permission)
            lines.append("      grants: " + (", ".join(item.encoded for item in grants) or "none"))
            if role_.parents:
                lines.append("      inherits: " + ", ".join(sorted(role_.parents)))
        return lines, True

    async def _sections(principal: str) -> tuple[list[str], bool]:
        """场景主体与账号主体的两段输出; 第二段不存在时只有一段。"""

        principals = [principal]
        account = account_of(principal)
        if account is not None and account != principal:
            principals.append(account)
        lines: list[str] = []
        found = False
        for item in principals:
            block, granted = await _describe(item)
            lines.extend(block)
            found = found or granted
        return lines, found

    @router.command("permission show", on=_TEXT_EVENTS)
    async def show(ctx: Context) -> Reply:
        lines, found = await _sections(ctx.principal)
        if not found:
            return Reply(text="No permissions are granted.")
        return Reply(text="Your permissions:\n" + "\n".join(lines))

    @router.command(
        "permission show <target:rest>",
        on=_TEXT_EVENTS,
        permission=PermissionCommands.SHOW,
        bind_args=False,
    )
    async def show_target(ctx: Context, argv: list[str]) -> Reply:
        target = _resolve(ctx, argv[0], global_=False)
        lines, found = await _sections(target)
        if not found:
            return Reply(text=f"No permissions are granted to {target}.")
        return Reply(text="\n".join(lines))

    @router.command(
        "permission grant <target:rest>",
        on=_TEXT_EVENTS,
        permission=PermissionCommands.GRANT,
        bind_args=False,
    )
    async def grant(ctx: Context, argv: list[str]) -> Reply:
        flags = {token for token in argv if token.startswith("--")}
        positional = [token for token in argv if not token.startswith("--")]
        global_ = "--global" in flags
        if "--code" in flags:
            if len(positional) != 1:
                raise UsageError(
                    "Invalid arguments. Usage: /permission grant <key> --code [--global]"
                )
            key = positional[0]
            scope = "global" if global_ else "group"
            if scope == "group" and ctx.kind != "group":
                raise UsageError("Group scope needs a group chat, add --global instead")
            pending = PendingGrant(
                key,
                "global" if global_ else "group",
                _group_openid(ctx) if ctx.kind == "group" else None,
            )
            code = _new_code()
            await store.save_pending(code, pending, ttl=code_ttl)
            return Reply(
                text=f"Authorization code {code} expires in {int(code_ttl // 60)} minutes; "
                f"run /permission claim {code}."
            )
        if len(positional) != 2:
            raise UsageError(
                "Invalid arguments. Usage: /permission grant <target> <key> [--global]"
            )
        target = _resolve(ctx, positional[0], global_=global_)
        await store.grant(target, Grant(positional[1]))
        return Reply(text=f"Granted {positional[1]} to {target}.")

    @router.command("permission claim <code:str>", on=_TEXT_EVENTS)
    async def claim(ctx: Context, code: str) -> Reply:
        pending = await store.pop_pending(code)
        if pending is None:
            raise UsageError("This authorization code is invalid, expired or already used.")
        if pending.scope == "group" and ctx.kind != "group":
            raise UsageError("This authorization code can only be claimed in a group.")
        target = _pending_target(ctx, pending)
        await store.grant(target, Grant(pending.permission))
        return Reply(text=f"Granted {pending.permission} to {target}.")

    @router.command(
        "permission revoke <target:str> <key:str>",
        on=_TEXT_EVENTS,
        permission=PermissionCommands.REVOKE,
    )
    async def revoke(ctx: Context, target: str, key: str) -> Reply:
        principal = _resolve(ctx, target, global_=False)
        removed = await store.revoke(principal, key)
        if not removed:
            raise UsageError(f"{principal} does not have {key}")
        return Reply(text=f"Revoked {key} from {principal}.")

    @router.command("permission whoami", on=_TEXT_EVENTS)
    async def whoami(ctx: Context) -> Reply:
        lines = [f"principal: {ctx.principal}"]
        if ctx.account is not None:
            lines.append(f"account: {ctx.account}")
        return Reply(text="\n".join(lines))

    @router.command(
        "permission role <rest:rest>",
        on=_TEXT_EVENTS,
        permission=PermissionCommands.ROLE,
        bind_args=False,
    )
    async def role(ctx: Context, argv: list[str]) -> Reply:
        if not argv:
            raise UsageError(
                "Invalid arguments. Usage: /permission role list|show|save|delete|assign|unassign"
            )
        action, rest = argv[0], argv[1:]
        if action == "list":
            roles = await store.all_roles()
            if not roles:
                return Reply(text="No roles are defined.")
            return Reply(text="\n".join(role.name for role in roles))
        if action == "show":
            if len(rest) != 1:
                raise UsageError("Invalid arguments. Usage: /permission role show <name>")
            found = await store.role(rest[0])
            if found is None:
                raise UsageError(f"Unknown role: {rest[0]}")
            return Reply(text="\n".join([found.name, *[grant_.encoded for grant_ in found.grants]]))
        if action == "save":
            if len(rest) < 2:
                raise UsageError("Invalid arguments. Usage: /permission role save <name> <key>...")
            await store.save_role(Role(rest[0], grants=tuple(Grant(item) for item in rest[1:])))
            return Reply(text=f"Saved role {rest[0]}.")
        if action == "delete":
            if len(rest) != 1:
                raise UsageError("Invalid arguments. Usage: /permission role delete <name>")
            if not await store.delete_role(rest[0]):
                raise UsageError(f"Unknown role: {rest[0]}")
            return Reply(text=f"Deleted role {rest[0]}.")
        if action in {"assign", "unassign"}:
            if len(rest) != 2:
                raise UsageError(
                    f"Invalid arguments. Usage: /permission role {action} <target> <name>"
                )
            principal = _resolve(ctx, rest[0], global_=False)
            role_name = rest[1]
            if action == "assign":
                if await store.role(role_name) is None:
                    raise UsageError(f"Unknown role: {role_name}")
                await store.assign(principal, role_name)
                return Reply(text=f"Assigned {role_name} to {principal}.")
            await store.unassign(principal, role_name)
            return Reply(text=f"Unassigned {role_name} from {principal}.")
        raise UsageError(f"Unknown role action: {action}")
