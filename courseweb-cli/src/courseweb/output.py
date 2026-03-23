from __future__ import annotations

import json
from typing import Any


def render_payload(data: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(data, ensure_ascii=False, indent=2)

    if _looks_like_command_result(data):
        return _render_command_result(data)

    lines: list[str] = []
    for key, value in data.items():
        lines.extend(_render_pair(key, value))
    return "\n".join(lines)


def _looks_like_command_result(data: dict[str, Any]) -> bool:
    return {"ok", "message", "payload"}.issubset(data.keys())


def _render_command_result(data: dict[str, Any]) -> str:
    ok = bool(data.get("ok"))
    message = str(data.get("message") or "").strip()
    payload = data.get("payload")

    sections: list[str] = []
    if message:
        sections.append(message if ok else f"Error: {message}")

    if isinstance(payload, dict) and payload:
        lines: list[str] = []
        for key, value in payload.items():
            lines.extend(_render_pair(key, value))
        sections.append("\n".join(lines))
    elif payload not in ({}, None):
        sections.append(str(payload))

    if not sections:
        return "Success." if ok else "Error."

    return "\n\n".join(section for section in sections if section.strip())


def _render_pair(key: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        lines = [f"{key}:"]
        for inner_key, inner_value in value.items():
            lines.extend(f"  {line}" for line in _render_pair(inner_key, inner_value))
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{key}: []"]
        lines = [f"{key}:"]
        for item in value:
            if isinstance(item, dict):
                lines.append("  -")
                for inner_key, inner_value in item.items():
                    lines.extend(
                        f"    {line}" for line in _render_pair(inner_key, inner_value)
                    )
            else:
                lines.append(f"  - {item}")
        return lines

    return [f"{key}: {value}"]
