# Copyright (c) 2026-present Half_nothing.

"""网关连接流程，Hello → Identify / Resume → 心跳 → 断线重连。

这一层只负责连接活着并且事件能被读出来
读完的事件按原样放进 events 队列
带 t 的 ready / resumed 会顺带更新 session 状态，让下一次重连能走 Resume。
"""

from __future__ import annotations

from asyncio import CancelledError, Queue, Task, create_task, sleep
from contextlib import suppress
from random import uniform
from sys import platform

from aiohttp import (
    ClientError,
    ClientWebSocketResponse,
    ClientWSTimeout,
    WSMsgType,
    WSServerHandshakeError,
)
from loguru import logger

from ..exceptions import TransportError
from ..model.event import ReadyEvent
from ..module.http_client import HTTPClient
from ..options import ClientOptions
from .payload import (
    CloseAction,
    GatewayClosedError,
    GatewayError,
    GatewayPayload,
    HeartbeatFrame,
    HelloFrame,
    IdentifyData,
    IdentifyFrame,
    Intents,
    OpCode,
    ResumeData,
    ResumeFrame,
    close_action,
)
from .session import GatewayInfo, SessionState

# 官方只给了 [0, 1] 一种分片写法，本期不做自动分片
_DEFAULT_SHARD = (0, 1)
_IDENTIFY_PROPERTIES = {
    "$os": platform,
    "$browser": "qbotsdk-sdk",
    "$device": "qbotsdk-sdk",
}
# 连续两个心跳周期没收到 op 11 就认为连接已死
_PENDING_ACK_LIMIT = 2
# 1000 正常关闭、1001 对端离开、1006 连接异常断开，按网络问题重连
_NORMAL_CLOSE_CODES = frozenset({1000, 1001, 1006})


class GatewayConnection:
    """一条到网关的长连接。

    run() 是常驻协程，连上、握手、读事件
    断了按关闭码决定 Resume 还是重新 Identify
    直到底层 close() 被调用或收到不可恢复的关闭码
    """

    def __init__(
        self,
        http: HTTPClient,
        *,
        options: ClientOptions | None = None,
        intents: int | None = None,
        shard: tuple[int, int] = _DEFAULT_SHARD,
    ) -> None:
        self._http = http
        self._options = options or ClientOptions()
        self._intents = Intents.DEFAULT if intents is None else intents
        self._shard = shard
        self.session = SessionState()
        # 读出来的事件先放这里，分发层从这里取
        self.events: Queue[GatewayPayload] = Queue()
        self._ws: ClientWebSocketResponse | None = None
        self._heartbeat_task: Task[None] | None = None
        self._gateway_url: str | None = None
        self._closed = False
        self._pending_acks = 0
        self._established = False

    @property
    def intents(self) -> int:
        return self._intents

    async def run(self) -> None:
        """常驻循环直到 close() 或不可恢复的关闭码。"""

        attempt = 0
        while not self._closed:
            self._established = False
            try:
                action = await self._connection_once()
            except (TimeoutError, ClientError, TransportError, OSError) as exc:
                logger.warning("Gateway connection failed: {!r}", exc)
                action = CloseAction.RESUME if self.session.can_resume else CloseAction.IDENTIFY
            if self._closed:
                return
            if action is CloseAction.RESUME and not self.session.can_resume:
                action = CloseAction.IDENTIFY
            if action is CloseAction.IDENTIFY:
                self.session.reset()
            attempt = 0 if self._established else attempt + 1
            delay = self._backoff(attempt)
            logger.info("Reconnecting gateway in {:.2f}s (action={})", delay, action.name)
            await sleep(delay)

    async def close(self) -> None:
        self._closed = True
        await self._stop_heartbeat()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def _connection_once(self) -> CloseAction:
        url = await self._resolve_url()
        session = await self._http.get_session()
        try:
            ws = await session.ws_connect(
                url,
                autoclose=True,
                autoping=True,
                # 长连接不用总超时，连接是否活着由心跳判断
                timeout=ClientWSTimeout(),
            )
        except WSServerHandshakeError as exc:
            raise GatewayError(f"gateway handshake failed with HTTP {exc.status}") from exc
        self._ws = ws
        try:
            interval = await self._hello(ws)
            token = await self._http.access_token()
            frame = (
                self._resume_frame(token)
                if self.session.can_resume
                else self._identify_frame(token)
            )
            await ws.send_str(frame.to_json())
            self._pending_acks = 0
            self._heartbeat_task = create_task(self._heartbeat(ws, interval))
            action = await self._read(ws)
        finally:
            await self._stop_heartbeat()
            if not ws.closed:
                await ws.close()
            self._ws = None

        if action is not None:
            return action
        if self._closed:
            # 我们自己关的, 不参与重连决策
            return CloseAction.IDENTIFY
        # 对面直接关连接时按关闭码决定后续动作
        code = ws.close_code
        if code is None or code in _NORMAL_CLOSE_CODES:
            return CloseAction.RESUME if self.session.can_resume else CloseAction.IDENTIFY
        action = close_action(code)
        if action is CloseAction.STOP:
            raise GatewayClosedError(code, action, "the gateway asked us not to reconnect")
        return action

    async def _resolve_url(self) -> str:
        if self._gateway_url is None:
            payload = await self._http.get("/gateway/bot")
            info = GatewayInfo.model_validate(payload)
            self._gateway_url = info.url
            logger.info(
                "Gateway endpoint resolved: shards={} remaining={}",
                info.shards,
                info.session_start_limit.remaining,
            )
            return info.url
        return self._gateway_url

    @staticmethod
    async def _hello(ws: ClientWebSocketResponse) -> float:
        """等 op 10 Hello，返回心跳间隔（秒）。"""

        while True:
            message = await ws.receive()
            if message.type is WSMsgType.TEXT:
                break
            if message.type in {WSMsgType.CLOSED, WSMsgType.ERROR}:
                raise TransportError(
                    f"gateway closed before hello: {message.type.name}",
                    method="GET",
                    path="/gateway/bot",
                )
        frame = HelloFrame.model_validate_json(message.data)
        if frame.op is not OpCode.HELLO:
            raise GatewayError(f"expected hello, got op {int(frame.op)}")
        return frame.d.heartbeat_interval / 1000.0

    def _identify_frame(self, token: str) -> IdentifyFrame:
        return IdentifyFrame(
            d=IdentifyData(
                token=f"QQBot {token}",
                intents=self._intents,
                shard=list(self._shard),
                properties=_IDENTIFY_PROPERTIES,
            )
        )

    def _resume_frame(self, token: str) -> ResumeFrame:
        session_id = self.session.session_id
        if session_id is None:
            raise GatewayError("cannot resume without a session id")
        return ResumeFrame(
            d=ResumeData(
                token=f"QQBot {token}",
                session_id=session_id,
                seq=self.session.seq,
            )
        )

    async def _read(self, ws: ClientWebSocketResponse) -> CloseAction | None:
        async for message in ws:
            if message.type is not WSMsgType.TEXT:
                continue
            payload = GatewayPayload.model_validate_json(message.data)
            action = self._handle(payload)
            if action is not None:
                return action
        return None

    def _handle(self, payload: GatewayPayload) -> CloseAction | None:
        if payload.op is OpCode.DISPATCH:
            self.session.update(seq=payload.s)
            self._established = True
            self.events.put_nowait(payload)
            if payload.t == "READY":
                ready = ReadyEvent.model_validate(payload.d)
                self.session.update(session_id=ready.session_id)
                logger.info("Gateway session ready: {}", ready.session_id)
            elif payload.t == "RESUMED":
                logger.info("Gateway session resumed: {}", self.session.session_id)
            return None
        if payload.op is OpCode.HEARTBEAT_ACK:
            self._pending_acks = 0
            return None
        if payload.op is OpCode.RECONNECT:
            logger.info("Gateway asked for a reconnect")
            return CloseAction.RESUME
        if payload.op is OpCode.INVALID_SESSION:
            logger.warning("Gateway invalidated the session, identifying again")
            self.session.reset()
            return CloseAction.IDENTIFY
        # Hello / Heartbeat 等其余 op 不需要处理
        return None

    async def _heartbeat(self, ws: ClientWebSocketResponse, interval: float) -> None:
        while not ws.closed:
            await sleep(interval)
            if ws.closed:
                return
            if self._pending_acks >= _PENDING_ACK_LIMIT:
                logger.warning("Gateway missed {} heartbeat acks, reconnecting", self._pending_acks)
                await ws.close()
                return
            self._pending_acks += 1
            await ws.send_str(HeartbeatFrame(d=self.session.seq).to_json())

    async def _stop_heartbeat(self) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None and not task.done():
            task.cancel()
            with suppress(CancelledError):
                await task

    def _backoff(self, attempt: int) -> float:
        base = float(self._options.backoff_base * 2 ** max(attempt - 1, 0))
        delay = min(base, self._options.backoff_max)
        return delay * (1.0 + uniform(0.0, 0.25))
