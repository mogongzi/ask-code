from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    # Use timezone-aware UTC timestamps and normalize to trailing Z
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _new_session_id(prefix: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}{ts}"


@dataclass
class SessionTurn:
    t: str
    user: str
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    request_1: Optional[Dict[str, Any]] = None
    assistant_first: Optional[str] = None
    tool_calls: List[dict] = field(default_factory=list)
    request_2: Optional[Dict[str, Any]] = None
    assistant_final: Optional[str] = None


class SessionRecorder:
    """Records a chat session and supports JSON persistence and Markdown export."""

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        self.version = 1
        self.id = _new_session_id()
        self.created_at = _now_iso()
        self.updated_at = self.created_at
        self.provider: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {}
        self.totals = {"tokens": 0, "cost": 0.0, "turns": 0}
        self.turns: List[SessionTurn] = []
        self._base_dir = Path(base_dir) if base_dir else Path("logs/sessions")
        self._session_dir: Optional[Path] = None

    # ---- lifecycle ----
    def start(self, *, provider_name: str, url: str, max_tokens: int, default_thinking: bool, default_tools: bool) -> None:
        self.provider = {"name": provider_name, "url": url}
        self.config = {
            "max_tokens": max_tokens,
            "default_thinking": default_thinking,
            "default_tools": default_tools,
        }

    def start_turn(self, user_text: str, context_snapshot: Optional[Dict[str, Any]] = None) -> int:
        turn = SessionTurn(t=_now_iso(), user=user_text, context_snapshot=context_snapshot or {})
        self.turns.append(turn)
        self.totals["turns"] = len(self.turns)
        self.updated_at = _now_iso()
        return len(self.turns) - 1

    def record_first_result(self, idx: int, *, model: Optional[str], tokens: int, cost: float, text: str) -> None:
        turn = self.turns[idx]
        turn.request_1 = {"model": model, "tokens": tokens, "cost": cost}
        turn.assistant_first = text
        self._accumulate(tokens, cost)

    def record_tool_calls(self, idx: int, tool_calls: List[dict]) -> None:
        if not tool_calls:
            return
        self.turns[idx].tool_calls = list(tool_calls)

    def record_followup_result(self, idx: int, *, model: Optional[str], tokens: int, cost: float, text: str) -> None:
        turn = self.turns[idx]
        turn.request_2 = {"model": model, "tokens": tokens, "cost": cost}
        turn.assistant_final = text
        self._accumulate(tokens, cost)

    def _accumulate(self, tokens: int, cost: float) -> None:
        try:
            self.totals["tokens"] += int(tokens or 0)
        except Exception:
            pass
        try:
            self.totals["cost"] = float(self.totals["cost"]) + float(cost or 0.0)
        except Exception:
            pass
        self.updated_at = _now_iso()

    # ---- persistence ----
    def session_dir(self) -> Path:
        if self._session_dir is None:
            self._session_dir = self._base_dir / self.id
            os.makedirs(self._session_dir, exist_ok=True)
        return self._session_dir

    def to_json_obj(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "config": self.config,
            "totals": self.totals,
            "turns": [
                {
                    "t": t.t,
                    "user": t.user,
                    "context_snapshot": t.context_snapshot,
                    "request_1": t.request_1,
                    "assistant_first": t.assistant_first,
                    "tool_calls": t.tool_calls,
                    "request_2": t.request_2,
                    "assistant_final": t.assistant_final,
                }
                for t in self.turns
            ],
        }

    def save_json(self, path: Optional[str | Path] = None) -> str:
        out_path = Path(path) if path else self.session_dir() / "session.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_json_obj(), f, ensure_ascii=False, indent=2)
        return str(out_path)

    # ---- export ----
    def export_markdown(self, path: Optional[str | Path] = None) -> str:
        out_path = Path(path) if path else self.session_dir() / "export.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            f.write(self._render_markdown())
        return str(out_path)

    def _render_markdown(self) -> str:
        lines: List[str] = []
        title = f"Chat Session — {self.created_at} — {self.provider.get('name','')}\n"
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"Totals: tokens={self.totals['tokens']} cost={self.totals['cost']:.6f} turns={self.totals['turns']}")
        lines.append("")
        for i, t in enumerate(self.turns, 1):
            lines.append(f"## Turn {i}")
            lines.append("")
            lines.append("### User")
            lines.append("")
            lines.append(t.user or "")
            lines.append("")
            if t.context_snapshot:
                raw_block = t.context_snapshot.get("raw_context_block")
                if raw_block:
                    lines.append("### Context")
                    lines.append("")
                    lines.append("```text")
                    lines.append(str(raw_block))
                    lines.append("```")
                    lines.append("")
            if t.assistant_first:
                lines.append("### Assistant")
                lines.append("")
                lines.append(t.assistant_first)
                lines.append("")
            if t.tool_calls:
                lines.append("### Tools")
                for tc in t.tool_calls:
                    tool_call = tc.get("tool_call", {})
                    name = tool_call.get("name", "")
                    args = tool_call.get("input", {})
                    result = tc.get("result", "")
                    lines.append(f"- {name}({json.dumps(args, ensure_ascii=False)})")
                    if result:
                        # Show result in a short fenced block
                        lines.append("")
                        lines.append("```text")
                        lines.append(str(result))
                        lines.append("```")
                lines.append("")
            if t.assistant_final:
                lines.append("### Assistant (final)")
                lines.append("")
                lines.append(t.assistant_final)
                lines.append("")
            # Usage summary
            if t.request_1 or t.request_2:
                lines.append("### Usage")
                if t.request_1:
                    r1 = t.request_1
                    lines.append(f"- First: model={r1.get('model','')} tokens={r1.get('tokens',0)} cost={r1.get('cost',0.0):.6f}")
                if t.request_2:
                    r2 = t.request_2
                    lines.append(f"- Follow-up: model={r2.get('model','')} tokens={r2.get('tokens',0)} cost={r2.get('cost',0.0):.6f}")
                lines.append("")
        return "\n".join(lines)
