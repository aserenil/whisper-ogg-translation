import re
from dataclasses import dataclass


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str


def _format_timestamp(ms: int) -> str:
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, millis = divmod(ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _parse_timestamp(timestamp: str) -> int:
    hms, millis = timestamp.strip().replace(".", ",").split(",")
    hours, minutes, seconds = hms.split(":")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(millis)
    )


def segments_to_srt(segments: list[Segment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        start = _format_timestamp(segment.start_ms)
        end = _format_timestamp(segment.end_ms)
        blocks.append(f"{index}\n{start} --> {end}\n{segment.text}\n\n")
    return "".join(blocks)


def parse_srt(content: str) -> list[Segment]:
    segments = []
    for block in re.split(r"\n{2,}", content.strip()):
        if not block.strip():
            continue
        lines = block.splitlines()
        timestamp_index = next(
            (i for i, line in enumerate(lines) if " --> " in line), None
        )
        if timestamp_index is None:
            continue
        start_str, end_str = lines[timestamp_index].split(" --> ")
        text_lines = lines[timestamp_index + 1 :]
        segments.append(
            Segment(
                start_ms=_parse_timestamp(start_str),
                end_ms=_parse_timestamp(end_str),
                text="\n".join(text_lines),
            )
        )
    return segments


def segment_at(segments: list[Segment], position_ms: int) -> int | None:
    for index, segment in enumerate(segments):
        if segment.start_ms <= position_ms < segment.end_ms:
            return index
    return None
