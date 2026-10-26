# Copyright (c) 2026-present Half_nothing.

"""
游标分页的统一实现
两类列表的游标语义不同
频道列表是 after=<最后一个 guild id>
成员列表是 after=<最后一个 member 的 user.id> 且可能重复返回已给过的成员
差异由调用方用回调表达，公共部分只有「取页 -> 产出 -> 推进游标 -> 判终止」
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from loguru import logger

_MAX_PAGES = 1000


async def paginate[T](
    fetch_page: Callable[[str | None], Awaitable[list[T]]],
    *,
    cursor_of: Callable[[list[T]], str | None],
    key_of: Callable[[T], str] | None = None,
    page_size: int | None = None,
) -> AsyncIterator[T]:
    """按游标翻页。

    Args:
        fetch_page: 传入游标，返回该页原始模型列表；首次调用游标为 None。
        cursor_of:  从一页数据里取下一页游标，返回 None 表示没有下一页。
        key_of:     提供时按该键去重，用于成员列表。
        page_size:  提供时，某页不足该数量即视为最后一页；
                    成员列表传 None，因为官方只承诺空数组表示结束。

    Yields:
        逐条产出模型，同一键只产出一次。
    """

    cursor: str | None = None
    seen: set[str] = set()
    pages = 0

    while True:
        page = await fetch_page(cursor)
        pages += 1
        if not page:
            return

        for item in page:
            if key_of is None:
                yield item
                continue
            key = key_of(item)
            if key in seen:
                continue
            seen.add(key)
            yield item

        if pages >= _MAX_PAGES:
            logger.warning("Pagination stopped after {} pages, cursor may be looping", pages)
            return

        next_cursor = cursor_of(page)
        if next_cursor is None or next_cursor == cursor:
            logger.warning("Pagination stopped, cursor did not advance: {!r}", next_cursor)
            return

        cursor = next_cursor
        if page_size is not None and len(page) < page_size:
            return
