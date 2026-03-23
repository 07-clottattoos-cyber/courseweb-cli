from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_LOGIN_URL = "https://course.pku.edu.cn/webapps/bb-sso-BBLEARN/login.html"
PORTAL_URL_RE = re.compile(r"https://course\.pku\.edu\.cn/webapps/portal/execute/tabs/tabAction")


class AuthError(RuntimeError):
    """Raised when real auth login cannot complete."""


@dataclass(slots=True)
class Credentials:
    username: str
    password: str
    source: str


@dataclass(slots=True)
class LoginArtifacts:
    storage_state: str
    final_url: str
    user_display: str | None


def resolve_credentials_file(explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.exists():
            raise AuthError(f"Credentials file not found: {path}")
        return path

    env_value = os.environ.get("COURSEWEB_CREDENTIALS_FILE")
    if env_value:
        path = Path(env_value).expanduser().resolve()
        if not path.exists():
            raise AuthError(f"Credentials file from COURSEWEB_CREDENTIALS_FILE not found: {path}")
        return path

    for parent in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        candidate = parent / "env.md"
        if candidate.exists():
            return candidate

    raise AuthError(
        "Could not find credentials. Pass --credentials-file, set COURSEWEB_CREDENTIALS_FILE, or place env.md in the working tree."
    )


def load_credentials(explicit: Path | None) -> Credentials:
    path = resolve_credentials_file(explicit)
    lines = path.read_text(encoding="utf-8").splitlines()
    username = lines[0].strip() if len(lines) > 0 else ""
    password = lines[1].strip() if len(lines) > 1 else ""

    if not username or not password:
        raise AuthError(f"Credentials file is missing username or password: {path}")

    return Credentials(username=username, password=password, source=str(path))


def login_with_playwright(
    *,
    credentials: Credentials,
    storage_state_path: Path,
    headless: bool,
    timeout_ms: int,
    login_url: str = DEFAULT_LOGIN_URL,
) -> LoginArtifacts:
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()

            page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_url(re.compile(r"https://iaaa\.pku\.edu\.cn/iaaa/oauth\.jsp"), timeout=timeout_ms)

            _fill_first_available(
                page,
                selectors=[
                    "#user_name",
                    'input[name="userName"]',
                    'input[placeholder="学号/职工号/手机号"]',
                    'input[placeholder="User ID / PKU Email / Cell Phone"]',
                ],
                value=credentials.username,
                timeout_ms=timeout_ms,
                field_label="username",
            )
            _fill_first_available(
                page,
                selectors=[
                    "#password",
                    'input[name="password"]',
                    'input[placeholder="密码"]',
                    'input[placeholder="Password"]',
                ],
                value=credentials.password,
                timeout_ms=timeout_ms,
                field_label="password",
            )
            page.locator("#logon_button").click()

            page.wait_for_url(PORTAL_URL_RE, timeout=timeout_ms)
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            try:
                page.wait_for_selector("main h1", timeout=5000)
            except PlaywrightTimeoutError:
                pass

            user_display = _extract_user_display(page)
            context.storage_state(path=str(storage_state_path))
            final_url = page.url

            context.close()
            browser.close()
            return LoginArtifacts(
                storage_state=str(storage_state_path),
                final_url=final_url,
                user_display=user_display,
            )
    except PlaywrightTimeoutError as exc:
        raise AuthError(f"Timed out during browser login: {exc}") from exc
    except Exception as exc:  # pragma: no cover - used for operational errors
        raise AuthError(f"Browser login failed: {exc}") from exc


def _fill_first_available(page, *, selectors: list[str], value: str, timeout_ms: int, field_label: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=min(timeout_ms, 10000))
        except PlaywrightTimeoutError:
            continue
        locator.fill(value)
        return
    raise AuthError(f"Could not find the {field_label} field on the login page.")


def _extract_user_display(page) -> str | None:
    selectors = [
        "main h1",
        "button[aria-label*='展开全局导航']",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count():
            text = locator.inner_text().strip()
            if text.startswith("欢迎，"):
                return text.removeprefix("欢迎，").strip()
            if text:
                return text.split()[0].strip()
    return None
