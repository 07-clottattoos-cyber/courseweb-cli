from __future__ import annotations

import json
from typing import Any


def render_payload(data: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(data, ensure_ascii=False, indent=2)

    lines: list[str] = []
    for key, value in data.items():
        lines.extend(_render_pair(key, value))
    return "\n".join(lines)


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
