# Copyright (c) 2026-present Half_nothing.

"""资源层端到端测试：本地 mock 服务 + 官方示例快照，断言「发了什么」和「解析成什么」。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiohttp.web
import pytest

from qbotsdk.bot import Bot
from qbotsdk.exceptions import TransportError
from qbotsdk.model.channel import Channel, ChannelType
from tests.support import MockServer

DATA = Path(__file__).parent / "data"


def snapshot(name: str) -> Any:
    """读取官方响应示例，原样喂给 mock 服务。"""

    return json.loads((DATA / name).read_text(encoding="utf-8"))


def json_route(server: MockServer, method: str, path: str, payload: object) -> None:
    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        return aiohttp.web.json_response(payload)

    server.route(method, path, handler)


def call_to(server: MockServer, path: str) -> Any:
    return next(call for call in server.calls if call.path == path)


async def test_guilds_pagination_sends_after_and_limit(bot: Bot, server: MockServer) -> None:
    payload = snapshot("guilds.json")
    json_route(server, "GET", "/users/@me/guilds", payload)

    guilds = await bot.api.user.guilds(after="696527283900292399", limit=50)

    assert len(guilds) == len(payload)
    assert guilds[0].id == payload[0]["id"]
    assert call_to(server, "/users/@me/guilds").query == {
        "after": "696527283900292399",
        "limit": "50",
    }


async def test_guild_get(bot: Bot, server: MockServer) -> None:
    payload = snapshot("guild.json")
    json_route(server, "GET", "/guilds/123", payload)

    guild = await bot.api.guild.get("123")

    assert guild.name == payload["name"]
    assert guild.owner is False


async def test_channels_list_is_bare_array(bot: Bot, server: MockServer) -> None:
    payload = snapshot("channels.json")
    json_route(server, "GET", "/guilds/123/channels", payload)

    channels = await bot.api.guild.channels("123")

    assert isinstance(channels, list)
    assert all(isinstance(channel, Channel) for channel in channels)
    assert channels[0].type is ChannelType.TEXT
    assert channels[-1].type is ChannelType.AUDIO


async def test_channel_get(bot: Bot, server: MockServer) -> None:
    payload = snapshot("channel.json")
    json_route(server, "GET", "/channels/456", payload)

    channel = await bot.api.channel.get("456")

    assert channel.id == payload["id"]
    assert channel.parent_id == payload["parent_id"]


async def test_members_sends_after_and_limit(bot: Bot, server: MockServer) -> None:
    payload = snapshot("members.json")
    json_route(server, "GET", "/guilds/123/members", payload)

    members = await bot.api.guild.members("123", after="u9", limit=20)

    assert len(members) == len(payload)
    assert members[0].user.id == payload[0]["user"]["id"]
    assert call_to(server, "/guilds/123/members").query == {"after": "u9", "limit": "20"}


async def test_roles_result(bot: Bot, server: MockServer) -> None:
    payload = snapshot("roles.json")
    json_route(server, "GET", "/guilds/123/roles", payload)

    result = await bot.api.guild.roles("123")

    assert result.guild_id == payload["guild_id"]
    assert result.role_num_limit == "30"
    assert isinstance(result.role_num_limit, str)


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
async def test_get_me_forwards_to_user_resource(bot: Bot, server: MockServer) -> None:
    payload = {"id": "123", "username": "tester", "avatar": "", "bot": True}
    json_route(server, "GET", "/users/@me", payload)

    first = await bot.get_me()
    second = await bot.api.user.me()

    assert first.id == second.id == "123"
    assert len([call for call in server.calls if call.path == "/users/@me"]) == 2


async def test_shape_mismatch_raises(bot: Bot, server: MockServer) -> None:
    # 官方契约是裸数组；返回对象形状说明契约变了，必须显式报错而不是猜
    json_route(server, "GET", "/guilds/123/channels", {"channels": []})

    with pytest.raises(TransportError) as info:
        await bot.api.guild.channels("123")

    assert "expected a JSON array" in str(info.value)
