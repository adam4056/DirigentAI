from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup


@dataclass
class BrowserSession:
    browser: Any
    context: Any
    page: Any


class HeadlessBrowserManager:
    """Playwright-backed browser sessions with text-first extraction for LLM use."""

    def __init__(self) -> None:
        self._playwright = None
        self._sessions: dict[str, BrowserSession] = {}

    def _ensure_playwright(self):
        if self._playwright is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError(
                    "Playwright is not installed. Install dependencies and run `python -m playwright install chromium`."
                ) from exc
            self._playwright = sync_playwright().start()
        return self._playwright

    def _get_or_create_session(self, session_id: str = "default") -> BrowserSession:
        if session_id in self._sessions:
            return self._sessions[session_id]

        playwright = self._ensure_playwright()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        session = BrowserSession(browser=browser, context=context, page=page)
        self._sessions[session_id] = session
        return session

    def navigate(self, url: str, session_id: str = "default", wait_until: str = "networkidle") -> str:
        session = self._get_or_create_session(session_id)
        session.page.goto(url, wait_until=wait_until, timeout=30000)
        title = session.page.title()
        return f"Navigated to {session.page.url} | title={title}"

    def click(self, selector: str, session_id: str = "default") -> str:
        session = self._get_or_create_session(session_id)
        session.page.locator(selector).first.click(timeout=10000)
        return f"Clicked {selector} | url={session.page.url}"

    def type_text(
        self,
        selector: str,
        text: str,
        session_id: str = "default",
        press_enter: bool = False,
        clear_first: bool = True,
    ) -> str:
        session = self._get_or_create_session(session_id)
        locator = session.page.locator(selector).first
        if clear_first:
            locator.fill(text, timeout=10000)
        else:
            locator.type(text, timeout=10000)
        if press_enter:
            locator.press("Enter")
        return f"Typed into {selector} | url={session.page.url}"

    def wait(
        self,
        session_id: str = "default",
        selector: str = "",
        timeout_ms: int = 5000,
        wait_for_network_idle: bool = False,
    ) -> str:
        session = self._get_or_create_session(session_id)
        if selector:
            session.page.wait_for_selector(selector, timeout=timeout_ms)
            return f"Selector ready: {selector}"
        if wait_for_network_idle:
            session.page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return "Page reached network idle state."
        session.page.wait_for_timeout(timeout_ms)
        return f"Waited {timeout_ms} ms."

    def extract_text(self, session_id: str = "default", max_chars: int = 8000) -> str:
        session = self._get_or_create_session(session_id)
        html = session.page.content()
        text = self._clean_html(html)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n...[truncated]"
        title = session.page.title()
        return f"TITLE: {title}\nURL: {session.page.url}\n\n{text}"

    def list_links(self, session_id: str = "default", limit: int = 50) -> str:
        session = self._get_or_create_session(session_id)
        links = session.page.locator("a[href]")
        count = min(links.count(), limit)
        items: list[str] = []
        for index in range(count):
            link = links.nth(index)
            href = link.get_attribute("href") or ""
            label = (link.inner_text(timeout=1000) or "").strip()
            label = re.sub(r"\s+", " ", label)
            if href:
                items.append(f"- {label or '[no text]'} -> {href}")
        return "\n".join(items) if items else "No links found."

    def close(self, session_id: str = "default") -> str:
        session = self._sessions.pop(session_id, None)
        if not session:
            return f"Session '{session_id}' does not exist."
        session.context.close()
        session.browser.close()
        return f"Closed browser session '{session_id}'."

    def shutdown(self) -> None:
        for session_id in list(self._sessions.keys()):
            self.close(session_id)
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "img", "iframe"]):
            tag.decompose()

        preferred = (
            soup.find("main")
            or soup.find("article")
            or soup.find(attrs={"role": "main"})
            or soup.body
            or soup
        )

        lines: list[str] = []
        for element in preferred.find_all(["h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "blockquote", "pre", "code"]):
            text = element.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue
            if element.name in {"h1", "h2", "h3", "h4"}:
                lines.append(f"\n{text.upper()}\n")
            elif element.name == "li":
                lines.append(f"- {text}")
            else:
                lines.append(text)

        if not lines:
            fallback = preferred.get_text("\n", strip=True)
            fallback = re.sub(r"\n{3,}", "\n\n", fallback)
            fallback = re.sub(r"[ \t]+", " ", fallback)
            return fallback.strip()

        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
