#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent.parent
COURSES_DIR = ROOT / "courses"
INBOX_DIR = ROOT / "inbox"
LOGS_DIR = ROOT / "logs"
TMP_DIR = ROOT / "tmp"
MODELS_DIR = ROOT / "models"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_CDP_COOKIE_URLS = [
    "https://onlineroomse.pku.edu.cn/",
    "https://resourcese.pku.edu.cn/",
]
MODEL_ALIASES = {
    "tiny-local": MODELS_DIR / "faster-whisper-tiny",
}


def safe_name(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "untitled"
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "untitled"


def ensure_layout() -> None:
    for path in (COURSES_DIR, INBOX_DIR, LOGS_DIR, TMP_DIR, MODELS_DIR):
        path.mkdir(parents=True, exist_ok=True)


@dataclass
class CoursePaths:
    root: Path
    recordings: Path
    transcripts: Path
    metadata: Path
    notes: Path


def ensure_course(course_name: str) -> CoursePaths:
    ensure_layout()
    course_dir = COURSES_DIR / safe_name(course_name)
    recordings = course_dir / "recordings"
    transcripts = course_dir / "transcripts"
    metadata = course_dir / "metadata"
    notes = course_dir / "notes"
    for path in (course_dir, recordings, transcripts, metadata, notes):
        path.mkdir(parents=True, exist_ok=True)
    course_meta_path = metadata / "course.json"
    if not course_meta_path.exists():
        course_meta_path.write_text(
            json.dumps(
                {
                    "course_name": course_name,
                    "folder_name": course_dir.name,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    index_path = notes / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "\n".join(
                [
                    f"# {course_name}",
                    "",
                    "## Suggested Notes",
                    "",
                    "- announcements: recent notices and deadlines",
                    "- materials: handouts, references, and reading lists",
                    "- tasks: homework, lab work, checkpoints, due dates",
                    "- recordings: playback sessions, summaries, and transcript links",
                    "- grades: visible grading items or score snapshots",
                    "- discussion: Q&A and collaboration notes",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return CoursePaths(course_dir, recordings, transcripts, metadata, notes)


def lesson_stem(lesson_title: str, recorded_at: str | None) -> str:
    prefix = ""
    if recorded_at:
        try:
            prefix = datetime.fromisoformat(recorded_at.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            prefix = safe_name(recorded_at)[:10]
    lesson_part = safe_name(lesson_title)
    if prefix:
        return f"{prefix}--{lesson_part}"
    return lesson_part


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def load_note_content(content: str | None, content_file: str | None) -> str:
    if content_file:
        return Path(content_file).expanduser().read_text(encoding="utf-8").strip()
    return (content or "").strip()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def count_files(path: Path, pattern: str) -> int:
    return sum(1 for _ in path.glob(pattern))


def run(cmd: List[str], dry_run: bool = False) -> str:
    print("+", " ".join(cmd), file=sys.stderr)
    if dry_run:
        return ""
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout.strip()


def load_cdp_targets(cdp_url: str) -> list[dict]:
    with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/list") as response:
        return json.load(response)


async def _grab_cdp_cookies(ws_url: str, cookie_urls: list[str]) -> list[dict]:
    from websockets.asyncio.client import connect

    async with connect(ws_url, max_size=None) as ws:
        message_id = 0

        async def call(method: str, params: dict | None = None) -> dict:
            nonlocal message_id
            message_id += 1
            payload = {"id": message_id, "method": method}
            if params is not None:
                payload["params"] = params
            await ws.send(json.dumps(payload))
            while True:
                reply = json.loads(await ws.recv())
                if reply.get("id") == message_id:
                    return reply

        await call("Network.enable")
        reply = await call("Network.getCookies", {"urls": cookie_urls})
        return reply.get("result", {}).get("cookies", [])


def export_cdp_cookies(cdp_url: str, cookie_urls: list[str], page_url_hint: str | None) -> Path:
    targets = load_cdp_targets(cdp_url)
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if page_url_hint:
        hinted = [page for page in pages if page_url_hint in (page.get("url") or "")]
        if hinted:
            pages = hinted
    if not pages:
        raise SystemExit(f"No debuggable Chrome page found at {cdp_url}")

    cookies = asyncio.run(_grab_cdp_cookies(pages[0]["webSocketDebuggerUrl"], cookie_urls))
    if not cookies:
        raise SystemExit(
            "No cookies were exported from Chrome DevTools. "
            "Open the playback page in the DevTools-backed Chrome profile first."
        )

    tmp_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".cookies.txt")
    with tmp_file as handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            domain = cookie.get("domain") or ""
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if cookie.get("secure") else "FALSE"
            expires = int(cookie.get("expires", 0)) if cookie.get("expires", -1) > 0 else 0
            path = cookie.get("path") or "/"
            handle.write(
                "\t".join(
                    [
                        domain,
                        include_subdomains,
                        path,
                        secure,
                        str(expires),
                        cookie["name"],
                        cookie["value"],
                    ]
                )
                + "\n"
            )
    return Path(tmp_file.name)


def render_srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_outputs(base_path: Path, transcript_segments: Iterable[dict], info: dict) -> None:
    segments = list(transcript_segments)
    txt_path = base_path.with_suffix(".txt")
    srt_path = base_path.with_suffix(".srt")
    json_path = base_path.with_suffix(".json")

    txt_path.write_text(
        "\n".join(seg["text"].strip() for seg in segments if seg["text"].strip()) + "\n",
        encoding="utf-8",
    )

    srt_chunks = []
    for idx, seg in enumerate(segments, start=1):
        srt_chunks.append(
            f"{idx}\n{render_srt_timestamp(seg['start'])} --> {render_srt_timestamp(seg['end'])}\n{seg['text'].strip()}\n"
        )
    srt_path.write_text("\n".join(srt_chunks), encoding="utf-8")

    payload = {"info": info, "segments": segments}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def transcribe_media(input_path: Path, output_base: Path, model_name: str) -> dict:
    from faster_whisper import WhisperModel

    resolved_model = resolve_model_name(model_name)
    model = WhisperModel(resolved_model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(input_path), beam_size=5, vad_filter=True)
    segment_dicts = []
    for seg in segments:
        segment_dicts.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            }
        )
    info_dict = {
        "language": getattr(info, "language", None),
        "duration": getattr(info, "duration", None),
        "duration_after_vad": getattr(info, "duration_after_vad", None),
        "model": model_name,
        "resolved_model": str(resolved_model),
        "input_path": str(input_path),
    }
    write_outputs(output_base, segment_dicts, info_dict)
    return info_dict


def resolve_model_name(model_name: str) -> str:
    alias_path = MODEL_ALIASES.get(model_name)
    if alias_path and alias_path.exists():
        return str(alias_path)
    return model_name


def cmd_init(args: argparse.Namespace) -> int:
    ensure_layout()
    print(ROOT)
    return 0


def cmd_ensure_course(args: argparse.Namespace) -> int:
    course = ensure_course(args.course_name)
    print(
        json.dumps(
            {
                "course_root": str(course.root),
                "recordings": str(course.recordings),
                "transcripts": str(course.transcripts),
                "metadata": str(course.metadata),
                "notes": str(course.notes),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    ensure_layout()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")
    output_base = Path(args.output_base).expanduser().resolve() if args.output_base else input_path.with_suffix("")
    info = transcribe_media(input_path, output_base, args.model)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_ingest_recording(args: argparse.Namespace) -> int:
    course = ensure_course(args.course_name)
    stem = lesson_stem(args.lesson_title, args.recorded_at)
    output_template = str(course.recordings / f"{stem}.%(ext)s")
    cookie_file: Path | None = None

    cmd = [
        args.ytdlp_path,
        "--no-progress",
        "--no-part",
        "--newline",
        "--merge-output-format",
        "mp4",
        "--print",
        "after_move:filepath",
        "-o",
        output_template,
    ]
    if args.auth_source == "cdp":
        cookie_file = export_cdp_cookies(args.cdp_url, args.cdp_cookie_url, args.cdp_page_url_hint)
        cmd.extend(["--cookies", str(cookie_file)])
    if args.dry_run:
        cmd.append("--simulate")
    cmd.append(args.source_url)
    try:
        stdout = run(cmd, dry_run=args.dry_run)
    finally:
        if cookie_file and cookie_file.exists():
            cookie_file.unlink()

    if args.dry_run:
        media_path = course.recordings / f"{stem}.mp4"
    else:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        media_path = Path(lines[-1]).expanduser().resolve() if lines else course.recordings / f"{stem}.mp4"

    metadata = {
        "course_name": args.course_name,
        "lesson_title": args.lesson_title,
        "recorded_at": args.recorded_at,
        "teacher": args.teacher,
        "source_url": args.source_url,
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        "media_path": str(media_path),
        "transcribe_model": None if args.no_transcribe or args.dry_run else args.model,
    }
    metadata_path = course.metadata / f"{stem}.json"
    write_json(metadata_path, metadata)

    if not args.no_transcribe and not args.dry_run:
        transcript_base = course.transcripts / stem
        transcript_info = transcribe_media(media_path, transcript_base, args.model)
        metadata["transcript"] = transcript_info
        write_json(metadata_path, metadata)

    print(json.dumps({"media_path": str(media_path), "metadata_path": str(metadata_path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_append_note(args: argparse.Namespace) -> int:
    course = ensure_course(args.course_name)
    content = load_note_content(args.content, args.content_file)
    if not content:
        raise SystemExit("Note content is empty.")
    slug = safe_name(args.slug or args.title or args.kind or "note")
    filename = f"{timestamp_slug()}--{safe_name(args.kind)}--{slug}.md"
    note_path = course.notes / filename
    body = [
        f"# {args.title or args.kind}",
        "",
        f"- kind: {args.kind}",
        f"- course: {args.course_name}",
        f"- captured_at: {datetime.now().isoformat(timespec='seconds')}",
    ]
    if args.source_url:
        body.append(f"- source_url: {args.source_url}")
    body.extend(["", content.strip(), ""])
    note_path.write_text("\n".join(body), encoding="utf-8")
    print(json.dumps({"note_path": str(note_path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_course_status(args: argparse.Namespace) -> int:
    course = ensure_course(args.course_name)
    status = {
        "course_name": args.course_name,
        "course_root": str(course.root),
        "recordings": count_files(course.recordings, "*"),
        "transcripts_txt": count_files(course.transcripts, "*.txt"),
        "transcripts_srt": count_files(course.transcripts, "*.srt"),
        "transcripts_json": count_files(course.transcripts, "*.json"),
        "metadata_files": count_files(course.metadata, "*.json"),
        "notes_files": count_files(course.notes, "*.md"),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage PKU CourseWeb recordings and transcripts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the standard CourseWeb workspace layout.")
    init_parser.set_defaults(func=cmd_init)

    ensure_course_parser = subparsers.add_parser("ensure-course", help="Create the standard folder layout for one course.")
    ensure_course_parser.add_argument("--course-name", required=True)
    ensure_course_parser.set_defaults(func=cmd_ensure_course)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe an existing media file.")
    transcribe_parser.add_argument("--input", required=True, help="Path to a local media file.")
    transcribe_parser.add_argument("--output-base", help="Output path without extension for transcript files.")
    transcribe_parser.add_argument(
        "--model",
        default=os.environ.get("COURSEWEB_TRANSCRIBE_MODEL", "tiny-local"),
        help="faster-whisper model name or local alias. Default: tiny-local",
    )
    transcribe_parser.set_defaults(func=cmd_transcribe)

    ingest_parser = subparsers.add_parser("ingest-recording", help="Download one recording and optionally transcribe it.")
    ingest_parser.add_argument("--course-name", required=True)
    ingest_parser.add_argument("--lesson-title", required=True)
    ingest_parser.add_argument("--source-url", required=True, help="Usually the playlist.m3u8 URL captured from network requests.")
    ingest_parser.add_argument("--recorded-at", help="Recorded time, e.g. 2026-03-20 15:10:00")
    ingest_parser.add_argument("--teacher", help="Teacher name")
    ingest_parser.add_argument(
        "--model",
        default=os.environ.get("COURSEWEB_TRANSCRIBE_MODEL", "tiny-local"),
        help="faster-whisper model name or local alias. Default: tiny-local",
    )
    ingest_parser.add_argument("--ytdlp-path", default="/opt/homebrew/bin/yt-dlp")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Validate parameters and yt-dlp invocation without downloading.")
    ingest_parser.add_argument("--no-transcribe", action="store_true", help="Skip transcription after download.")
    ingest_parser.add_argument(
        "--auth-source",
        choices=["none", "cdp"],
        default="cdp",
        help="How to authenticate recording downloads. Default: cdp",
    )
    ingest_parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help=f"Chrome DevTools JSON endpoint. Default: {DEFAULT_CDP_URL}",
    )
    ingest_parser.add_argument(
        "--cdp-cookie-url",
        action="append",
        default=list(DEFAULT_CDP_COOKIE_URLS),
        help="URL whose cookies should be exported from the DevTools session. Can be passed multiple times.",
    )
    ingest_parser.add_argument(
        "--cdp-page-url-hint",
        default="playVideo.action",
        help="Prefer a DevTools page whose URL contains this string when exporting cookies.",
    )
    ingest_parser.set_defaults(func=cmd_ingest_recording)

    note_parser = subparsers.add_parser("append-note", help="Write a markdown note into one course note folder.")
    note_parser.add_argument("--course-name", required=True)
    note_parser.add_argument("--kind", required=True, help="For example: announcements, materials, tasks, recordings, grades, discussion.")
    note_parser.add_argument("--title", help="Human-readable note title.")
    note_parser.add_argument("--slug", help="Optional short slug for the file name.")
    note_parser.add_argument("--content", help="Inline note content.")
    note_parser.add_argument("--content-file", help="Path to a markdown or text file to ingest.")
    note_parser.add_argument("--source-url", help="Optional source page URL.")
    note_parser.set_defaults(func=cmd_append_note)

    status_parser = subparsers.add_parser("course-status", help="Show how much content has been stored for one course.")
    status_parser.add_argument("--course-name", required=True)
    status_parser.set_defaults(func=cmd_course_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
