# Copyright (c) 2026-present Half_nothing.

"""WebhookServer 的用例：配置校验、明文回调、TLS 链路、验签失败。"""

from __future__ import annotations

import ipaddress
import ssl
from asyncio import sleep
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession, TCPConnector
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID
from loguru import logger

from qbotsdk.bot import Bot
from qbotsdk.gateway.webhook import build_validation_response
from qbotsdk.gateway.webhook_server import WebhookServer
from qbotsdk.model.event import GroupAtMessageCreate
from tests.support import read_frame

if TYPE_CHECKING:
    from async_event_bus import EventContext

BOT_SECRET = "DG5g3B4j9X2KOErG"
TIMESTAMP = "1725442341"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """按官方的种子规则给请求体签名。"""

    raw = secret.encode("utf-8")
    seed = (raw * (32 // len(raw) + 1))[:32]
    return (
        ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        .sign(timestamp.encode("utf-8") + body)
        .hex()
    )


def write_self_signed_cert(directory: Path) -> tuple[str, str]:
    """生成一张只用于测试的自签证书。"""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certfile = directory / "cert.pem"
    keyfile = directory / "key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(certfile), str(keyfile)


@pytest.fixture
async def bot() -> AsyncIterator[Bot]:
    instance = Bot(app_id="app", client_secret=BOT_SECRET)
    try:
        yield instance
    finally:
        await instance.close()


def test_certfile_needs_keyfile(bot: Bot) -> None:
    with pytest.raises(ValueError, match="certfile and keyfile must be provided together"):
        WebhookServer(bot.dispatcher, BOT_SECRET, certfile="cert.pem")


def test_ssl_context_excludes_certfile(bot: Bot) -> None:
    with pytest.raises(ValueError, match="ssl_context cannot be combined"):
        WebhookServer(
            bot.dispatcher,
            BOT_SECRET,
            certfile="cert.pem",
            keyfile="key.pem",
            ssl_context=ssl.create_default_context(),
        )


async def test_validation_request_is_answered(bot: Bot) -> None:
    server = WebhookServer(bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0)
    await server.start()
    try:
        payload = (
            b'{"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}}'
        )
        async with (
            ClientSession() as session,
            session.post(server.url, data=payload) as response,
        ):
            assert response.status == 200
            assert await response.json() == build_validation_response(
                BOT_SECRET, "Arq0D5A61EgUu4OxUvOp", "1725442341"
            )
    finally:
        await server.close()


async def test_event_is_acked_and_dispatched(bot: Bot) -> None:
    received: list[GroupAtMessageCreate] = []

    @bot.on(GroupAtMessageCreate)
    async def handler(ctx: EventContext[GroupAtMessageCreate]) -> None:
        received.append(ctx.event)

    body = read_frame("gateway_group_at_message_create.json").encode()
    server = WebhookServer(bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0)
    await server.start()
    try:
        async with (
            ClientSession() as session,
            session.post(
                server.url,
                data=body,
                headers={
                    "X-Signature-Ed25519": sign(BOT_SECRET, TIMESTAMP, body),
                    "X-Signature-Timestamp": TIMESTAMP,
                },
            ) as response,
        ):
            assert response.status == 200
            assert await response.json() == {"op": 12, "d": {}}

        for _ in range(50):
            if received:
                break
            await sleep(0.02)
        assert len(received) == 1
        assert received[0].content == "hello"
    finally:
        await server.close()


async def test_bad_signature_is_rejected(bot: Bot) -> None:
    body = read_frame("gateway_group_at_message_create.json").encode()
    server = WebhookServer(bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0)
    await server.start()
    try:
        async with ClientSession() as session:
            async with session.post(
                server.url,
                data=body,
                headers={
                    "X-Signature-Ed25519": "00" * 64,
                    "X-Signature-Timestamp": TIMESTAMP,
                },
            ) as response:
                assert response.status == 401
            async with session.post(server.url, data=body) as response:
                assert response.status == 401
    finally:
        await server.close()


async def test_invalid_payload_is_rejected(bot: Bot) -> None:
    server = WebhookServer(bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0)
    await server.start()
    try:
        async with (
            ClientSession() as session,
            session.post(server.url, data=b"not json") as response,
        ):
            assert response.status == 400
    finally:
        await server.close()


async def test_tls_certificate_is_loaded(bot: Bot, tmp_path: Path) -> None:
    certfile, keyfile = write_self_signed_cert(tmp_path)
    server = WebhookServer(
        bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0, certfile=certfile, keyfile=keyfile
    )
    await server.start()
    try:
        assert server.url.startswith("https://")
        payload = (
            b'{"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}}'
        )
        async with (
            ClientSession(connector=TCPConnector(ssl=False)) as session,
            session.post(server.url, data=payload) as response,
        ):
            assert response.status == 200
            assert (await response.json())["plain_token"] == "Arq0D5A61EgUu4OxUvOp"
    finally:
        await server.close()


async def test_non_callback_port_warns(bot: Bot) -> None:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    server = WebhookServer(bot.dispatcher, BOT_SECRET, host="127.0.0.1", port=0)
    try:
        await server.start()
        await server.close()
    finally:
        logger.remove(sink_id)

    assert any("not in the callback port list" in message for message in messages)
