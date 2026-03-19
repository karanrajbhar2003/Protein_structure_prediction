#!/usr/bin/env python3
"""
Generate a structured consolidated validation PDF from multiple result directories.

Each result directory is expected to look like:
  <result_dir>/
    original.pdb
    validation/
      <tool>/
        ...tool outputs...
"""

import argparse
import datetime
import json
import os
import tempfile
from html import escape
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

try:
    import cairosvg
except Exception:
    cairosvg = None


VALIDATOR_ORDER = [
    "pdbfixer",
    "dssp",
    "freesasa",
    "molprobity",
    "prosa",
    "voromqa",
    "qmean",
    "modeller",
]

TEXT_EXTS = {".txt", ".log", ".out", ".json", ".csv", ".tsv"}
IMAGE_EXTS = {".svg", ".png", ".jpg", ".jpeg"}


def ensure_space(pdf, y, needed, page_height, margin_bottom):
    if y - needed < margin_bottom:
        pdf.showPage()
        return page_height - 60
    return y


def fit_image(path, max_width, max_height):
    img = Image.open(path).convert("RGB")
    width, height = img.size
    ratio = min(max_width / width, max_height / height, 1.0)
    return int(width * ratio), int(height * ratio)


def draw_wrapped_text(pdf, x, y, text, max_width, font_size=8, leading=10):
    style = ParagraphStyle("default", fontSize=font_size, leading=leading)
    safe_text = escape(text if text is not None else "")
    text_html = safe_text.replace("\n", "<br/>").replace(" ", "&nbsp;")
    para = Paragraph(text_html, style)
    _, height = para.wrap(max_width, 2000)
    para.drawOn(pdf, x, y - height)
    return height


def draw_table(pdf, x, y, data, col_widths):
    table = Table(data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6f8f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    _, height = table.wrapOn(pdf, 0, 0)
    table.drawOn(pdf, x, y - height)
    return height


def truncate_json(data, max_items=12):
    if isinstance(data, dict):
        return {k: truncate_json(v, max_items=max_items) for k, v in data.items()}
    if isinstance(data, list):
        if len(data) > max_items:
            return [truncate_json(v, max_items=max_items) for v in data[:max_items]] + [
                f"... ({len(data) - max_items} more)"
            ]
        return [truncate_json(v, max_items=max_items) for v in data]
    return data


def discover_tools(validation_dir: Path):
    if not validation_dir.exists():
        return []
    existing = [d.name for d in validation_dir.iterdir() if d.is_dir()]
    ordered = [v for v in VALIDATOR_ORDER if v in existing]
    ordered.extend(sorted(v for v in existing if v not in VALIDATOR_ORDER))
    return ordered


def load_summary(tool_dir: Path):
    summary_files = sorted(tool_dir.glob("*_summary.json"))
    if not summary_files:
        return {"_note": "No summary JSON found"}
    summary_path = summary_files[0]
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"Failed reading {summary_path.name}: {exc}"}


def list_output_files(tool_dir: Path):
    files = [p for p in tool_dir.iterdir() if p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())


def list_graph_files(tool_dir: Path):
    image_files = [p for p in tool_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    image_files = sorted(image_files, key=lambda p: p.name.lower())

    by_stem = {}
    for path in image_files:
        by_stem.setdefault(path.stem, []).append(path)

    prioritized = []
    for stem in sorted(by_stem.keys()):
        candidates = by_stem[stem]
        svg = next((p for p in candidates if p.suffix.lower() == ".svg"), None)
        if svg:
            prioritized.append(svg)
            continue
        png = next((p for p in candidates if p.suffix.lower() == ".png"), None)
        if png:
            prioritized.append(png)
            continue
        prioritized.append(candidates[0])
    return prioritized


def image_for_pdf(image_path: Path):
    cleanup_path = None
    ext = image_path.suffix.lower()
    if ext != ".svg":
        return image_path, cleanup_path, None

    if cairosvg is None:
        fallback_png = image_path.with_suffix(".png")
        if fallback_png.exists():
            return fallback_png, cleanup_path, None
        return None, cleanup_path, "SVG skipped (cairosvg not installed and no PNG fallback found)."

    fd, temp_png = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cleanup_path = Path(temp_png)
    try:
        cairosvg.svg2png(url=str(image_path), write_to=str(cleanup_path), dpi=300)
        return cleanup_path, cleanup_path, None
    except Exception as exc:
        if cleanup_path.exists():
            cleanup_path.unlink()
        return None, None, f"Failed to render SVG {image_path.name}: {exc}"


def draw_json_section(pdf, width, height, margin_x, margin_bottom, y, title, payload):
    y = ensure_space(pdf, y, 40, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, title)
    y -= 16

    pretty = json.dumps(payload, indent=2)
    lines = pretty.splitlines()
    chunk_size = 42
    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i : i + chunk_size])
        estimated = min(420, 12 + len(chunk.splitlines()) * 10)
        y = ensure_space(pdf, y, estimated + 20, height, margin_bottom)
        pdf.setFont("Courier", 8)
        block_h = draw_wrapped_text(pdf, margin_x, y, chunk, width - (2 * margin_x), font_size=8, leading=10)
        y -= block_h + 10
    return y


def fmt_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def draw_metrics_table(pdf, width, height, margin_x, margin_bottom, y, title, rows):
    y = ensure_space(pdf, y, 60, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, title)
    y -= 16
    y = ensure_space(pdf, y, 220, height, margin_bottom)
    table_h = draw_table(pdf, margin_x, y, rows, col_widths=[220, 270])
    y -= table_h + 10
    return y


def draw_freesasa_residue_table(pdf, width, height, margin_x, margin_bottom, y, summary):
    residues = summary.get("residue_areas") if isinstance(summary, dict) else None
    if not isinstance(residues, list) or not residues:
        return y

    y = ensure_space(pdf, y, 60, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Per-residue SASA (first 10 residues)")
    y -= 16

    rows = [["Res #", "Name", "Total (A^2)", "Side Chain", "Main Chain"]]
    for item in residues[:10]:
        rows.append(
            [
                str(item.get("residue_number", "")),
                str(item.get("residue_name", "")),
                fmt_value(item.get("total_area")),
                fmt_value(item.get("side_chain")),
                fmt_value(item.get("main_chain")),
            ]
        )

    y = ensure_space(pdf, y, 250, height, margin_bottom)
    table_h = draw_table(pdf, margin_x, y, rows, col_widths=[55, 65, 95, 95, 95])
    y -= table_h + 8

    remaining = len(residues) - 10
    if remaining > 0:
        y = ensure_space(pdf, y, 24, height, margin_bottom)
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawString(margin_x, y, f"... ({remaining} more residues)")
        y -= 12
    return y


def draw_file_inventory(pdf, width, height, margin_x, margin_bottom, y, model_dir, files):
    y = ensure_space(pdf, y, 70, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Output Files")
    y -= 16

    if not files:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y, "No files found.")
        return y - 14

    rows = [["File", "Type", "Size (KB)"]]
    for p in files:
        rel = str(p.relative_to(model_dir)).replace("\\", "/")
        ext = p.suffix.lower() or "-"
        size_kb = f"{p.stat().st_size / 1024:.1f}"
        rows.append([rel, ext, size_kb])

    batch_size = 18
    for i in range(0, len(rows), batch_size):
        chunk = [rows[0]] + rows[i + 1 : i + batch_size]
        y = ensure_space(pdf, y, 220, height, margin_bottom)
        table_h = draw_table(pdf, margin_x, y, chunk, col_widths=[330, 80, 80])
        y -= table_h + 10
    return y


def draw_graphs(pdf, width, height, margin_x, margin_bottom, y, graph_files):
    y = ensure_space(pdf, y, 40, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Graphs and Plots")
    y -= 16

    if not graph_files:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y, "No graph/image files found.")
        return y - 14

    for graph_path in graph_files:
        render_path, cleanup, warning = image_for_pdf(graph_path)
        try:
            if warning:
                y = ensure_space(pdf, y, 30, height, margin_bottom)
                pdf.setFont("Helvetica-Oblique", 8)
                pdf.drawString(margin_x, y, f"{graph_path.name}: {warning}")
                y -= 12
                continue

            if render_path is None:
                continue

            max_w = width - (2 * margin_x)
            max_h = 330
            new_w, new_h = fit_image(str(render_path), max_w, max_h)
            y = ensure_space(pdf, y, new_h + 28, height, margin_bottom)

            pdf.setFont("Helvetica", 9)
            pdf.drawString(margin_x, y, graph_path.name)
            y -= 12

            pdf.drawImage(
                ImageReader(str(render_path)),
                margin_x,
                y - new_h,
                width=new_w,
                height=new_h,
            )
            y -= new_h + 12
        finally:
            if cleanup and cleanup.exists():
                cleanup.unlink()
    return y


def draw_raw_output_paths(pdf, width, height, margin_x, margin_bottom, y, summary, files):
    y = ensure_space(pdf, y, 40, height, margin_bottom)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Raw Output Files")
    y -= 16

    raw_paths = []

    if isinstance(summary, dict):
        for _, value in summary.items():
            if isinstance(value, str) and value.strip():
                low = value.lower()
                if low.endswith((".txt", ".log", ".out", ".json", ".csv", ".tsv", ".html", ".pdb")):
                    raw_paths.append(value)

    for p in files:
        if p.suffix.lower() in TEXT_EXTS or p.suffix.lower() in {".html", ".pdb"}:
            raw_paths.append(str(p.resolve()))

    deduped = []
    seen = set()
    for path in raw_paths:
        key = path.lower()
        if key not in seen:
            deduped.append(path)
            seen.add(key)

    if not deduped:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y, "No raw output files found.")
        return y - 14

    for path in deduped:
        y = ensure_space(pdf, y, 40, height, margin_bottom)
        pdf.setFont("Courier", 8)
        used_h = draw_wrapped_text(pdf, margin_x, y, path, width - (2 * margin_x), font_size=8, leading=10)
        y -= used_h + 6

    return y


def draw_interpreted_summary(pdf, width, height, margin_x, margin_bottom, y, tool, summary):
    if not isinstance(summary, dict):
        return draw_json_section(pdf, width, height, margin_x, margin_bottom, y, "Summary", summary)

    tool_low = tool.lower()
    rows = [["Metric", "Value"]]

    if tool_low == "freesasa":
        rows.append(["Total Area (A^2)", fmt_value(summary.get("total_area"))])
        rows.append(["Residues Analyzed", fmt_value(summary.get("num_residues"))])
        y = draw_metrics_table(pdf, width, height, margin_x, margin_bottom, y, "FreeSASA Summary", rows)
        y = draw_freesasa_residue_table(pdf, width, height, margin_x, margin_bottom, y, summary)
        return y

    if tool_low == "prosa":
        rows.append(["Mode", fmt_value(summary.get("mode"))])
        rows.append(["Z-score", fmt_value(summary.get("z_score"))])
        rows.append(["Input PDB", fmt_value(summary.get("input_pdb"))])
        return draw_metrics_table(pdf, width, height, margin_x, margin_bottom, y, "ProSA Global Metrics", rows)

    if tool_low == "qmean":
        rows.append(["QMEAN6 (normalized)", fmt_value(summary.get("global_score"))])
        rows.append(["QMEAN Z-score", fmt_value(summary.get("zscore"))])
        rows.append(["Residues", fmt_value(summary.get("num_residues"))])
        return draw_metrics_table(pdf, width, height, margin_x, margin_bottom, y, "QMEANDisCo Global Scores", rows)

    scalar_items = []
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            scalar_items.append((key, value))

    if scalar_items:
        for key, value in scalar_items[:16]:
            rows.append([str(key), fmt_value(value)])
        return draw_metrics_table(pdf, width, height, margin_x, margin_bottom, y, f"{tool.upper()} Summary", rows)

    return draw_json_section(pdf, width, height, margin_x, margin_bottom, y, "Summary", summary)


def draw_tool_section(pdf, model_dir: Path, validation_dir: Path, tool: str, width, height, margin_x, margin_bottom):
    tool_dir = validation_dir / tool
    pdf.showPage()
    y = height - 60

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin_x, y, f"{tool.upper()} Results")
    y -= 24

    summary = load_summary(tool_dir)
    status = summary.get("status", "unknown") if isinstance(summary, dict) else "unknown"
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin_x, y, f"Status: {status}")
    y -= 20

    y = draw_interpreted_summary(pdf, width, height, margin_x, margin_bottom, y, tool, summary)

    files = list_output_files(tool_dir)
    y = draw_graphs(pdf, width, height, margin_x, margin_bottom, y, list_graph_files(tool_dir))
    y = draw_raw_output_paths(pdf, width, height, margin_x, margin_bottom, y, summary, files)


def create_consolidated_pdf(results_dirs, out_pdf):
    pdf = canvas.Canvas(out_pdf, pagesize=letter)
    width, height = letter
    margin_x, margin_bottom = 50, 50

    y = height - 60
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(width / 2, y, "Consolidated Validation Report")
    y -= 30
    pdf.setFont("Helvetica", 10)
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    pdf.drawCentredString(width / 2, y, f"Generated: {ts} UTC")
    y -= 36

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, y, "Included Models")
    y -= 18
    pdf.setFont("Courier", 9)
    for path in results_dirs:
        y = ensure_space(pdf, y, 16, height, margin_bottom)
        pdf.drawString(margin_x, y, f"- {Path(path).name}")
        y -= 12

    for model_path in results_dirs:
        model_dir = Path(model_path)
        validation_dir = model_dir / "validation"
        tools = discover_tools(validation_dir)

        pdf.showPage()
        y = height - 60
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(margin_x, y, f"Model: {model_dir.name}")
        y -= 24
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin_x, y, f"Path: {model_dir}")
        y -= 24

        if not tools:
            pdf.setFont("Helvetica", 11)
            pdf.drawString(margin_x, y, "No validation tool outputs found for this model.")
            continue

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(margin_x, y, "Tools Included")
        y -= 16
        pdf.setFont("Courier", 9)
        for tool in tools:
            y = ensure_space(pdf, y, 14, height, margin_bottom)
            pdf.drawString(margin_x, y, f"- {tool}")
            y -= 11

        for tool in tools:
            draw_tool_section(pdf, model_dir, validation_dir, tool, width, height, margin_x, margin_bottom)

    pdf.save()
    print(f"Consolidated PDF saved to {out_pdf}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a consolidated validation PDF.")
    parser.add_argument("--results_dirs", required=True, help="Comma-separated list of result directories")
    parser.add_argument("--out_pdf", required=True, help="Output PDF path")
    args = parser.parse_args()

    directories = [d.strip() for d in args.results_dirs.split(",") if d.strip()]
    create_consolidated_pdf(directories, args.out_pdf)
