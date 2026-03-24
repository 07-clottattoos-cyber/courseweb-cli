from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .accounts import (
    AccountError,
    credentials_for_account,
    get_default_account,
    has_saved_password,
    list_accounts,
    prompt_for_credentials,
    remove_account,
    resolve_account,
    set_default_account,
    upsert_account,
)
from .announcements import AnnouncementScrapeError, resolve_announcement, scrape_announcements
from .assignments import (
    AssignmentScrapeError,
    download_assignment,
    resolve_assignment,
    scrape_assignment_detail,
    scrape_assignments,
    submit_assignment,
)
from .auth import AuthError, DEFAULT_LOGIN_URL, login_with_playwright
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
from .session_runtime import SessionRecoveryError, ensure_live_session
from .state import (
    accounts_path,
    clear_session,
    load_session,
    save_session,
    session_path,
    storage_state_path,
    utc_now_iso,
)


class ChineseArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        add_help = kwargs.pop("add_help", True)
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "命令选项"
        if add_help:
            self.add_argument(
                "-h",
                "--help",
                action="help",
                default=argparse.SUPPRESS,
                help="显示帮助信息并退出。",
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
    shared_parser = ChineseArgumentParser(add_help=False)
    shared_parser._optionals.title = "通用输出选项"
    shared_parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果。",
    )
    shared_parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="控制人类可读输出的颜色。",
    )

    parser = ChineseArgumentParser(
        prog="pkucw",
        description="面向北大教学网的命令行工具，使用真实浏览器会话驱动各类操作。",
        epilog=(
            "常见用法：\n"
            "  pkucw login\n"
            "  pkucw ls --current\n"
            "  pkucw use \"有机化学 (一)\"\n"
            "  pkucw announcements list\n"
            "  pkucw recordings latest --output ./downloads/latest\n"
            "\n兼容别名：cw, courseweb\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared_parser],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="显示版本号并退出。",
    )

    subparsers = parser.add_subparsers(
        dest="domain",
        metavar="{completion,auth,accounts,login,logout,status,courses,ls,use,current,doctor,course,info,announcements,contents,assignments,recordings}",
    )

    add_completion_parsers(subparsers, shared_parser)
    add_auth_parsers(subparsers, shared_parser)
    add_accounts_parsers(subparsers, shared_parser)
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
        help="输出 shell 补全脚本。",
        parents=[shared_parser],
    )
    completion_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="终端 shell 类型。")
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
        help="管理登录会话。",
        parents=[shared_parser],
    )
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    login_parser = auth_subparsers.add_parser(
        "login",
        help="执行真实浏览器登录并保存会话状态。",
        parents=[shared_parser],
    )
    _add_login_arguments(login_parser)
    login_parser.set_defaults(handler=handle_auth_login)

    logout_parser = auth_subparsers.add_parser(
        "logout",
        help="清除本地会话状态。",
        parents=[shared_parser],
    )
    logout_parser.set_defaults(handler=handle_auth_logout)

    status_parser = auth_subparsers.add_parser(
        "status",
        help="查看本地会话状态。",
        parents=[shared_parser],
    )
    status_parser.set_defaults(handler=handle_auth_status)


def add_accounts_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    accounts_parser = subparsers.add_parser(
        "accounts",
        help="管理保存在 macOS 钥匙串中的账号。",
        aliases=["account"],
        parents=[shared_parser],
    )
    accounts_subparsers = accounts_parser.add_subparsers(dest="accounts_command")

    list_parser = accounts_subparsers.add_parser(
        "list",
        help="列出已保存账号。",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.set_defaults(handler=handle_accounts_list)

    show_parser = accounts_subparsers.add_parser(
        "show",
        help="查看单个已保存账号。",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("account", nargs="?", help="已保存账号的用户名或标签。")
    show_parser.set_defaults(handler=handle_accounts_show)

    add_parser = accounts_subparsers.add_parser(
        "add",
        help="添加或更新已保存账号。",
        parents=[shared_parser],
    )
    add_parser.add_argument("--username", help="要保存的北大账号。")
    add_parser.add_argument("--label", help="账号的可选备注标签。")
    add_parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="从标准输入读取密码，而不是终端交互输入。",
    )
    add_parser.add_argument(
        "--default",
        action="store_true",
        help="将该账号设为默认账号，供后续 `pkucw login` 使用。",
    )
    add_parser.set_defaults(handler=handle_accounts_add)

    use_parser = accounts_subparsers.add_parser(
        "use",
        help="设置默认账号。",
        parents=[shared_parser],
    )
    use_parser.add_argument("account", help="已保存账号的用户名或标签。")
    use_parser.set_defaults(handler=handle_accounts_use)

    remove_parser = accounts_subparsers.add_parser(
        "remove",
        help="删除已保存账号，并从 macOS 钥匙串中移除对应密码。",
        aliases=["rm", "delete"],
        parents=[shared_parser],
    )
    remove_parser.add_argument("account", help="已保存账号的用户名或标签。")
    remove_parser.set_defaults(handler=handle_accounts_remove)


def _add_login_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--account", help="已保存账号的用户名或标签。")
    parser.add_argument("--username", help="本次登录使用的北大账号。")
    parser.add_argument("--label", help="保存账号时使用的可选标签。")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="从标准输入读取密码，而不是在终端里输入。",
    )
    parser.add_argument(
        "--no-save-account",
        action="store_true",
        help="登录成功后，不保存或更新账号信息。",
    )
    parser.add_argument(
        "--login-url",
        default=DEFAULT_LOGIN_URL,
        help="教学网登录入口地址。",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="登录时显示 Chromium 浏览器窗口，而不是无头模式。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="每个登录步骤的浏览器超时时间（秒）。",
    )


def add_auth_shortcuts(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    login_parser = subparsers.add_parser(
        "login",
        help="`auth login` 的快捷入口。",
        parents=[shared_parser],
    )
    _add_login_arguments(login_parser)
    login_parser.set_defaults(handler=handle_auth_login)

    logout_parser = subparsers.add_parser(
        "logout",
        help="`auth logout` 的快捷入口。",
        parents=[shared_parser],
    )
    logout_parser.set_defaults(handler=handle_auth_logout)

    status_parser = subparsers.add_parser(
        "status",
        help="`auth status` 的快捷入口。",
        parents=[shared_parser],
    )
    status_parser.set_defaults(handler=handle_auth_status)


def add_courses_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    courses_parser = subparsers.add_parser(
        "courses",
        help="查看课程列表。",
        parents=[shared_parser],
    )
    courses_subparsers = courses_parser.add_subparsers(dest="courses_command")

    list_parser = courses_subparsers.add_parser(
        "list",
        help="列出课程。",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("--current", action="store_true", help="只显示当前学期课程。")
    list_parser.add_argument("--archived", action="store_true", help="只显示历史课程。")
    list_parser.set_defaults(handler=handle_courses_list)

    show_parser = courses_subparsers.add_parser(
        "show",
        help="查看单门课程的匹配结果。",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", help="课程 ID、短标识或标题片段。")
    show_parser.set_defaults(handler=handle_courses_show)

    current_parser = courses_subparsers.add_parser(
        "current",
        help="查看当前会话里保存的活动课程。",
        parents=[shared_parser],
    )
    current_parser.set_defaults(handler=handle_current_course)


def add_context_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    ls_parser = subparsers.add_parser(
        "ls",
        help="`courses list` 的快捷入口。",
        parents=[shared_parser],
    )
    ls_parser.add_argument("--current", action="store_true", help="只显示当前学期课程。")
    ls_parser.add_argument("--archived", action="store_true", help="只显示历史课程。")
    ls_parser.set_defaults(handler=handle_courses_list)

    use_parser = subparsers.add_parser(
        "use",
        help="设置活动课程，后续命令可省略课程参数。",
        parents=[shared_parser],
    )
    use_parser.add_argument("course", help="课程 ID、短标识或标题片段。")
    use_parser.set_defaults(handler=handle_use_course)

    current_parser = subparsers.add_parser(
        "current",
        help="查看当前活动课程上下文。",
        parents=[shared_parser],
    )
    current_parser.set_defaults(handler=handle_current_course)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="查看安装、会话和上下文诊断信息。",
        parents=[shared_parser],
    )
    doctor_parser.set_defaults(handler=handle_doctor)


def add_course_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    course_parser = subparsers.add_parser(
        "course",
        help="在单门课程内操作。",
        parents=[shared_parser],
    )
    course_subparsers = course_parser.add_subparsers(dest="course_command")

    info_parser = course_subparsers.add_parser(
        "info",
        help="查看课程元数据。",
        parents=[shared_parser],
    )
    info_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
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
        help="`course info` 的快捷入口；省略时使用当前活动课程。",
        parents=[shared_parser],
    )
    info_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
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
    resource_label = _resource_label(name)
    singular_label = _resource_singular_label(name)
    parser = course_subparsers.add_parser(
        name,
        help=f"管理{resource_label}。",
        parents=[shared_parser],
    )
    subparsers = parser.add_subparsers(dest=f"{name}_command")

    list_parser = subparsers.add_parser(
        "list",
        help=f"列出{resource_label}。",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
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
            help="以树形方式显示教学内容。",
            parents=[shared_parser],
        )
        tree_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
        tree_parser.set_defaults(handler=handle_course_contents_tree)

        show_parser = subparsers.add_parser(
            "show",
            help="查看单个教学内容。",
            aliases=["get"],
            parents=[shared_parser],
        )
        show_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
        show_parser.add_argument("content", help="教学内容 ID 或标题片段。")
        show_parser.set_defaults(handler=handle_course_contents_show)

        download_parser = subparsers.add_parser(
            "download",
            help="下载教学内容。",
            aliases=["dl"],
            parents=[shared_parser],
        )
        download_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
        download_parser.add_argument("content", help="教学内容 ID 或标题片段。")
        download_parser.add_argument(
            "--output",
            type=Path,
            help="下载文件或文件夹的可选输出路径。",
        )
        download_parser.set_defaults(handler=handle_course_contents_download)
        return

    show_parser = subparsers.add_parser(
        "show",
        help=f"查看单条{singular_label}详情。",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
    show_parser.add_argument(name[:-1], help=f"{singular_label} ID 或标题片段。")
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
        download_parser = subparsers.add_parser(
            "download",
            help="下载作业说明和附件。",
            aliases=["dl"],
            parents=[shared_parser],
        )
        download_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
        download_parser.add_argument("assignment", help="作业 ID 或标题片段。")
        download_parser.add_argument(
            "--output",
            type=Path,
            help="下载目录或输出前缀；默认使用作业标题创建目录。",
        )
        download_parser.set_defaults(handler=handle_course_assignments_download)

        submit_parser = subparsers.add_parser(
            "submit",
            help="提交 Blackboard 站内作业。",
            parents=[shared_parser],
        )
        submit_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
        submit_parser.add_argument("assignment", help="作业 ID 或标题片段。")
        submit_parser.add_argument("--file", type=Path, action="append", default=[], help="要上传的文件。")
        submit_parser.add_argument(
            "--replace-files",
            action="store_true",
            help="上传新文件前，先移除现有草稿附件。",
        )
        submit_parser.add_argument(
            "--clear-files",
            action="store_true",
            help="移除现有草稿附件，但不新增文件。",
        )
        submit_parser.add_argument("--text", help="文本提交内容。")
        submit_parser.add_argument(
            "--clear-text",
            action="store_true",
            help="清空当前草稿中的文本提交内容。",
        )
        submit_parser.add_argument("--comment", help="可选提交备注。")
        submit_parser.add_argument(
            "--clear-comment",
            action="store_true",
            help="清空当前草稿备注。",
        )
        submit_parser.add_argument(
            "--final-submit",
            action="store_true",
            help="执行真实最终提交，而不是仅保存草稿。",
        )
        submit_parser.add_argument(
            "--confirm-final-submit",
            help="`--final-submit` 的二次确认，必须与作业 ID 或标题完全一致。",
        )
        submit_parser.add_argument(
            "--save-draft",
            action="store_true",
            help="执行真实草稿保存。",
        )
        submit_parser.set_defaults(handler=handle_assignment_submit)


def add_recording_parsers(
    course_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    shared_parser: argparse.ArgumentParser,
) -> None:
    parser = course_subparsers.add_parser(
        "recordings",
        help="管理课堂实录。",
        parents=[shared_parser],
    )
    subparsers = parser.add_subparsers(dest="recordings_command")

    list_parser = subparsers.add_parser(
        "list",
        help="列出课堂实录。",
        aliases=["ls"],
        parents=[shared_parser],
    )
    list_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
    list_parser.set_defaults(handler=handle_course_recordings_list)

    show_parser = subparsers.add_parser(
        "show",
        help="查看单条课堂实录详情。",
        aliases=["get"],
        parents=[shared_parser],
    )
    show_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
    show_parser.add_argument("recording", help="课堂实录 ID 或标题片段。")
    show_parser.set_defaults(handler=handle_course_recordings_show)

    download_parser = subparsers.add_parser(
        "download",
        help="下载单条课堂实录。",
        aliases=["dl"],
        parents=[shared_parser],
    )
    download_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
    download_parser.add_argument("recording", help="课堂实录 ID 或标题片段。")
    download_parser.add_argument("--output", type=Path, help="可选输出路径。")
    download_parser.add_argument(
        "--no-remux",
        action="store_true",
        help="保留解密后的 .ts 文件，并跳过 mp4 转封装。",
    )
    download_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="不在 stderr 中显示分片下载进度。",
    )
    download_parser.set_defaults(handler=handle_course_recordings_download)

    latest_parser = subparsers.add_parser(
        "download-latest",
        help="下载最新一条课堂实录。",
        aliases=["latest"],
        parents=[shared_parser],
    )
    latest_parser.add_argument("course", nargs="?", help="课程 ID、短标识或标题片段。")
    latest_parser.add_argument("--output", type=Path, help="可选输出路径。")
    latest_parser.add_argument(
        "--no-remux",
        action="store_true",
        help="保留解密后的 .ts 文件，并跳过 mp4 转封装。",
    )
    latest_parser.add_argument(
        "--no-progress",
        action="store_true",
        help="不在 stderr 中显示分片下载进度。",
    )
    latest_parser.set_defaults(handler=handle_course_recordings_download_latest)


def handle_auth_login(args: argparse.Namespace) -> CommandResult:
    try:
        saved_account = None
        should_save_account = not args.no_save_account

        if args.account and args.username:
            return CommandResult(
                ok=False,
                message="`--account` 和 `--username` 只能二选一。",
                payload={},
            )
        if args.account and args.password_stdin:
            return CommandResult(
                ok=False,
                message="`--password-stdin` 不能和 `--account` 一起使用；已保存账号会直接从 macOS 钥匙串读取密码。",
                payload={},
            )

        if args.account:
            saved_account = resolve_account(args.account)
            credentials = credentials_for_account(saved_account)
        elif args.username or args.password_stdin:
            credentials = prompt_for_credentials(
                username=args.username,
                password_stdin=args.password_stdin,
            )
        else:
            default_account = get_default_account()
            if default_account is not None:
                saved_account = default_account
                credentials = credentials_for_account(default_account)
            else:
                credentials = prompt_for_credentials()

        artifacts = login_with_playwright(
            credentials=credentials,
            storage_state_path=storage_state_path(),
            headless=not args.show_browser,
            timeout_ms=args.timeout_seconds * 1000,
            login_url=args.login_url,
        )
    except (AuthError, AccountError) as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
            payload={
                "login_url": args.login_url,
            },
        )

    account_record = None
    if should_save_account:
        try:
            account_record = upsert_account(
                username=credentials.username,
                password=credentials.password,
                label=args.label or (saved_account.label if saved_account else None),
                make_default=True,
                mark_login=True,
            )
        except AccountError as exc:
            return CommandResult(
                ok=False,
                message=f"登录成功，但保存账号失败：{exc}",
                payload={
                    "login_url": args.login_url,
                    "final_url": artifacts.final_url,
                    "storage_state_path": artifacts.storage_state,
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
    state.account_username = credentials.username
    state.account_label = account_record.label if account_record is not None else (saved_account.label if saved_account else None)

    path = save_session(state)
    return CommandResult(
        ok=True,
        message=(
            f"浏览器登录成功，并已保存账号 {credentials.username}。"
            if account_record is not None
            else "浏览器登录成功，已保存会话状态。"
        ),
        payload={
            "session_path": str(path),
            "storage_state_path": artifacts.storage_state,
            "accounts_path": str(accounts_path()),
            "credentials_source": credentials.source,
            "final_url": artifacts.final_url,
            "account": _account_payload(account_record) if account_record is not None else None,
            "session": state.to_dict(),
        },
    )


def handle_auth_logout(args: argparse.Namespace) -> CommandResult:
    removed = clear_session()
    return CommandResult(
        ok=True,
        message="已清除本地会话状态。" if removed else "当前没有可清除的本地会话状态。",
        payload={
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "removed": removed,
        },
    )


def handle_auth_status(args: argparse.Namespace) -> CommandResult:
    state = load_session()
    accounts = list_accounts()
    default_account = next((account for account in accounts if account.is_default), None)
    return CommandResult(
        ok=True,
        message="已读取本地会话状态。" if state.configured else "未找到本地会话状态。",
        payload={
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "accounts_path": str(accounts_path()),
            "account_count": len(accounts),
            "default_account": _account_payload(default_account) if default_account is not None else None,
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
        message=f"已将活动课程设置为：{course.name}",
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
            message="当前没有活动课程，请先运行 `pkucw use <course>`。",
            payload={"session": session.to_dict()},
        )

    if session.authenticated and session.storage_state:
        course, _ = _resolve_course_from_query(session, None)
        if course is not None:
            return CommandResult(
                ok=True,
                message=f"已加载当前活动课程：{course.name}",
                payload={
                    "course": course.to_dict(),
                    "session": session.to_dict(),
                },
            )

    return CommandResult(
        ok=True,
        message="已读取本地会话中保存的活动课程。",
        payload={
            "active_course_id": session.active_course_id,
            "active_course_title": session.active_course_title,
            "session": session.to_dict(),
        },
    )


def handle_doctor(args: argparse.Namespace) -> CommandResult:
    session = load_session()
    accounts = list_accounts()
    default_account = next((account for account in accounts if account.is_default), None)
    return CommandResult(
        ok=True,
        message="已收集本地 CLI 诊断信息。",
        payload={
            "installed_commands": {
                "pkucw": True,
                "courseweb": True,
                "cw": True,
            },
            "session_path": str(session_path()),
            "storage_state_path": str(storage_state_path()),
            "accounts_path": str(accounts_path()),
            "account_count": len(accounts),
            "default_account": _account_payload(default_account) if default_account is not None else None,
            "session": session.to_dict(),
            "recommended_flow": [
                "pkucw accounts add",
                "pkucw login",
                "pkucw ls --current",
                "pkucw use <course>",
                "pkucw recordings latest",
            ],
        },
    )


def handle_accounts_list(args: argparse.Namespace) -> CommandResult:
    try:
        accounts = list_accounts()
        payload_accounts = [_account_payload(account) for account in accounts]
    except AccountError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    message = "还没有已保存账号，请先运行 `pkucw accounts add` 或 `pkucw login`。"
    if accounts:
        message = f"已加载 {len(accounts)} 个已保存账号。"
    return CommandResult(
        ok=True,
        message=message,
        payload={
            "accounts_path": str(accounts_path()),
            "count": len(payload_accounts),
            "accounts": payload_accounts,
        },
    )


def handle_accounts_show(args: argparse.Namespace) -> CommandResult:
    try:
        account = get_default_account() if not args.account else resolve_account(args.account)
        if account is None:
            return CommandResult(
                ok=False,
                message="还没有已保存账号，请先运行 `pkucw accounts add`。",
                payload={"accounts_path": str(accounts_path())},
            )
        payload_account = _account_payload(account)
    except AccountError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"已读取账号：{account.username}",
        payload={
            "accounts_path": str(accounts_path()),
            "account": payload_account,
        },
    )


def handle_accounts_add(args: argparse.Namespace) -> CommandResult:
    try:
        credentials = prompt_for_credentials(
            username=args.username,
            password_stdin=args.password_stdin,
        )
        account = upsert_account(
            username=credentials.username,
            password=credentials.password,
            label=args.label,
            make_default=args.default,
            mark_login=False,
        )
    except AccountError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    return CommandResult(
        ok=True,
        message=f"已将账号 {account.username} 保存到 macOS Keychain。",
        payload={
            "accounts_path": str(accounts_path()),
            "account": _account_payload(account),
        },
    )


def handle_accounts_use(args: argparse.Namespace) -> CommandResult:
    try:
        account = set_default_account(args.account)
    except AccountError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    session = load_session()
    if session.account_username == account.username:
        session.account_label = account.label
        session.updated_at = utc_now_iso()
        save_session(session)

    return CommandResult(
        ok=True,
        message=f"已将默认账号设置为：{account.username}",
        payload={
            "accounts_path": str(accounts_path()),
            "account": _account_payload(account),
        },
    )


def handle_accounts_remove(args: argparse.Namespace) -> CommandResult:
    try:
        account = remove_account(args.account)
    except AccountError as exc:
        return CommandResult(ok=False, message=str(exc), payload={})

    session = load_session()
    if session.account_username == account.username:
        session.account_username = None
        session.account_label = None
        session.updated_at = utc_now_iso()
        save_session(session)

    return CommandResult(
        ok=True,
        message=f"已删除账号：{account.username}",
        payload={
            "accounts_path": str(accounts_path()),
            "account": _account_payload(account),
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
        message=f"已从教学网门户加载 {len(filtered)} 门课程。",
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
        message=f"已匹配课程：{course.name}",
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
        message=f"已加载课程信息：{course.name}",
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
        message=f"已加载 {course.name} 的 {len(items)} 条作业条目。",
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
            message=f"无法匹配作业：{args.assignment}",
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
        message=f"已加载作业详情：{item.title}",
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


def handle_course_assignments_download(args: argparse.Namespace) -> CommandResult:
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
            message=f"无法匹配作业：{args.assignment}",
            payload={
                "query": args.assignment,
                "course": course.to_dict(),
                "available_assignment_count": len(items),
            },
        )

    try:
        result = download_assignment(
            storage_state_path=session.storage_state or "",
            item=item,
            output_path=str(args.output.expanduser().resolve()) if args.output else None,
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
        message=f"已下载作业内容：{item.title}",
        payload={
            "course": course.to_dict(),
            "course_page": {
                "page_title": info.page_title,
                "current_page_url": info.current_page_url,
                "current_page_label": info.current_page_label,
            },
            "download": result.to_dict(),
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
        message=f"已加载 {course.name} 的 {len(details)} 条通知。",
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
            message=f"无法匹配通知：{args.announcement}",
            payload={
                "query": args.announcement,
                "course": course.to_dict(),
                "available_announcement_count": len(details),
            },
        )

    return CommandResult(
        ok=True,
        message=f"已加载通知详情：{detail.item.title}",
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
        message=f"已加载 {course.name} 的 {len(items)} 个顶层教学内容。",
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
        message=f"已加载 {course.name} 的 {len(items)} 个教学内容节点。",
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
            message=f"无法匹配教学内容：{args.content}",
            payload={
                "query": args.content,
                "course": course.to_dict(),
                "available_content_count": len(items),
            },
        )

    return CommandResult(
        ok=True,
        message=f"已加载教学内容详情：{item.title}",
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
            message=f"无法匹配教学内容：{args.content}",
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
        message=f"已下载教学内容：{item.title}",
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
        message=f"已加载 {course.name} 的 {len(items)} 条课堂实录。",
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
            message=f"无法匹配课堂实录：{args.recording}",
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
        message=f"已加载课堂实录详情：{item.title}",
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
            message=f"无法匹配课堂实录：{args.recording}",
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
        message=f"已下载课堂实录：{item.title}",
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
            message=f"{course.name} 当前没有可用的课堂实录。",
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
        message=f"已下载 {course.name} 的最新课堂实录。",
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
            message="`--save-draft` 和 `--final-submit` 只能二选一。",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.confirm_final_submit and not args.final_submit:
        return CommandResult(
            ok=False,
            message="`--confirm-final-submit` 只能和 `--final-submit` 一起使用。",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.replace_files and not file_list:
        return CommandResult(
            ok=False,
            message="`--replace-files` 至少需要一个 `--file`。",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.replace_files and args.clear_files:
        return CommandResult(
            ok=False,
            message="文件处理模式只能二选一：`--replace-files` 或 `--clear-files`。",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.text and args.clear_text:
        return CommandResult(
            ok=False,
            message="文本模式只能二选一：`--text` 或 `--clear-text`。",
            payload={
                "course": args.course,
                "assignment": args.assignment,
            },
        )

    if args.comment and args.clear_comment:
        return CommandResult(
            ok=False,
            message="备注模式只能二选一：`--comment` 或 `--clear-comment`。",
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
            message="作业提交至少需要提供 `--file`、`--text` 或 `--comment` 之一。",
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
            message=f"无法匹配作业：{args.assignment}",
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
            message="已准备好作业提交参数，目前是 dry-run 模式，不会执行真实写入。",
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
                "recommended_next_step": "如需真实保存草稿，请重新运行并加上 `--save-draft`；如需最终提交，请使用 `--final-submit`。",
            },
        )

    if live_action == "submit":
        confirmation = (args.confirm_final_submit or "").strip()
        valid_confirmations = {value for value in (item.id, item.title) if value}
        if confirmation not in valid_confirmations:
            return CommandResult(
                ok=False,
                message="最终提交受保护。请重新运行，并让 `--confirm-final-submit` 与作业 ID 或标题完全一致。",
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
            "真实草稿保存已完成。"
            if live_action == "save" and result.ok
            else "真实最终提交已完成。"
            if live_action == "submit" and result.ok
            else "真实作业操作已完成，但带有警告。"
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
            message=f"{command_name} 已完成命令骨架，但尚未接入真实后端。",
            payload=payload,
        )

    return handler


def _resource_label(name: str) -> str:
    mapping = {
        "announcements": "课程通知",
        "contents": "教学内容",
        "assignments": "课程作业",
        "recordings": "课堂实录",
    }
    return mapping.get(name, name)


def _resource_singular_label(name: str) -> str:
    mapping = {
        "announcements": "通知",
        "contents": "教学内容条目",
        "assignments": "作业",
        "recordings": "课堂实录",
    }
    return mapping.get(name, name)


def _resource_plan_steps(name: str, action: str) -> list[str]:
    if name == "announcements":
        if action == "list":
            return [
                "打开已解析课程下的通知页面。",
                "解析通知标题、发布时间和详情链接。",
            ]
        return [
            "定位到选中的通知条目。",
            "返回完整通知正文和元数据。",
        ]

    if name == "assignments":
        if action == "list":
            return [
                "打开课程作业页面。",
                "区分 Blackboard 原生作业、外部作业和纯附件作业条目。",
            ]
        return [
            "定位到选中的作业条目。",
            "返回截止时间、分值、提交方式和当前状态。",
        ]

    return [f"实现 {name} {action} 的真实后端逻辑。"]


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
            message="既没有传入课程参数，也没有设置活动课程。请先运行 `pkucw use <course>`。",
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
            message=f"无法匹配课程：{query}。请尝试下面的候选项。",
            payload=payload,
        )
    return CommandResult(
        ok=False,
        message=f"无法匹配课程：{query}",
        payload=payload,
    )


def _account_payload(account) -> dict[str, object] | None:
    if account is None:
        return None
    payload = account.to_dict()
    try:
        payload["has_saved_password"] = has_saved_password(account)
    except AccountError:
        payload["has_saved_password"] = False
    return payload


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
    try:
        ensure_live_session(session, stale_after_seconds=0)
    except SessionRecoveryError as exc:
        return CommandResult(
            ok=False,
            message=str(exc),
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
    if next_dest == "account":
        return _account_completion_candidates()
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


def _account_completion_candidates() -> list[str]:
    suggestions: list[str] = []
    for account in list_accounts():
        suggestions.append(account.username)
        if account.label:
            suggestions.append(account.label)
    return [item for item in dict.fromkeys(suggestions) if item]
