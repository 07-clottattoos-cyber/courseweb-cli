from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


PORTAL_HOME_URL = "https://course.pku.edu.cn/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"
COURSE_KEY_RE = re.compile(r"key=(_\d+_1)")
TERM_RE = re.compile(r"\(([^()]*(?:学年第\d学期|学年第[12]学期))\)")
RETRYABLE_ERROR_SNIPPETS = (
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_RESET",
    "ERR_NETWORK_CHANGED",
    "Timeout",
)


class CourseScrapeError(RuntimeError):
    """Raised when course scraping cannot complete."""


@dataclass(slots=True)
class CourseRecord:
    id: str | None
    title: str
    name: str
    term: str | None
    role: str
    status: str
    launcher_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "name": self.name,
            "term": self.term,
            "role": self.role,
            "status": self.status,
            "launcher_url": self.launcher_url,
        }


@dataclass(slots=True)
class CourseInfo:
    course: CourseRecord
    page_title: str
    current_page_url: str
    current_page_label: str | None
    menu_items: list[dict[str, str | None]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "course": self.course.to_dict(),
            "page_title": self.page_title,
            "current_page_url": self.current_page_url,
            "current_page_label": self.current_page_label,
            "menu_items": self.menu_items,
        }


def scrape_courses(*, storage_state_path: str, headless: bool = True, timeout_ms: int = 30000) -> list[CourseRecord]:
    try:
        data = _run_with_retries(
            lambda: _scrape_courses_once(
                storage_state_path=storage_state_path,
                headless=headless,
                timeout_ms=timeout_ms,
            )
        )
    except PlaywrightTimeoutError as exc:
        raise CourseScrapeError(f"Timed out while loading the portal page: {exc}") from exc
    except Exception as exc:  # pragma: no cover - operational fallback
        raise CourseScrapeError(f"Could not scrape courses: {exc}") from exc

    records: list[CourseRecord] = []
    for item in data.get("current", []):
        records.append(_normalize_course(item, status="current"))
    for item in data.get("archived", []):
        records.append(_normalize_course(item, status="archived"))
    return records


def scrape_course_info(
    *,
    storage_state_path: str,
    course: CourseRecord,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> CourseInfo:
    try:
        raw = _run_with_retries(
            lambda: _scrape_course_info_once(
                storage_state_path=storage_state_path,
                course=course,
                headless=headless,
                timeout_ms=timeout_ms,
            )
        )
    except PlaywrightTimeoutError as exc:
        raise CourseScrapeError(f"Timed out while loading course info: {exc}") from exc
    except Exception as exc:  # pragma: no cover - operational fallback
        raise CourseScrapeError(f"Could not scrape course info: {exc}") from exc

    return CourseInfo(
        course=course,
        page_title=raw["page_title"],
        current_page_url=raw["current_page_url"],
        current_page_label=raw["current_page_label"] or _label_from_page_title(raw["page_title"]),
        menu_items=[
            {
                "label": item["label"],
                "url": item["url"],
                "kind": _infer_menu_kind(item["url"]),
            }
            for item in raw["menu_items"]
        ],
    )


def _scrape_courses_once(*, storage_state_path: str, headless: bool, timeout_ms: int) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=storage_state_path, ignore_https_errors=True)
        page = context.new_page()
        try:
            page.goto(PORTAL_HOME_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "a[href*='execute/launcher?type=Course']",
                state="attached",
                timeout=timeout_ms,
            )
            return page.evaluate(
                """
                () => {
                  function collectSection(title) {
                    const heading = [...document.querySelectorAll('h2')].find(
                      node => (node.textContent || '').trim() === title
                    );
                    if (!heading) return [];
                    const container = heading.parentElement;
                    if (!container) return [];
                    return [...container.querySelectorAll('a[href*="execute/launcher?type=Course"]')].map(a => ({
                      title: (a.textContent || '').replace(/\\s+/g, ' ').trim(),
                      launcher_url: a.href,
                    }));
                  }

                  return {
                    current: collectSection('当前学期课程'),
                    archived: collectSection('历史课程'),
                  };
                }
                """
            )
        finally:
            context.close()
            browser.close()


def _scrape_course_info_once(
    *,
    storage_state_path: str,
    course: CourseRecord,
    headless: bool,
    timeout_ms: int,
) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=storage_state_path, ignore_https_errors=True)
        page = context.new_page()
        try:
            page.goto(course.launcher_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "nav[aria-label='Course Menu'], nav[role='navigation']",
                state="attached",
                timeout=timeout_ms,
            )
            return page.evaluate(
                """
                () => {
                  const nodes = document.querySelectorAll('nav[aria-label="Course Menu"] a, nav[role="navigation"] a');
                  const menuItems = [];
                  const seen = {};
                  for (let i = 0; i < nodes.length; i += 1) {
                    const a = nodes[i];
                    const label = (a.textContent || '').replace(/\\s+/g, ' ').trim();
                    const url = a.href || null;
                    if (!label || !url) continue;
                    if (/#$/.test(url)) continue;
                    const key = label + '||' + url;
                    if (seen[key]) continue;
                    seen[key] = true;
                    menuItems.push({ label, url });
                  }

                  const breadcrumbNodes = document.querySelectorAll('nav[aria-label="位置导航"] li');
                  const breadcrumbItems = [];
                  for (let i = 0; i < breadcrumbNodes.length; i += 1) {
                    const text = (breadcrumbNodes[i].textContent || '').replace(/\\s+/g, ' ').trim();
                    if (text) breadcrumbItems.push(text);
                  }
                  const currentPageLabel = breadcrumbItems.length ? breadcrumbItems[breadcrumbItems.length - 1] : null;

                  return {
                    page_title: document.title,
                    current_page_url: window.location.href,
                    current_page_label: currentPageLabel,
                    menu_items: menuItems,
                  };
                }
                """
            )
        finally:
            context.close()
            browser.close()


def _run_with_retries(operation: Callable[[], Any], *, attempts: int = 3, delay_seconds: float = 1.5) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_retryable_error(exc):
                raise
            time.sleep(delay_seconds * attempt)
    raise last_error or RuntimeError("retry loop ended without an error")


def _is_retryable_error(error: Exception) -> bool:
    message = str(error)
    return any(snippet in message for snippet in RETRYABLE_ERROR_SNIPPETS)


def resolve_course(courses: list[CourseRecord], needle: str) -> CourseRecord | None:
    raw = needle.strip().lower()
    if not raw:
        return None

    exact = [course for course in courses if raw in _candidate_tokens(course)]
    if exact:
        return exact[0]

    partial = [
        course
        for course in courses
        if raw in course.title.lower()
        or raw in course.name.lower()
        or (course.id and raw in course.id.lower())
    ]
    if partial:
        return partial[0]
    return None


def _candidate_tokens(course: CourseRecord) -> set[str]:
    values = {course.title.lower(), course.name.lower(), course.launcher_url.lower()}
    if course.id:
        values.add(course.id.lower())
    if course.term:
        values.add(course.term.lower())
    return values


def _normalize_course(item: dict[str, str], *, status: str) -> CourseRecord:
    title = item["title"]
    launcher_url = item["launcher_url"]
    course_id = _parse_course_id(launcher_url)
    name = _parse_course_name(title)
    term = _parse_term(title)
    return CourseRecord(
        id=course_id,
        title=title,
        name=name,
        term=term,
        role="student",
        status=status,
        launcher_url=launcher_url,
    )


def _parse_course_id(url: str) -> str | None:
    match = COURSE_KEY_RE.search(url)
    return match.group(1) if match else None


def _parse_term(title: str) -> str | None:
    match = TERM_RE.search(title)
    return match.group(1) if match else None


def _parse_course_name(title: str) -> str:
    if ": " in title:
        return title.split(": ", 1)[1]
    return title


def _infer_menu_kind(url: str | None) -> str | None:
    if not url:
        return None
    if "tool_id=_142_1" in url:
        return "announcements"
    if "tool_id=_1761_1" in url:
        return "recordings"
    if "tool_id=_162_1" in url:
        return "grades"
    if "/webapps/assignment/uploadAssignment" in url:
        return "assignment"
    if "/content/listContent.jsp" in url:
        return "content"
    if "/launchLink.jsp" in url:
        return "tool"
    return "link"


def _label_from_page_title(page_title: str) -> str | None:
    if " – " in page_title:
        return page_title.split(" – ", 1)[0].strip() or None
    return page_title.strip() or None
