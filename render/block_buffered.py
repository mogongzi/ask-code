from __future__ import annotations

import re
from typing import List, Optional


OPEN_FENCE_RE = re.compile(r"(?m)^(?P<fence>`{3,}|~{3,})[ \t]*[^\n]*\n")
CLOSE_FENCE_FMT = r"(?m)^(?:%s{3,})\s*$\n"


class BlockBuffer:
    """Accumulates streaming Markdown and yields completed blocks.

    Blocks are paragraphs (ending with \n\n) or fenced code blocks (``` or ~~~).
    """

    def __init__(self) -> None:
        self.pending: str = ""
        self.in_code: bool = False
        self._close_re: Optional[re.Pattern[str]] = None

    def feed(self, text: str) -> List[str]:
        """Feed text, returning a list of completed blocks to flush."""
        out: List[str] = []
        if not text:
            return out
        self.pending += text

        while True:
            if self.in_code:
                assert self._close_re is not None
                m = self._close_re.search(self.pending)
                if not m:
                    break
                end = m.end()
                out.append(self.pending[:end])
                self.pending = self.pending[end:]
                self.in_code = False
                self._close_re = None
                continue

            para_idx = self.pending.find("\n\n")
            m_open = OPEN_FENCE_RE.search(self.pending)

            if para_idx != -1 and (m_open is None or para_idx < m_open.start()):
                end = para_idx + 2
                out.append(self.pending[:end])
                self.pending = self.pending[end:]
                continue

            if m_open:
                start = m_open.start()
                if start > 0:
                    out.append(self.pending[:start])
                    self.pending = self.pending[start:]
                    m_open = OPEN_FENCE_RE.match(self.pending)
                    assert m_open

                fence = m_open.group("fence")[0]
                self._close_re = re.compile(CLOSE_FENCE_FMT % re.escape(fence))
                self.in_code = True
                m_close = self._close_re.search(self.pending[m_open.end():])
                if m_close:
                    end = m_open.end() + m_close.end()
                    out.append(self.pending[:end])
                    self.pending = self.pending[end:]
                    self.in_code = False
                    self._close_re = None
                    continue
                else:
                    break

            break

        return out

    def flush_remaining(self) -> Optional[str]:
        if not self.pending:
            return None
        rest = self.pending
        self.pending = ""
        self.in_code = False
        self._close_re = None
        return rest

