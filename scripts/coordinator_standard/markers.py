"""Byte-preserving management of the coordinator block in AGENTS.md."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .model import Blocker, CoordinatorError


_START = re.compile(
    rb"(?m)^<!-- cody-coordinator:start standard="
    rb"(?P<version>[0-9]+\.[0-9]+\.[0-9]+) -->[ \t]*(?:\r?\n|$)"
)
_END = re.compile(
    rb"(?m)^<!-- cody-coordinator:end -->[ \t]*(?:\r?\n|$)"
)
_START_PREFIX = b"<!-- cody-coordinator:start"
_END_PREFIX = b"<!-- cody-coordinator:end"


@dataclass(frozen=True)
class ManagedBlock:
    start: int
    end: int
    version: str
    body_start: int
    body_end: int


def _marker_error(code: str, message: str) -> CoordinatorError:
    return CoordinatorError(
        Blocker(
            code,
            message,
            "Repair AGENTS.md so it contains either no coordinator markers or one valid block.",
            ("AGENTS.md",),
        )
    )


def parse_managed_block(content: bytes) -> ManagedBlock | None:
    starts = list(_START.finditer(content))
    ends = list(_END.finditer(content))
    raw_start_count = content.count(_START_PREFIX)
    raw_end_count = content.count(_END_PREFIX)
    if raw_start_count == 0 and raw_end_count == 0:
        return None
    if raw_start_count != len(starts) or raw_end_count != len(ends):
        raise _marker_error(
            "managed_marker_malformed", "AGENTS.md contains a malformed coordinator marker."
        )
    if len(starts) != 1 or len(ends) != 1:
        code = "managed_marker_nested" if len(starts) > 1 and len(ends) > 1 else "managed_marker_duplicate"
        raise _marker_error(code, "AGENTS.md contains duplicate or nested coordinator markers.")
    start = starts[0]
    end = ends[0]
    if end.start() < start.end():
        raise _marker_error(
            "managed_marker_malformed", "The coordinator end marker precedes its start marker."
        )
    return ManagedBlock(
        start=start.start(),
        end=end.end(),
        version=start.group("version").decode("ascii"),
        body_start=start.end(),
        body_end=end.start(),
    )


def format_managed_block(body: bytes, *, version: str = "0.2.0") -> bytes:
    normalized_body = body if body.endswith(b"\n") else body + b"\n"
    return (
        f"<!-- cody-coordinator:start standard={version} -->\n".encode("ascii")
        + normalized_body
        + b"<!-- cody-coordinator:end -->\n"
    )


def upsert_managed_block(content: bytes, body: bytes, *, version: str = "0.2.0") -> bytes:
    block_bytes = format_managed_block(body, version=version)
    existing = parse_managed_block(content)
    if existing is not None:
        return content[: existing.start] + block_bytes + content[existing.end :]
    if not content:
        return block_bytes
    separator = b"" if content.endswith(b"\n") else b"\n"
    return content + separator + block_bytes


__all__ = [
    "CoordinatorError",
    "ManagedBlock",
    "format_managed_block",
    "parse_managed_block",
    "upsert_managed_block",
]
