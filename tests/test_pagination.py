# Copyright (c) 2026-present Half_nothing.

"""分页测试：去重、空页终止、游标推进。"""

from __future__ import annotations

from typing import Any

import aiohttp.web

from qbotsdk.bot import Bot
from tests.support import MockServer


def member(user_id: str) -> dict[str, Any]:
    return {
        "user": {"id": user_id, "username": user_id, "avatar": ""},
        "nick": "",
        "roles": ["1"],
        "joined_at": "2021-12-22T12:00:00+08:00",
        "deaf": False,
        "mute": False,
        "pending": False,
    }


def guild(guild_id: str) -> dict[str, Any]:
    return {
        "id": guild_id,
        "name": guild_id,
        "icon": "",
        "owner_id": "1",
        "owner": False,
        "member_count": 1,
        "max_members": 100,
        "description": "",
        "joined_at": "2021-12-22T12:00:00+08:00",
    }


def route_pages(
    server: MockServer,
    path: str,
    pages: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    *,
    cursor_key: str = "after",
) -> None:
    """按 query 里的游标返回对应页；传列表则忽略游标，恒返回同一页。"""

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        if isinstance(pages, list):
            return aiohttp.web.json_response(pages)
        cursor = request.query.get(cursor_key, "0")
        return aiohttp.web.json_response(pages.get(cursor, []))

    server.route("GET", path, handler)


def calls_to(server: MockServer, path: str) -> list[Any]:
    return [call for call in server.calls if call.path == path]


async def test_members_dedupe(bot: Bot, server: MockServer) -> None:
    path = "/guilds/123/members"
    route_pages(
        server,
        path,
        {
            "0": [member("u1"), member("u2")],
            "u2": [member("u2"), member("u3")],
            "u3": [],
        },
    )

    ids = [m.user.id async for m in bot.api.guild.iter_members("123", limit=2)]

    assert ids == ["u1", "u2", "u3"]
    assert [call.query["after"] for call in calls_to(server, path)] == ["0", "u2", "u3"]


async def test_stops_on_empty_page(bot: Bot, server: MockServer) -> None:
    path = "/guilds/123/members"
    route_pages(server, path, {"0": [member("u1")]})

    ids = [m.user.id async for m in bot.api.guild.iter_members("123")]

    assert ids == ["u1"]
    assert len(calls_to(server, path)) == 2


async def test_stops_when_cursor_stalls(bot: Bot, server: MockServer) -> None:
    path = "/guilds/123/members"
    route_pages(server, path, [member("u1")])

    ids = [m.user.id async for m in bot.api.guild.iter_members("123")]

    assert ids == ["u1"]
    assert len(calls_to(server, path)) == 2


async def test_guilds_iterate_until_partial_page(bot: Bot, server: MockServer) -> None:
    path = "/users/@me/guilds"
    route_pages(
        server,
        path,
        {
            "0": [guild("g1"), guild("g2")],
            "g2": [guild("g3")],
        },
    )

    ids = [g.id async for g in bot.api.user.iter_guilds(limit=2)]

    assert ids == ["g1", "g2", "g3"]
    assert len(calls_to(server, path)) == 2
