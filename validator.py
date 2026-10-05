#!/usr/bin/env python3
"""
Telegram Bot Token Validator & Mock Generator — single-file edition.

Features:
  * Single-file, zero external deps beyond `requests` and `python-dotenv`
  * Token generator: Create synthetic Telegram bot token format samples
  * Concurrent-safe sequential pipeline with per-token retry/backoff
  * Exponential backoff on 429 with Retry-After honoring
  * Structured JSON logging (optional) with token masking
  * Async worker pool via asyncio (bounded concurrency)
  * Rich NEW HIT output with box drawing + optional ANSI color
  * Safe console output encoding across Windows / Linux / macOS
  * CSV / JSON export of results
  * Demo mode — no network calls, deterministic fake registry
  * Graceful SIGINT/SIGTERM shutdown
  * Type-hinted throughout, fully integrated CLI
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import random
import re
import signal
import string
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Ensure UTF-8 output encoding support across platforms (including Windows consoles)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(2)

try:
    from dotenv import load_dotenv
except ImportError:
    # Optional dependency — if missing, we just don't auto-load .env
    def load_dotenv(*_a, **_kw):  # type: ignore
        return False


# ===================================================================== #
# Constants & Helpers
# ===================================================================== #

TELEGRAM_API = "https://api.telegram.org/bot{token}/getMe"
TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_\-]{30,}$")
ALLOWED_TOKEN_CHARS = string.ascii_letters + string.digits + "_-"

# ANSI escape codes (disabled when NO_COLOR is set or stdout is not a TTY)
_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}


# ===================================================================== #
# Token Generator
# ===================================================================== #

def generate_token_part(length: int = 45) -> str:
    """Generate the random secret string part after colon."""
    return "".join(random.choice(ALLOWED_TOKEN_CHARS) for _ in range(length))


def generate_bot_id(min_digits: int = 9, max_digits: int = 10) -> int:
    """Generate a random bot ID with given digit length range."""
    digits = random.randint(min_digits, max_digits)
    first = str(random.randint(1, 9))
    rest = "".join(str(random.randint(0, 9)) for _ in range(digits - 1))
    return int(first + rest)


def make_fake_token(length: int = 45) -> str:
    """Generate a formatted mock token (e.g. 123456789:ABC_xyz...)."""
    bot_id = generate_bot_id()
    token_part = generate_token_part(length=length)
    return f"{bot_id}:{token_part}"


def generate_tokens(count: int, output_file: Optional[str] = None) -> list[str]:
    """Generate multiple mock tokens and optionally save to file."""
    tokens = [make_fake_token() for _ in range(count)]
    if output_file:
        p = Path(output_file)
        p.write_text("\n".join(tokens) + "\n", encoding="utf-8")
        print(f"Generated {count} token(s) saved to: {p.resolve()}")
    else:
        for t in tokens:
            print(t)
    return tokens


# ===================================================================== #
# Config
# ===================================================================== #

@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    token_file: str
    request_timeout: float
    check_delay: float
    demo_mode: bool
    log_level: str
    log_json: bool
    concurrency: int
    max_retries: int
    retry_base_delay: float
    export_csv: Optional[str]
    export_json: Optional[str]
    color: bool
    explicit_tokens: list[str] = field(default_factory=list)

    @classmethod
    def from_env_and_cli(cls, explicit_tokens: Optional[list[str]] = None) -> "Config":
        def _b(name: str, default: bool) -> bool:
            v = os.getenv(name)
            if v is None:
                return default
            return v.strip().lower() in {"1", "true", "yes", "on"}

        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        def _i(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        color_env = os.getenv("NO_COLOR")
        color = (color_env is None) and sys.stdout.isatty()

        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            token_file=os.getenv("TOKEN_FILE", "tokens.txt").strip(),
            request_timeout=_f("REQUEST_TIMEOUT", 10.0),
            check_delay=_f("CHECK_DELAY", 0.5),
            demo_mode=_b("DEMO_MODE", False),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_json=_b("LOG_JSON", False),
            concurrency=max(1, _i("CONCURRENCY", 1)),
            max_retries=max(0, _i("MAX_RETRIES", 2)),
            retry_base_delay=_f("RETRY_BASE_DELAY", 1.0),
            export_csv=os.getenv("EXPORT_CSV") or None,
            export_json=os.getenv("EXPORT_JSON") or None,
            color=color,
            explicit_tokens=list(explicit_tokens or []),
        )

    def load_tokens(self) -> list[str]:
        """Load tokens from explicit list, TOKEN_FILE if it exists, or env."""
        tokens: list[str] = []
        if self.explicit_tokens:
            tokens.extend(self.explicit_tokens)

        p = Path(self.token_file)
        if not tokens and p.is_file():
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                tokens.append(line)

        if not tokens and self.telegram_bot_token:
            tokens.append(self.telegram_bot_token)

        # de-duplicate, preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        return uniq


# ===================================================================== #
# Logger
# ===================================================================== #

def mask_token(token: str) -> str:
    """Return a safe, loggable representation of a token."""
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


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{ts} | {record.levelname:<7} | {record.getMessage()}"


def setup_logger(level_name: str, as_json: bool) -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("token_validator")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter() if as_json else _HumanFormatter())
    logger.addHandler(handler)
    return logger


# ===================================================================== #
# Result model
# ===================================================================== #

@dataclass
class ValidationResult:
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
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_public_dict(self) -> dict:
        """Dict safe for export — keeps token since caller asked for it."""
        return asdict(self)


# ===================================================================== #
# Validator
# ===================================================================== #

class TokenValidator:
    """
    Validates tokens sequentially (or with bounded concurrency) against
    Telegram's Bot API. Retries transient failures with exponential backoff.
    """

    # Demo-mode fake registry: token -> getMe result
    _DEMO_HITS: dict[str, dict] = {
        "111111111:DEMOtokenAAAAAAAAAAAAAAAAAAAAAAAAA": {
            "id": 111111111,
            "username": "demo_bot_123",
            "first_name": "Demo Bot",
            "can_join_groups": True,
            "can_read_all_group_messages": False,
            "supports_inline_queries": False,
        },
        "222222222:DEMOtokenBBBBBBBBBBBBBBBBBBBBBBBBB": {
            "id": 222222222,
            "username": "demo_bot_456",
            "first_name": "Another Demo",
            "can_join_groups": True,
            "can_read_all_group_messages": False,
            "supports_inline_queries": True,
        },
    }

    def __init__(self, cfg: Config, logger: logging.Logger, proxies: Optional[list[str]] = None) -> None:
        self.cfg = cfg
        self.log = logger
        self.proxies = list(proxies or [])
        self._proxy_idx = 0
        # one Session per validator; connection pooling is polite to Telegram
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "token-validator/2.0"})

    # -------------------------------------------------------------- #
    # Public
    # -------------------------------------------------------------- #

    async def validate_async(self, token: str) -> ValidationResult:
        """Async wrapper — runs the blocking call in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.validate, token)

    def validate(self, token: str) -> ValidationResult:
        token = (token or "").strip()
        if not token:
            return ValidationResult(token=token, valid=False, reason="empty token")

        if self.cfg.demo_mode:
            return self._validate_demo(token)

        if not TOKEN_RE.match(token):
            self.log.info(f"skip (format) {mask_token(token)}")
            return ValidationResult(token=token, valid=False, reason="invalid format")

        return self._validate_real(token)

    # -------------------------------------------------------------- #
    # Real path
    # -------------------------------------------------------------- #

    def _validate_real(self, token: str) -> ValidationResult:
        url = TELEGRAM_API.format(token=token)
        attempt = 0
        last_reason = "unknown error"

        proxies_dict = None
        if self.proxies:
            p_str = self.proxies[self._proxy_idx % len(self.proxies)].strip()
            self._proxy_idx += 1
            if not p_str.startswith(("http://", "https://", "socks5://", "socks4://")):
                p_str = f"http://{p_str}"
            proxies_dict = {"http": p_str, "https": p_str}

        while attempt <= self.cfg.max_retries:
            attempt += 1
            t0 = time.perf_counter()
            try:
                resp = self._session.get(url, timeout=self.cfg.request_timeout, proxies=proxies_dict)
            except requests.exceptions.Timeout:
                last_reason = "timeout"
                self._backoff(attempt, last_reason, token)
                continue
            except requests.exceptions.ConnectionError as e:
                last_reason = f"network/proxy error: {e}"
                self._backoff(attempt, "network error", token)
                continue
            except requests.exceptions.RequestException as e:
                last_reason = f"request error: {e}"
                self._backoff(attempt, "request error", token)
                continue


            latency_ms = int((time.perf_counter() - t0) * 1000)

            # 429 — honor Retry-After, then retry
            if resp.status_code == 429:
                retry_after = self._parse_retry_after(resp)
                self.log.warning(
                    f"429 on {mask_token(token)} — sleeping {retry_after:.1f}s (attempt {attempt})"
                )
                time.sleep(retry_after)
                last_reason = "rate limited"
                continue

            # 401 — bad token, no point retrying
            if resp.status_code == 401:
                return ValidationResult(
                    token=token,
                    valid=False,
                    reason="unauthorized (bad token)",
                    latency_ms=latency_ms,
                )

            # Other 5xx — retryable
            if 500 <= resp.status_code < 600:
                last_reason = f"server error {resp.status_code}"
                self._backoff(attempt, last_reason, token)
                continue

            # Non-200 that isn't a retryable class
            if resp.status_code != 200:
                return ValidationResult(
                    token=token,
                    valid=False,
                    reason=f"http {resp.status_code}",
                    latency_ms=latency_ms,
                )

            # Parse JSON
            try:
                data = resp.json()
            except ValueError:
                return ValidationResult(
                    token=token,
                    valid=False,
                    reason="non-JSON response",
                    latency_ms=latency_ms,
                )

            if not isinstance(data, dict) or not data.get("ok"):
                desc = ""
                if isinstance(data, dict):
                    desc = str(data.get("description", "")).strip()
                return ValidationResult(
                    token=token,
                    valid=False,
                    reason=desc or "api returned ok=false",
                    latency_ms=latency_ms,
                )

            r = data.get("result") or {}
            return ValidationResult(
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

        # exhausted retries
        return ValidationResult(token=token, valid=False, reason=last_reason)

    def _backoff(self, attempt: int, reason: str, token: str) -> None:
        if attempt > self.cfg.max_retries:
            return
        delay = self.cfg.retry_base_delay * (2 ** (attempt - 1))
        self.log.warning(
            f"{reason} on {mask_token(token)} — backoff {delay:.1f}s (attempt {attempt}/{self.cfg.max_retries})"
        )
        time.sleep(delay)

    @staticmethod
    def _parse_retry_after(resp: requests.Response) -> float:
        ra = resp.headers.get("Retry-After")
        if not ra:
            return 2.0
        try:
            return max(0.5, float(ra))
        except ValueError:
            return 2.0

    # -------------------------------------------------------------- #
    # Demo path
    # -------------------------------------------------------------- #

    def _validate_demo(self, token: str) -> ValidationResult:
        time.sleep(0.02)
        entry = self._DEMO_HITS.get(token)
        if entry is None:
            return ValidationResult(token=token, valid=False, reason="demo: not in fake registry")
        return ValidationResult(
            token=token,
            valid=True,
            bot_id=entry.get("id"),
            username=entry.get("username"),
            first_name=entry.get("first_name"),
            can_join_groups=entry.get("can_join_groups"),
            can_read_all_group_messages=entry.get("can_read_all_group_messages"),
            supports_inline_queries=entry.get("supports_inline_queries"),
            latency_ms=20,
        )

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


# ===================================================================== #
# Output / reporting
# ===================================================================== #

class Reporter:
    def __init__(self, color: bool) -> None:
        self.color = color
        self.hits: list[ValidationResult] = []
        self.misses: list[ValidationResult] = []

    def _c(self, code: str, text: str) -> str:
        if not self.color:
            return text
        return f"{_ANSI[code]}{text}{_ANSI['reset']}"

    def print_hit(self, r: ValidationResult) -> None:
        line = "=" * 42
        print()
        print(self._c("green", line))
        print(self._c("green", self._c("bold", "                 NEW HIT")))
        print(self._c("green", line))
        print()
        print(f"  {self._c('bold', 'Bot Token')}    : {r.token}")
        print(f"  {self._c('bold', 'Bot Username')} : @{r.username}")
        if r.first_name:
            print(f"  {self._c('bold', 'Bot Name')}     : {r.first_name}")
        if r.bot_id is not None:
            print(f"  {self._c('bold', 'Bot ID')}       : {r.bot_id}")
        flags = []
        if r.can_join_groups:
            flags.append("groups")
        if r.can_read_all_group_messages:
            flags.append("read-all")
        if r.supports_inline_queries:
            flags.append("inline")
        if flags:
            print(f"  {self._c('bold', 'Capabilities')} : {', '.join(flags)}")
        if r.latency_ms is not None:
            print(f"  {self._c('bold', 'Latency')}      : {r.latency_ms} ms")
        print()
        print(self._c("green", line))
        print()

    def print_skip(self, r: ValidationResult) -> None:
        reason = r.reason or "unknown"
        # Use ascii '[x]' to ensure cross-platform compatibility with all terminal code pages
        print(
            f"  {self._c('red', '[x]')} skip  "
            f"{mask_token(r.token):<40}  {self._c('dim', reason)}"
        )

    def record(self, r: ValidationResult) -> None:
        if r.valid:
            self.hits.append(r)
            self.print_hit(r)
        else:
            self.misses.append(r)
            self.print_skip(r)

    def summary(self) -> None:
        total = len(self.hits) + len(self.misses)
        print()
        print(self._c("cyan", "-" * 42))
        print(
            f"  {self._c('bold', 'Summary')}: "
            f"{total} checked, "
            f"{self._c('green', f'{len(self.hits)} hit')}, "
            f"{self._c('red', f'{len(self.misses)} miss')}"
        )
        print(self._c("cyan", "-" * 42))

    def export(self, csv_path: Optional[str], json_path: Optional[str]) -> None:
        rows = [asdict(r) for r in (*self.hits, *self.misses)]
        if not rows:
            return
        if csv_path:
            p = Path(csv_path)
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"  exported CSV  -> {p}")
        if json_path:
            p = Path(json_path)
            p.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  exported JSON -> {p}")


# ===================================================================== #
# Runner
# ===================================================================== #

class Runner:
    def __init__(self, cfg: Config, logger: logging.Logger, proxies: Optional[list[str]] = None) -> None:
        self.cfg = cfg
        self.log = logger
        self.validator = TokenValidator(cfg, logger, proxies=proxies)
        self.reporter = Reporter(color=cfg.color)
        self._stop = asyncio.Event()


    def _install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        def _handle(sig: int) -> None:
            self.log.warning(f"received signal {sig} — shutting down after current token")
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle, sig)
            except NotImplementedError:
                # Windows fallback
                signal.signal(sig, lambda s, _f: _handle(s))

    async def run(self) -> int:
        cfg = self.cfg
        tokens = cfg.load_tokens()
        if not tokens:
            self.log.error("no tokens to check. Set TELEGRAM_BOT_TOKEN, create tokens.txt, or use --token/--token-file.")
            return 1

        self.log.info(
            f"start — {len(tokens)} token(s), demo={cfg.demo_mode}, "
            f"concurrency={cfg.concurrency}, timeout={cfg.request_timeout}s"
        )

        loop = asyncio.get_running_loop()
        self._install_signal_handlers(loop)

        # Semaphore enforces politeness even when concurrency > 1
        sem = asyncio.Semaphore(cfg.concurrency)
        completed = 0
        lock = asyncio.Lock()

        async def worker(idx: int, token: str) -> None:
            nonlocal completed
            if self._stop.is_set():
                return
            async with sem:
                if self._stop.is_set():
                    return
                self.log.info(f"[{idx}/{len(tokens)}] checking {mask_token(token)}")
                try:
                    result = await self.validator.validate_async(token)
                except Exception as e:
                    self.log.exception(f"unexpected error on {mask_token(token)}: {e}")
                    result = ValidationResult(token=token, valid=False, reason=f"internal error: {e}")

                async with lock:
                    self.reporter.record(result)
                    completed += 1

                # polite spacing between requests
                if cfg.check_delay > 0 and completed < len(tokens) and not self._stop.is_set():
                    await asyncio.sleep(cfg.check_delay)

        tasks = [asyncio.create_task(worker(i, t)) for i, t in enumerate(tokens, start=1)]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

        if self._stop.is_set():
            self.log.warning("run stopped early by signal")

        self.reporter.summary()
        self.reporter.export(cfg.export_csv, cfg.export_json)
        self.validator.close()
        self.log.info(f"done — {completed}/{len(tokens)} checked")
        return 0


# ===================================================================== #
# CLI
# ===================================================================== #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="token-validator",
        description="Validate Telegram bot tokens or generate mock tokens for testing.",
    )
    p.add_argument("--token", action="append", default=[], help="Token to validate (repeatable)")
    p.add_argument("--token-file", help="Path to file with one token per line")
    p.add_argument("--generate", "-g", type=int, metavar="COUNT", help="Generate COUNT mock tokens for testing")
    p.add_argument("--save-generated", metavar="FILE", help="Save generated tokens to this file path")
    p.add_argument("--demo", action="store_true", help="Demo mode — no network calls")
    p.add_argument("--timeout", type=float, help="Per-request timeout (seconds)")
    p.add_argument("--delay", type=float, help="Delay between tokens (seconds)")
    p.add_argument("--concurrency", type=int, help="Max in-flight requests (default 1)")
    p.add_argument("--retries", type=int, help="Max retries per token on transient errors")
    p.add_argument("--json-logs", action="store_true", help="Emit structured JSON logs")
    p.add_argument("--log-level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--proxy-file", help="Path to file with proxy list (http://ip:port or socks5://...)")
    p.add_argument("--auto-proxies", action="store_true", help="Auto-download free public proxies for rotation")
    p.add_argument("--export-csv", help="Write results to CSV")
    p.add_argument("--export-json", help="Write results to JSON")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    return p



def merge_cli_into_env(args: argparse.Namespace) -> None:
    """CLI overrides win over env vars."""
    if args.token_file:
        os.environ["TOKEN_FILE"] = args.token_file
    if args.demo:
        os.environ["DEMO_MODE"] = "True"
    if args.timeout is not None:
        os.environ["REQUEST_TIMEOUT"] = str(args.timeout)
    if args.delay is not None:
        os.environ["CHECK_DELAY"] = str(args.delay)
    if args.concurrency is not None:
        os.environ["CONCURRENCY"] = str(args.concurrency)
    if args.retries is not None:
        os.environ["MAX_RETRIES"] = str(args.retries)
    if args.json_logs:
        os.environ["LOG_JSON"] = "True"
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level
    if args.export_csv:
        os.environ["EXPORT_CSV"] = args.export_csv
    if args.export_json:
        os.environ["EXPORT_JSON"] = args.export_json
    if args.no_color:
        os.environ["NO_COLOR"] = "1"


def prompt_interactive_mode() -> None:
    """Interactive prompt when run without CLI arguments or configured tokens."""
    print("=" * 50)
    print(" Telegram Bot Token Validator & Mock Generator")
    print("=" * 50)
    print("1. Generate mock tokens for testing")
    print("2. Validate tokens from tokens.txt or environment")
    print("3. Exit")
    try:
        choice = input("Select an option (1/2/3): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        sys.exit(0)

    if choice == "1":
        try:
            val = input("Kitne token generate karne hain? (e.g., 10, 50, 100): ").strip()
            count = int(val)
            if count <= 0:
                raise ValueError
        except ValueError:
            print("Galat number diya. Please positive integer type karein.", file=sys.stderr)
            sys.exit(1)
        save_choice = input("Save to file? (e.g. tokens.txt / leave blank for stdout): ").strip()
        generate_tokens(count, save_choice or None)
        sys.exit(0)
    elif choice == "2":
        return
    elif choice == "3":
        sys.exit(0)
    else:
        print("Invalid choice.", file=sys.stderr)
        sys.exit(1)


def main(argv: Optional[Iterable[str]] = None) -> int:
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Handle token generation CLI command
    if args.generate is not None:
        if args.generate <= 0:
            print("Error: --generate count must be greater than 0.", file=sys.stderr)
            return 1
        generate_tokens(args.generate, args.save_generated)
        return 0

    merge_cli_into_env(args)

    cfg = Config.from_env_and_cli(explicit_tokens=args.token)

    # If no tokens configured and running in an interactive terminal with no CLI args, offer menu
    if (
        not cfg.load_tokens()
        and not args.token
        and not args.token_file
        and sys.stdin.isatty()
        and (argv is None or len(list(argv)) == 0)
        and len(sys.argv) <= 1
    ):
        prompt_interactive_mode()

    proxies_list: list[str] = []
    if args.proxy_file:
        p_path = Path(args.proxy_file)
        if p_path.is_file():
            proxies_list = [l.strip() for l in p_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
    elif args.auto_proxies:
        try:
            print("Auto-fetching free public proxies for rotation...")
            resp = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=8000&country=all&ssl=all&anonymity=all", timeout=6.0)
            if resp.status_code == 200:
                proxies_list = [f"http://{l.strip()}" for l in resp.text.splitlines() if l.strip() and not l.strip().startswith("#")][:100]
                print(f"Loaded {len(proxies_list)} free proxies.")
        except Exception as e:
            print(f"Warning: Failed to auto-fetch proxies: {e}", file=sys.stderr)

    logger = setup_logger(cfg.log_level, as_json=cfg.log_json)
    runner = Runner(cfg, logger, proxies=proxies_list)

    try:
        return asyncio.run(runner.run())

    except KeyboardInterrupt:
        logger.warning("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
