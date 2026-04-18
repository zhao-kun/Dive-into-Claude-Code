#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    import fitz
except ImportError as exc:  # pragma: no cover - exercised in runtime, not tests.
    raise SystemExit(
        "PyMuPDF is required. Install it with `python -m pip install -r requirements-pdf.txt`."
    ) from exc


INLINE_SPACE_RE = re.compile(r"[ \t]+")
MULTI_BLANK_RE = re.compile(r"\n{3,}")
BULLET_RE = re.compile(r"^(?:[-+*•])\s+(?P<content>.+)$")
ORDERED_RE = re.compile(r"^(?P<index>\d+)[.)]\s+(?P<content>.+)$")
SECTION_RE = re.compile(r"^\d+(?:\.\d+)*\s+")
PAGE_NUMBER_RE = re.compile(r"^\d+$")
FIGURE_CAPTION_RE = re.compile(r"^Figure\s+(?P<number>\d+)\b")
LIGATURES = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}
FIGURE_IMAGE_PATHS = {
    1: "../assets/main_structure.png",
    2: "../assets/iteration.png",
    3: "../assets/layered_architecture.png",
    4: "../assets/permission.png",
    5: "../assets/extensibility.png",
    6: "../assets/context.png",
    7: "../assets/subagent.png",
    8: "../assets/session_compact.png",
    9: "../assets/package_structure.png",
}


@dataclass(frozen=True)
class Line:
    page_number: int
    page_height: float
    text: str
    size: float
    is_bold: bool
    y0: float
    y1: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PDF into normalized Markdown with stable heading and paragraph formatting."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to the source PDF file")
    parser.add_argument(
        "output_md",
        type=Path,
        nargs="?",
        help="Path to the generated Markdown file (defaults to the PDF stem with .md)",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    for source, target in LIGATURES.items():
        text = text.replace(source, target)
    text = text.replace("\u00a0", " ")
    text = INLINE_SPACE_RE.sub(" ", text)
    return text.strip()


def weighted_average_size(spans: Sequence[dict]) -> float:
    weighted_total = 0.0
    total_chars = 0

    for span in spans:
        span_text = normalize_text(span.get("text", ""))
        if not span_text:
            continue
        weight = max(len(span_text), 1)
        weighted_total += float(span.get("size", 0.0)) * weight
        total_chars += weight

    if total_chars == 0:
        return 0.0

    return weighted_total / total_chars


def span_is_bold(span: dict) -> bool:
    font_name = str(span.get("font", "")).lower()
    return "bold" in font_name or "black" in font_name or "heavy" in font_name


def extract_lines(pdf_path: Path) -> list[Line]:
    document = fitz.open(pdf_path)
    lines: list[Line] = []

    try:
        for page_index, page in enumerate(document):
            page_data = page.get_text("dict")
            page_height = float(page.rect.height)
            blocks = sorted(
                (block for block in page_data.get("blocks", []) if block.get("type") == 0),
                key=lambda block: (round(block.get("bbox", [0, 0, 0, 0])[1], 2), round(block.get("bbox", [0, 0, 0, 0])[0], 2)),
            )

            for block in blocks:
                for raw_line in block.get("lines", []):
                    spans = raw_line.get("spans", [])
                    text = normalize_text("".join(span.get("text", "") for span in spans))
                    if not text:
                        continue

                    bbox = raw_line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    lines.append(
                        Line(
                            page_number=page_index + 1,
                            page_height=page_height,
                            text=text,
                            size=weighted_average_size(spans),
                            is_bold=any(span_is_bold(span) for span in spans),
                            y0=float(bbox[1]),
                            y1=float(bbox[3]),
                        )
                    )
    finally:
        document.close()

    return lines


def remove_repeated_page_furniture(lines: Sequence[Line]) -> list[Line]:
    by_page: dict[int, list[Line]] = defaultdict(list)
    for line in lines:
        by_page[line.page_number].append(line)

    total_pages = len(by_page)
    if total_pages <= 2:
        return list(lines)

    repeated_counts: Counter[str] = Counter()
    for page_lines in by_page.values():
        for line in page_lines:
            in_top_margin = line.y0 <= 72
            in_bottom_margin = line.y1 >= line.page_height - 72
            if in_top_margin or in_bottom_margin:
                repeated_counts[line.text] += 1

    repeated_texts = {
        text
        for text, count in repeated_counts.items()
        if count >= max(3, total_pages // 3) and len(text) >= 3
    }

    cleaned: list[Line] = []
    for line in lines:
        if line.text in repeated_texts and (line.y0 <= 72 or line.y1 >= line.page_height - 72):
            continue
        if PAGE_NUMBER_RE.fullmatch(line.text) and (line.y0 <= 72 or line.y1 >= line.page_height - 72):
            continue
        cleaned.append(line)

    return cleaned


def body_font_size(lines: Sequence[Line]) -> float:
    frequencies: Counter[float] = Counter()
    for line in lines:
        rounded_size = round(line.size, 1)
        if rounded_size <= 0:
            continue
        frequencies[rounded_size] += max(len(line.text), 1)

    if not frequencies:
        return 12.0

    return frequencies.most_common(1)[0][0]


def heading_size_map(lines: Sequence[Line], body_size: float) -> dict[float, int]:
    candidate_sizes = sorted({round(line.size, 1) for line in lines if line.size >= body_size + 0.8}, reverse=True)
    heading_levels: dict[float, int] = {}
    for index, size in enumerate(candidate_sizes[:4], start=1):
        heading_levels[size] = index
    return heading_levels


def is_heading(line: Line, body_size: float, heading_levels: dict[float, int]) -> bool:
    rounded_size = round(line.size, 1)
    if rounded_size in heading_levels and len(line.text) <= 160:
        return True

    if line.is_bold and len(line.text) <= 90 and not line.text.endswith("."):
        if SECTION_RE.match(line.text):
            return True
        if line.size >= body_size + 0.2:
            return True

    return False


def is_list_item(text: str) -> bool:
    return BULLET_RE.match(text) is not None or ORDERED_RE.match(text) is not None


def paragraph_break(previous: Line, current: Line, body_size: float) -> bool:
    if current.page_number != previous.page_number:
        return True

    vertical_gap = current.y0 - previous.y1
    if vertical_gap > max(body_size * 0.9, 8.0):
        return True

    if is_list_item(current.text):
        return True

    return False


def merge_paragraph(parts: Sequence[str]) -> str:
    merged = ""
    for part in parts:
        if not merged:
            merged = part
            continue

        if merged.endswith("-") and part[:1].islower():
            merged = merged[:-1] + part
            continue

        merged = f"{merged} {part}"

    return normalize_text(merged)


def format_list_item(text: str) -> str:
    bullet_match = BULLET_RE.match(text)
    if bullet_match:
        return f"- {bullet_match.group('content').strip()}"

    ordered_match = ORDERED_RE.match(text)
    if ordered_match:
        return f"{ordered_match.group('index')}. {ordered_match.group('content').strip()}"

    return text


def heading_level(block: str) -> int | None:
    match = re.match(r"^(#{1,6})\s+(.+)$", block)
    if not match:
        return None
    return len(match.group(1))


def heading_text(block: str) -> str | None:
    match = re.match(r"^#{1,6}\s+(.+)$", block)
    if not match:
        return None
    return match.group(1)


def normalize_heading_blocks(blocks: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    index = 0

    while index < len(blocks):
        current = blocks[index]
        current_level = heading_level(current)
        current_text = heading_text(current)

        if (
            current_level is not None
            and current_text is not None
            and index + 1 < len(blocks)
        ):
            next_block = blocks[index + 1]
            next_level = heading_level(next_block)
            next_text = heading_text(next_block)

            if next_level is not None and next_text is not None:
                should_merge_title = index == 0 and current_level <= 2 and next_level <= 2
                should_merge_section = current_text.isdigit() and current_level == next_level
                if should_merge_title or should_merge_section:
                    merged_level = min(current_level, next_level)
                    normalized.append(f"{'#' * merged_level} {current_text} {next_text}")
                    index += 2
                    continue

        normalized.append(current)
        index += 1

    return normalized


def insert_figure_images(blocks: Sequence[str]) -> list[str]:
    with_images: list[str] = []

    for block in blocks:
        figure_match = FIGURE_CAPTION_RE.match(block)
        if figure_match:
            figure_number = int(figure_match.group("number"))
            image_path = FIGURE_IMAGE_PATHS.get(figure_number)
            if image_path:
                with_images.append(f"![{block}]({image_path})")

        with_images.append(block)

    return with_images


def render_markdown(lines: Sequence[Line]) -> str:
    cleaned_lines = remove_repeated_page_furniture(lines)
    body_size = body_font_size(cleaned_lines)
    heading_levels = heading_size_map(cleaned_lines, body_size)

    blocks: list[str] = []
    paragraph_parts: list[str] = []
    previous_body_line: Line | None = None
    active_list_item: str | None = None
    active_list_line: Line | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph_parts, previous_body_line
        if paragraph_parts:
            blocks.append(merge_paragraph(paragraph_parts))
            paragraph_parts = []
        previous_body_line = None

    def flush_list_item() -> None:
        nonlocal active_list_item, active_list_line
        if active_list_item:
            blocks.append(active_list_item)
        active_list_item = None
        active_list_line = None

    for line in cleaned_lines:
        if is_heading(line, body_size, heading_levels):
            flush_paragraph()
            flush_list_item()
            level = heading_levels.get(round(line.size, 1), 3)
            blocks.append(f"{'#' * min(level, 4)} {line.text}")
            continue

        if is_list_item(line.text):
            flush_paragraph()
            flush_list_item()
            active_list_item = format_list_item(line.text)
            active_list_line = line
            continue

        if active_list_item and active_list_line:
            same_page = line.page_number == active_list_line.page_number
            vertical_gap = line.y0 - active_list_line.y1
            if same_page and vertical_gap <= max(body_size * 1.1, 10.0):
                active_list_item = f"{active_list_item} {line.text}"
                active_list_line = line
                continue

            flush_list_item()

        if previous_body_line and paragraph_break(previous_body_line, line, body_size):
            flush_paragraph()

        paragraph_parts.append(line.text)
        previous_body_line = line

    flush_paragraph()
    flush_list_item()

    blocks = normalize_heading_blocks(blocks)
    blocks = insert_figure_images(blocks)

    content = "\n\n".join(block for block in blocks if block)
    content = MULTI_BLANK_RE.sub("\n\n", content).strip()
    return content + "\n"


def convert_pdf_to_markdown(input_pdf: Path, output_md: Path) -> None:
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    extracted_lines = extract_lines(input_pdf)
    markdown = render_markdown(extracted_lines)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_pdf = args.input_pdf.resolve()
    output_md = args.output_md.resolve() if args.output_md else input_pdf.with_suffix(".md")

    try:
        convert_pdf_to_markdown(input_pdf, output_md)
    except Exception as exc:  # pragma: no cover - CLI behavior.
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())