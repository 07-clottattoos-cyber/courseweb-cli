from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .announcements import AnnouncementScrapeError, resolve_announcement, scrape_announcements
from .assignments import (
    AssignmentScrapeError,
    resolve_assignment,
    scrape_assignment_detail,
    scrape_assignments,
    submit_assignment,
)
from .auth import AuthError, DEFAULT_LOGIN_URL, load_credentials, login_with_playwright
from .contents import ContentItem, ContentScrapeError, download_content, resolve_content, scrape_contents
from .courses import (
    CourseInfo,
    CourseRecord,
    CourseScrapeError,
    resolve_course,
    scrape_course_info,
    scrape_courses,
    suggest_courses,
)
from .models import CommandResult, SessionState
from .output import render_payload
from .recordings import (
    RecordingScrapeError,
    download_recording,
    resolve_recording,
    scrape_recording_detail,
    scrape_recordings,
)
from .state import (
    clear_session,
    load_session,
    save_session,
    session_path,
    storage_state_path,
    utc_now_iso,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    if getattr(args, "domain", None) == "__complete":
        candidates = _complete_words(build_parser(), getattr(args, "words", []))
        if candidates:
            print("\n".join(candidates))
        return 0

    result = args.handler(args)
    data = result.to_dict()
    print(
        render_payload(
            data,
            as_json=getattr(args, "json", False),
            color=getattr(args, "color", "auto"),
        )
    )
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    shared_parser = argparse.ArgumentParser(add_help=False)
    shared_parser.add_argument(
        "--json",
        action="store_true",
        help="Render command output as JSON.",
    )
    shared_parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize human-readable output.",
    )

    parser = argparse.ArgumentParser(
        prog="pkucw",
        description="CLI for PKU course.pku.edu.cn with browser-backed workflows.",
        epilog=(
            "Common flows:\n"
            "  pkucw login\n"
            "  pkucw ls --current\n"
            "  pkucw use \"有机化学 (一)\"\n"
            "  pkucw announcements list\n"
            "  pkucw recordings latest --output ./downloads/latest\n"
            "\nAliases: cw, courseweb\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared_parser],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(
        dest="domain",
        metavar="{completion,auth,login,logout,status,courses,ls,use,current,doctor,course,info,announcements,contents,assignments,recordings}",
    )

    add_completion_parsers(subparsers, shared_parser)
    add_auth_parsers(subparsers, shared_parser)
    add_auth_shortcuts(subparsers, shared_parser)
    add_courses_parsers(subparsers, shared_parser)
    add_context_parsers(subparsers, shared_parser)
    add_course_parsers(subparsers, shared_parser)
    add_top_level_course_resource_parsers(subparsers, shared_parser)

    return parser


def add_completion_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    completion_parser = subparsers.add_parser(
        "completion",
        help="Print shell completion setup code.",
        parents=[shared_parser],
    )
    completion_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="Shell name.")
    completion_parser.set_defaults(handler=handle_completion_script)

    complete_parser = subparsers.add_parser(
        "__complete",
        help=argparse.SUPPRESS,
        parents=[shared_parser],
    )
    complete_parser.add_argument("words", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    complete_parser.set_defaults(handler=handle_completion_candidates)
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions if action.dest != "__complete"
    ]


def add_auth_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    auth_parser = subparsers.add_parser(
        "auth",
        help="Manage session metadata.",
        parents=[shared_parser],
    )
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    login_parser = auth_subparsers.add_parser(
        "login",
        help="Perform a real browser-backed login and persist storage state.",
        parents=[shared_parser],
    )
    login_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Credentials file with username on line 1 and password on line 2.",
    )
    login_parser.add_argument(
        "--login-url",
        default=DEFAULT_LOGIN_URL,
        help="Login entry URL for the PKU teaching site.",
    )
    login_parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show the Chromium window during login instead of running headless.",
    )
    login_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Browser timeout for each login step.",
    )
    login_parser.set_defaults(handler=handle_auth_login)

    logout_parser = auth_subparsers.add_parser(
        "logout",
        help="Clear local session metadata.",
        parents=[shared_parser],
    )
    logout_parser.set_defaults(handler=handle_auth_logout)

    status_parser = auth_subparsers.add_parser(
        "status",
        help="Show local session metadata.",
        parents=[shared_parser],
    )
    status_parser.set_defaults(handler=handle_auth_status)


def add_auth_shortcuts(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    login_parser = subparsers.add_parser(
        "login",
        help="Shortcut for `auth login`.",
        parents=[shared_parser],
    )
    login_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Credentials file with username on line 1 and password on line 2.",
    )
    login_parser.add_argument(
        "--login-url",
        default=DEFAULT_LOGIN_URL,
        help="Login entry URL for the PKU teaching site.",
    )
    login_parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show the Chromium window during login instead of running headless.",
    )
    login_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Browser timeout for each login step.",
    )
    login_parser.set_defaults(handler=handle_auth_login)

    logout_parser = subparsers.add_parser(
        "logout",
        help="Shortcut for `auth logout`.",
        parents=[shared_parser],
    )
    logout_parser.set_defaults(handler=handle_auth_logout)

    status_parser = subparsers.add_parser(
        "status",
        help="Shortcut for `auth status`.",
        parents=[shared_parser],
    )
    status_parser.set_defaults(handler=handle_auth_status)


def add_courses_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    courses_parser = subparsers.add_parser(
        "courses",
        help="Work with course lists.",
        parents=[shared_parser],
    )
    courses_subparsers = courses_parser.add_subparsers(dest="courses_command")

    list_parser = courses_subparsers.add_parser(
        "list",
        help="List courses.",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("--current", action="store_true", help="Limit to current courses.")
    list_parser.add_argument("--archived", action="store_true", help="Limit to archived courses.")
    list_parser.set_defaults(handler=handle_courses_list)

    show_parser = courses_subparsers.add_parser(
        "show",
        help="Show a course reference.",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", help="Course identifier, slug, or title fragment.")
    show_parser.set_defaults(handler=handle_courses_show)

    current_parser = courses_subparsers.add_parser(
        "current",
        help="Show the active course stored in the local session.",
        parents=[shared_parser],
    )
    current_parser.set_defaults(handler=handle_current_course)


def add_context_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    ls_parser = subparsers.add_parser(
        "ls",
        help="Shortcut for `courses list`.",
        parents=[shared_parser],
    )
    ls_parser.add_argument("--current", action="store_true", help="Limit to current courses.")
    ls_parser.add_argument("--archived", action="store_true", help="Limit to archived courses.")
    ls_parser.set_defaults(handler=handle_courses_list)

    use_parser = subparsers.add_parser(
        "use",
        help="Set the active course so later commands can omit the course argument.",
        parents=[shared_parser],
    )
    use_parser.add_argument("course", help="Course identifier, slug, or title fragment.")
    use_parser.set_defaults(handler=handle_use_course)

    current_parser = subparsers.add_parser(
        "current",
        help="Show the currently active course context.",
        parents=[shared_parser],
    )
    current_parser.set_defaults(handler=handle_current_course)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Show install, session, and context diagnostics.",
        parents=[shared_parser],
    )
    doctor_parser.set_defaults(handler=handle_doctor)


def add_course_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    course_parser = subparsers.add_parser(
        "course",
        help="Work inside a single course.",
        parents=[shared_parser],
    )
    course_subparsers = course_parser.add_subparsers(dest="course_command")

    info_parser = course_subparsers.add_parser(
        "info",
        help="Show course metadata.",
        parents=[shared_parser],
    )
    info_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    info_parser.set_defaults(handler=handle_course_info)

    add_named_resource_parsers(
        course_subparsers,
        shared_parser,
        "announcements",
        supports_submit=False,
    )
    add_named_resource_parsers(course_subparsers, shared_parser, "contents", supports_submit=False)
    add_named_resource_parsers(
        course_subparsers,
        shared_parser,
        "assignments",
        supports_submit=True,
    )
    add_recording_parsers(course_subparsers, shared_parser)


def add_top_level_course_resource_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    info_parser = subparsers.add_parser(
        "info",
        help="Shortcut for `course info`; uses the active course when omitted.",
        parents=[shared_parser],
    )
    info_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    info_parser.set_defaults(handler=handle_course_info)

    add_named_resource_parsers(subparsers, shared_parser, "announcements", supports_submit=False)
    add_named_resource_parsers(subparsers, shared_parser, "contents", supports_submit=False)
    add_named_resource_parsers(subparsers, shared_parser, "assignments", supports_submit=True)
    add_recording_parsers(subparsers, shared_parser)


def add_named_resource_parsers(
    course_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
    name: str,
    *,
    supports_submit: bool,
) -> None:
    parser = course_subparsers.add_parser(
        name,
        help=f"Work with course {name}.",
        parents=[shared_parser],
    )
    subparsers = parser.add_subparsers(dest=f"{name}_command")

    list_parser = subparsers.add_parser(
        "list",
        help=f"List {name}.",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    if name == "assignments":
        list_parser.set_defaults(handler=handle_course_assignments_list)
    elif name == "announcements":
        list_parser.set_defaults(handler=handle_course_announcements_list)
    elif name == "contents":
        list_parser.set_defaults(handler=handle_course_contents_list)
    else:
        list_parser.set_defaults(
            handler=make_placeholder_handler(
                f"course {name} list",
                _resource_plan_steps(name, "list"),
            )
        )

    if name == "contents":
        tree_parser = subparsers.add_parser(
            "tree",
            help="Render a content tree.",
            parents=[shared_parser],
        )
        tree_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
        tree_parser.set_defaults(handler=handle_course_contents_tree)

        show_parser = subparsers.add_parser(
            "show",
            help="Show a single content item.",
            aliases=["get"],
            parents=[shared_parser],
        )
        show_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
        show_parser.add_argument("content", help="Content identifier or title fragment.")
        show_parser.set_defaults(handler=handle_course_contents_show)

        download_parser = subparsers.add_parser(
            "download",
            help="Download a content item.",
            aliases=["dl"],
            parents=[shared_parser],
        )
        download_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
        download_parser.add_argument("content", help="Content identifier or title fragment.")
        download_parser.add_argument(
            "--output",
            type=Path,
            help="Optional output path for the downloaded file or folder.",
        )
        download_parser.set_defaults(handler=handle_course_contents_download)
        return

    show_parser = subparsers.add_parser(
        "show",
        help=f"Show a single {name[:-1]}.",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    show_parser.add_argument(name[:-1], help=f"{name[:-1].capitalize()} identifier or title fragment.")
    if name == "assignments":
        show_parser.set_defaults(handler=handle_course_assignments_show)
    elif name == "announcements":
        show_parser.set_defaults(handler=handle_course_announcements_show)
    else:
        show_parser.set_defaults(
            handler=make_placeholder_handler(
                f"course {name} show",
                _resource_plan_steps(name, "show"),
            )
        )

    if supports_submit:
        submit_parser = subparsers.add_parser(
            "submit",
            help="Submit a Blackboard assignment.",
            parents=[shared_parser],
        )
        submit_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
        submit_parser.add_argument("assignment", help="Assignment identifier or title fragment.")
        submit_parser.add_argument("--file", type=Path, action="append", default=[], help="File to upload.")
        submit_parser.add_argument(
            "--replace-files",
            action="store_true",
            help="Remove existing draft attachments before uploading --file entries.",
        )
        submit_parser.add_argument(
            "--clear-files",
            action="store_true",
            help="Remove existing draft attachments without adding new ones.",
        )
        submit_parser.add_argument("--text", help="Inline text submission.")
        submit_parser.add_argument(
            "--clear-text",
            action="store_true",
            help="Clear the current draft text submission.",
        )
        submit_parser.add_argument("--comment", help="Optional submission comment.")
        submit_parser.add_argument(
            "--clear-comment",
            action="store_true",
            help="Clear the current draft comment.",
        )
        submit_parser.add_argument(
            "--final-submit",
            action="store_true",
            help="Perform a live final submit instead of a draft save.",
        )
        submit_parser.add_argument(
            "--confirm-final-submit",
            help="Second confirmation for --final-submit. Must exactly match the assignment id or title.",
        )
        submit_parser.add_argument(
            "--save-draft",
            action="store_true",
            help="Perform a live draft save.",
        )
        submit_parser.set_defaults(handler=handle_assignment_submit)


def add_recording_parsers(
    course_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    parser = course_subparsers.add_parser(
        "recordings",
        help="Work with course recordings.",
        parents=[shared_parser],
    )
    subparsers = parser.add_subparsers(dest="recordings_command")

    list_parser = subparsers.add_parser(
        "list",
        help="List recordings.",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    list_parser.set_defaults(handler=handle_course_recordings_list)

    show_parser = subparsers.add_parser(
        "show",
        help="Show a single recording.",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    show_parser.add_argument("recording", help="Recording identifier or title fragment.")
    show_parser.set_defaults(handler=handle_course_recordings_show)

    download_parser = subparsers.add_parser(
        "download",
        help="Download a single recording.",
        aliases=["dl"],
        parents=[shared_parser],
    )
    download_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    download_parser.add_argument("recording", help="Recording identifier or title fragment.")
    download_parser.add_argument("--output", type=Path, help="Optional output path.")
    download_parser.add_argument(
        "--no-remux",
        action="store_true",
        help="Keep the decrypted .ts file and skip mp4 remux.",
    )
    download_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Do not render segment download progress to stderr.",
    )
    download_parser.set_defaults(handler=handle_course_recordings_download)

    latest_parser = subparsers.add_parser(
        "download-latest",
        help="Download the latest recording.",
        aliases=["latest"],
        parents=[shared_parser],
    )
    latest_parser.add_argument("course", nargs="?", help="Course identifier, slug, or title fragment.")
    latest_parser.add_argument("--output", type=Path, help="Optional output path.")
    latest_parser.add_argument(
        "--no-remux",
        action="store_true",
        help="Keep the decrypted .ts file and skip mp4 remux.",
    )
    latest_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Do not render segment download progress to stderr.",
    )
    latest_parser.set_defaults(handler=handle_course_recordings_download_latest)


def handle_auth_login(args: argparse.Namespace) -> CommandResult:
    try:
        credentials = load_credentials(args.credentials_file)
        artifacts = login_with_playwright(
            credentials=credentials,
            storage_state_path=storage_state_path(),
            headless=not args.show_browser,
            timeout_ms=args.timeout_seconds * 1000,
            login_url=args.login_url,
        )
    except AuthError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "login_url": args.login_url,
            },
        )

    state = load_session()
    now = utc_now_iso()
    state.configured = True
    state.auth_mode = "browser"
    state.cookie_jar = None
    state.storage_state = artifacts.storage_state
    state.browser_profile = None
    state.login_url = args.login_url
    state.user_display = artifacts.user_display
    state.updated_at = now
    state.created_at = state.created_at or now
    state.last_verified_at = now
    state.authenticated = True

    path = save_session(state)
    return CommandResult(
        ok=True,
        message="Browser login succeeded and storage state was saved.",
        payload={
            "session_path": str(path),
            "storage_state_path": artifacts.storage_state,
            "credentials_source": credentials.source,
            "final_url": artifacts.final_url,
            "session": state.to_dict(),
        },
    )


def handle_auth_logout(args: argparse.Namespace) -> CommandResult:
    removed = clear_session()
    return CommandResult(
        ok=True,
        message="Cleared local session metadata." if removed else "No local session metadata was present.",
        payload={
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "removed": removed,
        },
    )


def handle_auth_status(args: argparse.Namespace) -> CommandResult:
    state = load_session()
    return CommandResult(
        ok=True,
        message="Loaded local session metadata." if state.configured else "No local session metadata found.",
        payload={
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "session": state.to_dict(),
        },
    )


def handle_use_course(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    path = _set_active_course(session, course)
    return CommandResult(
        ok=True,
        message=f"Set the active course to {course.name}.",
        payload={
            "session_path": str(path),
            "course": course.to_dict(),
        },
    )


def handle_current_course(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    if not session.active_course_id and not session.active_course_title:
        return CommandResult(
            ok=False,
            message="No active course is set. Run `pkucw use <course>` first.",
            payload={"session": session.to_dict()},
        )

    if session.authenticated and session.storage_state:
        course, _ = _resolve_course_from_query(session, None)
        if course is not None:
            return CommandResult(
                ok=True,
                message=f"Loaded the active course: {course.name}",
                payload={
                    "course": course.to_dict(),
                    "session": session.to_dict(),
                },
            )

    return CommandResult(
        ok=True,
        message="Loaded the active course stored in the local session.",
        payload={
            "active_course_id": session.active_course_id,
            "active_course_title": session.active_course_title,
            "session": session.to_dict(),
        },
    )


def handle_doctor(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    return CommandResult(
        ok=True,
        message="Collected local CLI diagnostics.",
        payload={
            "installed_commands": {
                "pkucw": True,
                "courseweb": True,
                "cw": True,
            },
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "session": session.to_dict(),
            "recommended_flow": [
                "pkucw login",
                "pkucw ls --current",
                "pkucw use <course>",
                "pkucw recordings latest",
            ],
        },
    )


def handle_completion_script(args: argparse.Namespace) -> CommandResult:
    return CommandResult(
        ok=True,
        message=_build_completion_script(args.shell),
        payload={},
    )


def handle_completion_candidates(args: argparse.Namespace) -> CommandResult:
    candidates = _complete_words(build_parser(), args.words)
    return CommandResult(
        ok=True,
        message="\n".join(candidates),
        payload={},
    )


def handle_courses_list(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    try:
        courses = scrape_courses(storage_state_path=session.storage_state or "", headless=True)
    except CourseScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    filtered = courses
    if args.current and not args.archived:
        filtered = [course for course in courses if course.status == "current"]
    elif args.archived and not args.current:
        filtered = [course for course in courses if course.status == "archived"]

    return CommandResult(
        ok=True,
        message=f"Loaded {len(filtered)} courses from the PKU portal.",
        payload={
            "count": len(filtered),
            "courses": [course.to_dict() for course in filtered],
        },
    )


def handle_courses_show(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    try:
        courses = scrape_courses(storage_state_path=session.storage_state or "", headless=True)
    except CourseScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    course = resolve_course(courses, args.course)
    if course is None:
        return _course_resolution_error(courses, args.course)

    return CommandResult(
        ok=True,
        message=f"Resolved course: {course.name}",
        payload={
            "course": course.to_dict(),
        },
    )


def handle_course_info(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info = scrape_course_info(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except CourseScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"Loaded course info for {course.name}.",
        payload=info.to_dict(),
    )


def handle_course_assignments_list(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_assignments(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except AssignmentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    return CommandResult(
        ok=True,
        message=f"Loaded {len(items)} assignment entries for {course.name}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "count": len(items),
            "assignments": [item.to_dict() for item in items],
        },
    )


def handle_course_assignments_show(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_assignments(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except AssignmentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    item = resolve_assignment(items, args.assignment)
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve assignment: {args.assignment}",
            payload={
                "query": args.assignment,
                "course": course.to_dict(),
                "available_assignment_count": len(items),
            },
        )

    try:
        detail = scrape_assignment_detail(
            storage_state_path=session.storage_state or "",
            item=item,
            headless=True,
        )
    except AssignmentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "assignment": item.to_dict(),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Loaded assignment detail for {item.title}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            **detail.to_dict(),
        },
    )


def handle_course_announcements_list(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, details = scrape_announcements(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except AnnouncementScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"Loaded {len(details)} announcements for {course.name}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "count": len(details),
            "announcements": [detail.item.to_dict() for detail in details],
        },
    )


def handle_course_announcements_show(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, details = scrape_announcements(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except AnnouncementScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    detail = resolve_announcement(details, args.announcement)
    if detail is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve announcement: {args.announcement}",
            payload={
                "query": args.announcement,
                "course": course.to_dict(),
                "available_announcement_count": len(details),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Loaded announcement detail for {detail.item.title}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            **detail.to_dict(),
        },
    )


def handle_course_contents_list(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_contents(
            storage_state_path=session.storage_state or "",
            course=course,
            recursive=False,
            headless=True,
        )
    except ContentScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"Loaded {len(items)} top-level content items for {course.name}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "count": len(items),
            "contents": [item.to_dict() for item in items],
        },
    )


def handle_course_contents_tree(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_contents(
            storage_state_path=session.storage_state or "",
            course=course,
            recursive=True,
            headless=True,
            timeout_ms=60000,
        )
    except ContentScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"Loaded {len(items)} content nodes for {course.name}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "count": len(items),
            "contents": [item.to_dict() for item in items],
        },
    )


def handle_course_contents_show(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    info, items, item, content_error = _resolve_content_from_query(
        session,
        course,
        args.content,
    )
    if content_error is not None:
        return content_error
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve content item: {args.content}",
            payload={
                "query": args.content,
                "course": course.to_dict(),
                "available_content_count": len(items),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Loaded content detail for {item.title}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "content": item.to_dict(),
        },
    )


def handle_course_contents_download(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    _, items, item, content_error = _resolve_content_from_query(
        session,
        course,
        args.content,
    )
    if content_error is not None:
        return content_error
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve content item: {args.content}",
            payload={
                "query": args.content,
                "course": course.to_dict(),
                "available_content_count": len(items),
            },
        )

    try:
        result = download_content(
            storage_state_path=session.storage_state or "",
            item=item,
            output_path=str(args.output.expanduser().resolve()) if args.output else None,
        )
    except ContentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "content": item.to_dict(),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Downloaded content for {item.title}.",
        payload={
            "course": course.to_dict(),
            "download": result.to_dict(),
        },
    )


def handle_course_recordings_list(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_recordings(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except RecordingScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"Loaded {len(items)} recordings for {course.name}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "count": len(items),
            "recordings": [item.to_dict() for item in items],
        },
    )


def handle_course_recordings_show(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        info, items = scrape_recordings(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except RecordingScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    item = resolve_recording(items, args.recording)
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve recording: {args.recording}",
            payload={
                "query": args.recording,
                "course": course.to_dict(),
                "available_recording_count": len(items),
            },
        )

    try:
        detail = scrape_recording_detail(
            storage_state_path=session.storage_state or "",
            item=item,
            headless=True,
            timeout_ms=45000,
        )
    except RecordingScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "recording": item.to_dict(),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Loaded recording detail for {item.title}.",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            **detail.to_dict(),
        },
    )


def handle_course_recordings_download(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        _, items = scrape_recordings(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except RecordingScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    item = resolve_recording(items, args.recording)
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve recording: {args.recording}",
            payload={
                "query": args.recording,
                "course": course.to_dict(),
                "available_recording_count": len(items),
            },
        )

    try:
        result = download_recording(
            storage_state_path=session.storage_state or "",
            item=item,
            output_path=str(args.output.expanduser().resolve()) if args.output else None,
            headless=True,
            timeout_ms=45000,
            remux_to_mp4=not args.no_remux,
            show_progress=not args.no_progress,
        )
    except RecordingScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "recording": item.to_dict(),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Downloaded recording for {item.title}.",
        payload={
            "course": course.to_dict(),
            "download": result.to_dict(),
        },
    )


def handle_course_recordings_download_latest(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        _, items = scrape_recordings(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except RecordingScrapeError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    if not items:
        return CommandResult(
            ok=False,
            message=f"No recordings were found for {course.name}.",
            payload={"course": course.to_dict()},
        )

    item = max(items, key=lambda current: current.recorded_at or "")

    try:
        result = download_recording(
            storage_state_path=session.storage_state or "",
            item=item,
            output_path=str(args.output.expanduser().resolve()) if args.output else None,
            headless=True,
            timeout_ms=45000,
            remux_to_mp4=not args.no_remux,
            show_progress=not args.no_progress,
        )
    except RecordingScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "recording": item.to_dict(),
            },
        )

    return CommandResult(
        ok=True,
        message=f"Downloaded the latest recording for {course.name}.",
        payload={
            "course": course.to_dict(),
            "download": result.to_dict(),
        },
    )


def handle_assignment_submit(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    auth_error = _require_authenticated_session(session)
    if auth_error is not None:
        return auth_error

    file_list = [str(item.expanduser().resolve()) for item in args.file]

    if args.save_draft and args.final_submit:
        return CommandResult(
            ok=False,
            message="Choose only one live action: --save-draft or --final-submit.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.confirm_final_submit and not args.final_submit:
        return CommandResult(
            ok=False,
            message="--confirm-final-submit only works together with --final-submit.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.replace_files and not file_list:
        return CommandResult(
            ok=False,
            message="--replace-files needs at least one --file.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.replace_files and args.clear_files:
        return CommandResult(
            ok=False,
            message="Choose only one file mutation mode: --replace-files or --clear-files.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.text and args.clear_text:
        return CommandResult(
            ok=False,
            message="Choose only one text mode: --text or --clear-text.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.comment and args.clear_comment:
        return CommandResult(
            ok=False,
            message="Choose only one comment mode: --comment or --clear-comment.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    clear_existing_files = args.clear_files or args.replace_files

    has_mutation_input = bool(
        file_list
        or args.text
        or args.comment
        or clear_existing_files
        or args.clear_text
        or args.clear_comment
    )

    if not has_mutation_input and not args.final_submit:
        return CommandResult(
            ok=False,
            message="Assignment submission needs at least one --file, --text, or --comment input.",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    course, error = _resolve_course_from_query(session, args.course)
    if error is not None:
        return error

    try:
        _, items = scrape_assignments(
            storage_state_path=session.storage_state or "",
            course=course,
            headless=True,
        )
    except AssignmentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    item = resolve_assignment(items, args.assignment)
    if item is None:
        return CommandResult(
            ok=False,
            message=f"Could not resolve assignment: {args.assignment}",
            payload={
                "query": args.assignment,
                "course": course.to_dict(),
                "available_assignment_count": len(items),
            },
        )

    live_action = None
    if args.save_draft:
        live_action = "save"
    elif args.final_submit:
        live_action = "submit"

    if live_action is None:
        return CommandResult(
            ok=True,
            message="Prepared assignment submission payload in dry-run mode. No live write was performed.",
            payload={
                "course": course.to_dict(),
                "assignment": item.to_dict(),
                "text_submission": bool(args.text),
                "attached_files": file_list,
                "replace_files": args.replace_files,
                "clear_files": args.clear_files,
                "clear_text": args.clear_text,
                "clear_comment": args.clear_comment,
                "comment": args.comment,
                "dry_run": True,
                "recommended_next_step": "Re-run with --save-draft to create a live draft, or --final-submit for a real submit.",
            },
        )

    if live_action == "submit":
        confirmation = (args.confirm_final_submit or "").strip()
        valid_confirmations = {value for value in (item.id, item.title) if value}
        if confirmation not in valid_confirmations:
            return CommandResult(
                ok=False,
                message="Final submit is protected. Re-run with --confirm-final-submit matching the exact assignment id or title.",
                payload={
                    "course": course.to_dict(),
                    "assignment": item.to_dict(),
                    "required_confirmations": sorted(valid_confirmations),
                },
            )

    try:
        result = submit_assignment(
            storage_state_path=session.storage_state or "",
            item=item,
            text=args.text,
            comment=args.comment,
            files=file_list,
            clear_existing_files=clear_existing_files,
            clear_text=args.clear_text,
            clear_comment=args.clear_comment,
            action=live_action,
            headless=True,
        )
    except AssignmentScrapeError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "course": course.to_dict(),
                "assignment": item.to_dict(),
                "requested_action": live_action,
            },
        )

    return CommandResult(
        ok=result.ok,
        message=(
            "Live draft save completed."
            if live_action == "save" and result.ok
            else "Live final submit completed."
            if live_action == "submit" and result.ok
            else "Live assignment action finished with warnings."
        ),
        payload={
            "course": course.to_dict(),
            "submission": result.to_dict(),
            "text_submission": bool(args.text),
            "attached_files": file_list,
            "replace_files": args.replace_files,
            "clear_files": args.clear_files,
            "clear_text": args.clear_text,
            "clear_comment": args.clear_comment,
            "comment": args.comment,
        },
    )


def make_placeholder_handler(command_name: str, steps: list[str]):
    def handler(args: argparse.Namespace) -> CommandResult:
        session = load_session()
        payload = {
            "command": command_name,
            "prototype": True,
            "session_configured": session.configured,
            "next_steps": steps,
            "args": _namespace_to_dict(args),
        }
        return CommandResult(
            ok=True,
            message=f"{command_name} is scaffolded but not wired to the live backend yet.",
            payload=payload,
        )

    return handler


def _resource_plan_steps(name: str, action: str) -> list[str]:
    if name == "announcements":
        if action == "list":
            return [
                "Open the announcement tool for the resolved course.",
                "Parse titles, timestamps, and announcement URLs.",
            ]
        return [
            "Resolve the selected announcement.",
            "Return the full announcement body and metadata.",
        ]

    if name == "assignments":
        if action == "list":
            return [
                "Open the course assignment content area.",
                "Classify Blackboard-native, external, and file-only assignment entries.",
            ]
        return [
            "Resolve the selected assignment entry.",
            "Return due date, points, submission mode, and current status.",
        ]

    return [f"Implement {name} {action}."]


def _namespace_to_dict(args: argparse.Namespace) -> dict[str, object]:
    return {
        key: _normalize_value(value)
        for key, value in vars(args).items()
        if key not in {"handler", "json"}
    }


def _normalize_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _resolve_course_from_query(
    session: SessionState,
    query: str | None,
) -> tuple[CourseRecord | None, CommandResult | None]:
    try:
        courses = scrape_courses(storage_state_path=session.storage_state or "", headless=True)
    except CourseScrapeError as exc:
        return None, CommandResult(
            ok=False,
            message=str(exc),
            payload={},
        )

    effective_query = (query or "").strip() or session.active_course_id or session.active_course_title
    if not effective_query:
        return None, CommandResult(
            ok=False,
            message="No course was provided and no active course is set. Run `pkucw use <course>` first.",
            payload={
                "available_course_count": len(courses),
                "session": session.to_dict(),
            },
        )

    course = resolve_course(courses, effective_query)
    if course is None:
        return None, _course_resolution_error(courses, effective_query)
    return course, None


def _set_active_course(session: SessionState, course: CourseRecord):
    session.active_course_id = course.id
    session.active_course_title = course.title
    session.updated_at = utc_now_iso()
    return save_session(session)


def _course_resolution_error(courses: list[CourseRecord], query: str) -> CommandResult:
    suggestions = suggest_courses(courses, query, limit=5)
    payload = {
        "query": query,
        "available_course_count": len(courses),
    }
    if suggestions:
        payload["suggestions"] = [course.to_dict() for course in suggestions]
        return CommandResult(
            ok=False,
            message=f"Could not resolve course: {query}. Try one of the suggested matches.",
            payload=payload,
        )
    return CommandResult(
        ok=False,
        message=f"Could not resolve course: {query}",
        payload=payload,
    )


def _resolve_content_from_query(
    session: SessionState,
    course: CourseRecord,
    query: str,
) -> tuple[CourseInfo | None, list[ContentItem], ContentItem | None, CommandResult | None]:
    try:
        info, top_level_items = scrape_contents(
            storage_state_path=session.storage_state or "",
            course=course,
            recursive=False,
            headless=True,
            timeout_ms=30000,
        )
    except ContentScrapeError as exc:
        return None, [], None, CommandResult(ok=False, message=str(exc), payload={})

    item = resolve_content(top_level_items, query)
    if item is not None:
        return info, top_level_items, item, None

    try:
        info, recursive_items = scrape_contents(
            storage_state_path=session.storage_state or "",
            course=course,
            recursive=True,
            headless=True,
            timeout_ms=60000,
        )
    except ContentScrapeError as exc:
        return None, [], None, CommandResult(ok=False, message=str(exc), payload={})

    item = resolve_content(recursive_items, query)
    return info, recursive_items, item, None


def _require_authenticated_session(session: SessionState) -> CommandResult | None:
    if not session.configured or not session.authenticated or not session.storage_state:
        return CommandResult(
            ok=False,
            message="No authenticated session is available. Run `pkucw login` first.",
            payload={
                "session_path": str(session_path()),
                "storage_state_path": str(storage_state_path()),
            },
        )
    return None


def _build_completion_script(shell: str) -> str:
    if shell == "bash":
        return """_pkucw_completion() {
  local IFS=$'\\n'
  local current="${COMP_WORDS[COMP_CWORD]}"
  COMPREPLY=($(pkucw __complete -- "${COMP_WORDS[@]:1:COMP_CWORD}" "$current"))
}
complete -o default -F _pkucw_completion pkucw
"""

    if shell == "zsh":
        return """autoload -Uz compinit >/dev/null 2>&1
if ! whence compdef >/dev/null 2>&1; then
  compinit -C >/dev/null 2>&1 || true
fi

_pkucw_completion() {
  local -a completions
  completions=("${(@f)$(pkucw __complete -- "${words[@]:2}")}")
  _describe 'pkucw values' completions
}
if whence compdef >/dev/null 2>&1; then
  compdef _pkucw_completion pkucw
fi
"""

    return """function __pkucw_complete
    set -l tokens (commandline -opc)
    set -e tokens[1]
    pkucw __complete -- $tokens
end
complete -c pkucw -f -a "(__pkucw_complete)"
"""


def _complete_words(
    parser: argparse.ArgumentParser,
    words: list[str],
) -> list[str]:
    current_parser, prefix, consumed_positionals = _resolve_completion_context(parser, words)
    suggestions: list[str] = []

    subparsers = _get_subparsers(current_parser)
    if prefix.startswith("-"):
        suggestions.extend(_collect_option_strings(current_parser))
    else:
        if subparsers is not None:
            suggestions.extend(subparsers.choices.keys())
        suggestions.extend(_dynamic_completion_candidates(current_parser, consumed_positionals))
        suggestions.extend(_collect_option_strings(current_parser))

    filtered = [item for item in suggestions if item.startswith(prefix)]
    return list(dict.fromkeys(filtered))


def _resolve_completion_context(
    parser: argparse.ArgumentParser,
    words: list[str],
) -> tuple[argparse.ArgumentParser, str, list[str]]:
    current_parser = parser
    tokens = list(words)
    prefix = tokens[-1] if tokens else ""
    consumed = tokens[:-1] if tokens else []
    consumed_positionals: list[str] = []

    for token in consumed:
        if not token or token.startswith("-"):
            continue
        subparsers = _get_subparsers(current_parser)
        if subparsers is None or token not in subparsers.choices:
            consumed_positionals.append(token)
            continue
        current_parser = subparsers.choices[token]

    return current_parser, prefix, consumed_positionals


def _get_subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _collect_option_strings(parser: argparse.ArgumentParser) -> list[str]:
    options: list[str] = []
    for action in parser._actions:
        options.extend(action.option_strings)
    return [item for item in options if item]


def _dynamic_completion_candidates(
    parser: argparse.ArgumentParser,
    consumed_positionals: list[str],
) -> list[str]:
    next_dest = _next_positional_dest(parser, consumed_positionals)
    if next_dest == "course":
        return _course_completion_candidates()
    return []


def _next_positional_dest(parser: argparse.ArgumentParser, consumed_positionals: list[str]) -> str | None:
    positionals = [
        action
        for action in parser._actions
        if not action.option_strings and not isinstance(action, argparse._SubParsersAction)
    ]
    if not positionals:
        return None

    index = min(len(consumed_positionals), len(positionals) - 1)
    return positionals[index].dest


def _course_completion_candidates() -> list[str]:
    session = load_session()
    suggestions: list[str] = []
    if session.active_course_title:
        suggestions.append(session.active_course_title)
    if session.active_course_id:
        suggestions.append(session.active_course_id)

    if session.configured and session.authenticated and session.storage_state:
        try:
            courses = scrape_courses(storage_state_path=session.storage_state, headless=True, timeout_ms=15000)
        except CourseScrapeError:
            courses = []
        for course in courses:
            suggestions.append(course.name)
            suggestions.append(course.title)
            if course.id:
                suggestions.append(course.id)

    return [item for item in dict.fromkeys(suggestions) if item]
