#!/usr/bin/env python3
"""Render PNG/PDF variants of Figure 5.9 from its frozen source-data CSV."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


WIDTH = 1120
HEIGHT = 620
SCALE = 3
LEFT, RIGHT, TOP, BOTTOM = 210, 72, 126, 94
TEAL = "#2a8580"
PURPLE = "#6f4c9b"
INK = "#1a1a1a"
MUTED = "#66707a"
GRID = "#d9dee2"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size * SCALE)


def point(value: float) -> int:
    return round(value * SCALE)


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    *,
    size: int,
    fill: str = INK,
    bold: bool = False,
    anchor: str = "la",
) -> None:
    draw.text(
        (point(xy[0]), point(xy[1])),
        value,
        font=font(size, bold),
        fill=fill,
        anchor=anchor,
    )


def render(rows: list[dict], png_path: Path, pdf_path: Path) -> None:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)
    plot_width = WIDTH - LEFT - RIGHT
    row_height = (HEIGHT - TOP - BOTTOM) / 4

    text(
        draw,
        (WIDTH / 2, 38),
        "Grounding context and repair effectiveness",
        size=24,
        bold=True,
        anchor="mm",
    )
    text(
        draw,
        (WIDTH / 2, 65),
        "One matched GPT-5.6 Sol observation per target and level (30 targets; 120 calls)",
        size=14,
        fill=MUTED,
        anchor="mm",
    )
    for tick in range(0, 101, 20):
        x = LEFT + plot_width * tick / 100
        draw.line(
            [(point(x), point(TOP - 10)), (point(x), point(HEIGHT - BOTTOM))],
            fill=GRID,
            width=SCALE,
        )
        text(draw, (x, HEIGHT - BOTTOM + 28), f"{tick}%", size=13, fill=MUTED, anchor="mm")
    text(
        draw,
        (LEFT + plot_width / 2, HEIGHT - 22),
        "Percentage of all 30 targets",
        size=13,
        fill=MUTED,
        anchor="mm",
    )

    for index, row in enumerate(rows):
        centre = TOP + row_height * (index + 0.5)
        text(draw, (LEFT - 22, centre), row["Context"], size=16, bold=True, anchor="rm")
        series = [
            ("verified_rate", "verified_lo", "verified_hi", TEAL, centre - 17),
            ("preserved_rate", "preserved_lo", "preserved_hi", PURPLE, centre + 17),
        ]
        for rate_key, lo_key, hi_key, color, y in series:
            rate = float(row[rate_key])
            lo = float(row[lo_key])
            hi = float(row[hi_key])
            bar_width = plot_width * rate / 100
            draw.rectangle(
                [point(LEFT), point(y - 10), point(LEFT + bar_width), point(y + 10)],
                fill=color,
            )
            x_lo = LEFT + plot_width * lo / 100
            x_hi = LEFT + plot_width * hi / 100
            draw.line(
                [(point(x_lo), point(y)), (point(x_hi), point(y))],
                fill=INK,
                width=4,
            )
            for cap in (x_lo, x_hi):
                draw.line(
                    [(point(cap), point(y - 5)), (point(cap), point(y + 5))],
                    fill=INK,
                    width=4,
                )
            if rate > 88:
                text(draw, (LEFT + bar_width - 8, y), f"{rate:.1f}%", size=13, bold=True, anchor="rm")
            else:
                text(draw, (LEFT + bar_width + 8, y), f"{rate:.1f}%", size=13, bold=True, anchor="lm")

    draw.rectangle(
        [point(LEFT), point(82), point(LEFT + 18), point(94)],
        fill=TEAL,
    )
    text(draw, (LEFT + 26, 88), "Detector-verified repair", size=13, anchor="lm")
    draw.rectangle(
        [point(LEFT + 238), point(82), point(LEFT + 256), point(94)],
        fill=PURPLE,
    )
    text(
        draw,
        (LEFT + 264, 88),
        "Detector-verified + private oracle passed",
        size=13,
        anchor="lm",
    )
    text(
        draw,
        (WIDTH / 2, 606),
        "Error bars are 95% Wilson intervals; inferential tests use the matched target design.",
        size=14,
        fill=MUTED,
        anchor="mm",
    )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(png_path, format="PNG", dpi=(300, 300))
    page_width = 806.4
    page_height = page_width * HEIGHT / WIDTH
    document = canvas.Canvas(str(pdf_path), pagesize=(page_width, page_height))
    document.drawImage(
        ImageReader(image),
        0,
        0,
        width=page_width,
        height=page_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    document.showPage()
    document.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args()
    with args.source.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 4:
        raise ValueError(f"expected four context rows, got {len(rows)}")
    render(rows, args.png, args.pdf)
    print(f"wrote {args.png} and {args.pdf}")


if __name__ == "__main__":
    main()
