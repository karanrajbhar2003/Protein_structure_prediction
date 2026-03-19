#!/usr/bin/env python3
"""
Generate a consolidated validation PDF for one model directory.

This version expects validator folders to provide SVG images (no PNG).
SVGs are converted to temporary PNG files (in-memory / tempdir) for embedding
into the ReportLab PDF. No PNGs are written to the validator folders.

Usage:
  python tools/generate_validation_pdf.py --model_dir path/to/results/model1 --out_pdf path/to/report.pdf
"""

import os
import json
import argparse
import sys
import tempfile
import shutil
from html import escape

print(f"Arguments received: {sys.argv}")

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image

# cairosvg required for converting SVG -> PNG
try:
    import cairosvg
except Exception:
    cairosvg = None

# Only SVG names (we embed SVGs exclusively)
COMMON_SVGS = [
    "energy_plot.svg",
    "voromqa_profile.svg",
    "qmean_plot.svg",
    "verify3d_profile.svg",
    "ramachandran_plot.svg",
    "freesasa_plot.svg"
]

def fmt(v, fmt_str="{:.2f}"):
    """Safe formatting - returns 'N/A' for None or strings."""
    if v is None or isinstance(v, str):
        return "N/A"
    try:
        return fmt_str.format(v)
    except Exception:
        return "N/A"

def fit_image(path, max_width, max_height):
    """
    Open an image (PNG) and compute new width/height to fit within max dims.
    Returns (new_w, new_h)
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    ratio = min(max_width / w, max_height / h, 1.0)
    return (int(w * ratio), int(h * ratio))

def draw_multiline_text(c, x, y, text, max_width, font_size=8, leading=10):
    """Draw multiline text using ReportLab Paragraph; returns height used."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    style = ParagraphStyle('default', fontSize=font_size, leading=leading)
    # keep spaces but allow line breaks; escape tag-like text first
    safe_text = escape(text if text is not None else "")
    text_html = safe_text.replace("\n", "<br/>").replace(" ", "&nbsp;")
    para = Paragraph(text_html, style)
    w, h = para.wrap(max_width, 2000)
    para.drawOn(c, x, y - h)
    return h

def aggregate_json_files(model_dir, validators=None):
    """Collect *_summary.json files from validator subfolders in a defined order."""
    summaries = {}
    validator_order = ["pdbfixer", "dssp", "freesasa", "molprobity",
                       "prosa", "voromqa", "qmean", "modeller"]

    if validators is not None:
        subdirectories = [v for v in validator_order if v in validators]
    else:
        existing_dirs = [d for d in os.listdir(model_dir)
                         if os.path.isdir(os.path.join(model_dir, d))]
        subdirectories = [v for v in validator_order if v in existing_dirs]
        subdirectories.extend([d for d in sorted(existing_dirs) if d not in validator_order])

    print(f"Processing validators in order: {subdirectories}")

    for entry in subdirectories:
        p = os.path.join(model_dir, entry)
        if os.path.isdir(p):
            print(f"Scanning directory: {entry}")
            json_found = False
            for fname in os.listdir(p):
                if fname.endswith("_summary.json"):
                    try:
                        with open(os.path.join(p, fname)) as fh:
                            summaries[entry] = json.load(fh)
                            json_found = True
                            print(f"  Found JSON: {fname}")
                    except Exception as e:
                        print(f"  Error reading {fname}: {e}")
                        summaries[entry] = {"_raw_exists": True, "_error": str(e)}

            if not json_found:
                print(f"  No JSON summary found in {entry}")
                summaries[entry] = {"_note": "No summary JSON found"}

    return summaries

def find_svgs_for_tool(tool_dir):
    """
    Return list of SVG file paths (only). Prefer known common SVG basenames,
    then include any other .svg files present.
    """
    svgs = []
    svg_basenames = set()

    print(f"  Searching for SVG images in: {tool_dir}")

    # First include known filenames if present
    for name in COMMON_SVGS:
        p = os.path.join(tool_dir, name)
        if os.path.exists(p):
            svgs.append(p)
            svg_basenames.add(name)
            print(f"    Found common SVG: {name}")

    # Then any other svg files
    try:
        for f in os.listdir(tool_dir):
            if f in svg_basenames:
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext == ".svg":
                svgs.append(os.path.join(tool_dir, f))
                print(f"    Found additional SVG: {f}")
    except Exception as e:
        print(f"    Error listing directory: {e}")

    print(f"  Total SVGs found: {len(svgs)}")
    return svgs

def convert_svg_to_png_temp(svg_path, dpi=300):
    """
    Convert SVG to a temporary PNG file using cairosvg.
    Returns the path to the temporary PNG (caller must not persist it).
    """
    if cairosvg is None:
        raise RuntimeError("cairosvg is required to convert SVG to PNG but is not installed.")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(tmp_fd)
    try:
        # cairosvg.svg2png supports write_to
        cairosvg.svg2png(url=svg_path, write_to=tmp_path, dpi=dpi)
        return tmp_path
    except Exception:
        # Clean up on error
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

def truncate_json_for_display(data, max_items=10):
    """Truncate large lists in JSON to avoid very long pages."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, list) and len(value) > max_items:
                result[key] = value[:max_items] + [f"... ({len(value) - max_items} more items)"]
            elif isinstance(value, (dict, list)):
                result[key] = truncate_json_for_display(value, max_items)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        if len(data) > max_items:
            return data[:max_items] + [f"... ({len(data) - max_items} more items)"]
        return [truncate_json_for_display(item, max_items) if isinstance(item, (dict, list)) else item
                for item in data]
    return data

def draw_table(c, x, y, data, col_widths, font_size=9, leading=11):
    """Draw a simple table and return the total height."""
    if not data:
        return 0

    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    table = Table(data, colWidths=col_widths)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4682B4")),  # header
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey)
    ])
    table.setStyle(style)
    w, h = table.wrapOn(c, 0, 0)
    table.drawOn(c, x, y - h)
    return h

def draw_molprobity_section(c, y, tool_dir, page_width, page_height, margin_x, margin_bottom):
    """
    Draw the MolProbity section. Ramachandran image is embedded large and
    SVG -> PNG conversion is done via a temporary PNG that is deleted.
    """
    summary_path = os.path.join(tool_dir, "molprobity_summary.json")
    if not os.path.exists(summary_path):
        c.setFont("Helvetica", 10)
        c.drawString(margin_x, y, "molprobity_summary.json not found.")
        return y - 20

    with open(summary_path) as f:
        summary = json.load(f)

    # Core metrics
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, y, "Core MolProbity Metrics")
    y -= 18

    core_data = [
        ["Metric", "Value", "Metric", "Value"],
        ["MolProbity Score", fmt(summary.get("molprobity_score")),
         "Clashscore", fmt(summary.get("clashscore"))],
        ["Bond RMSD", fmt(summary.get("bond_rmsd"), "{:.3f}"),
         "Angle RMSD", fmt(summary.get("angle_rmsd"))],
        ["Rotamer Outliers", fmt(summary.get("rotamers", {}).get("outliers"), "{:.1f}%"),
         "Cβ Deviations", summary.get("cbeta_deviations", "N/A")],
    ]
    table_h = draw_table(c, margin_x, y, core_data, col_widths=[120, 80, 120, 80])
    y -= (table_h + 28)

    # Ramachandran (full-width)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, y, "Ramachandran Analysis")
    y -= 18

    # prefer svg, convert to temp png for embedding
    rama_svg = os.path.join(tool_dir, "ramachandran_plot.svg")
    rama_png_tmp = None
    try:
        if os.path.exists(rama_svg) and cairosvg:
            rama_png_tmp = convert_svg_to_png_temp(rama_svg, dpi=300)
            embed_path = rama_png_tmp
        else:
            # If no svg present, try a PNG fallback only if exists (but we won't search for PNGs globally).
            possible_png = os.path.join(tool_dir, "ramachandran_plot.png")
            if os.path.exists(possible_png):
                embed_path = possible_png
            else:
                embed_path = None

        if not embed_path:
            c.setFont("Helvetica", 10)
            c.drawString(margin_x, y, "Ramachandran plot not found.")
            y -= 20
        else:
            max_w = page_width - (margin_x * 2)
            max_h = 480
            new_w, new_h = fit_image(embed_path, max_w, max_h)

            # page break if needed
            if y - new_h < margin_bottom:
                c.showPage()
                y = page_height - 60

            c.drawImage(ImageReader(embed_path), margin_x, y - new_h, width=new_w, height=new_h)
            y -= (new_h + 18)

            # stats below the image
            rama_stats = summary.get("ramachandran", {})
            stats_data = [
                ["Region", "Percentage"],
                ["Favored", fmt(rama_stats.get("favored"), "{:.1f}%")],
                ["Allowed", fmt(rama_stats.get("allowed"), "{:.1f}%")],
                ["Outliers", fmt(rama_stats.get("outliers"), "{:.1f}%")],
            ]
            stats_h = draw_table(c, margin_x, y, stats_data, col_widths=[140, 140])
            y -= (stats_h + 24)
    finally:
        if rama_png_tmp:
            try:
                os.remove(rama_png_tmp)
            except Exception:
                pass

    # Top clashes
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, y, "Top 10 Steric Clashes")
    y -= 18

    clashes = summary.get("worst_clashes", [])
    if clashes:
        clash_data = [["Atom 1", "Atom 2", "Overlap (Å)"]]
        for clash in clashes:
            clash_data.append([clash.get("atom1"), clash.get("atom2"),
                               fmt(clash.get("overlap"), "{:.3f}")])
        table_h = draw_table(c, margin_x, y, clash_data, col_widths=[180, 180, 80])
        y -= (table_h + 20)
    else:
        c.setFont("Helvetica", 10)
        c.drawString(margin_x, y, "No clash data available.")
        y -= 20

    # Raw files listing (only if present)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, y, "Raw Output Files")
    y -= 16
    c.setFont("Courier", 9)
    for fname in ("molprobity.log", "molprobity_probe.txt", "ramachandran_data.json"):
        fpath = os.path.join(tool_dir, fname)
        if os.path.exists(fpath):
            c.drawString(margin_x, y, fpath)
        else:
            c.drawString(margin_x, y, f"[missing] {fname}")
        y -= 12

    y -= 10
    return y

def create_pdf(model_dir, out_pdf, validators=None):
    print(f"\n=== Starting PDF Generation ===")
    print(f"Model directory: {model_dir}")
    print(f"Output PDF: {out_pdf}")
    print(f"Requested validators: {validators}")

    c = canvas.Canvas(out_pdf, pagesize=letter)
    width, height = letter
    margin_x = 50
    margin_bottom = 50
    y = height - 60

    model_name = os.path.basename(model_dir.rstrip("/\\"))

    # Title page
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin_x, y, f"Validation Report — {model_name}")
    y -= 30
    c.setFont("Helvetica", 10)
    import datetime
    c.drawString(margin_x, y, f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    y -= 50

    summaries = aggregate_json_files(model_dir, validators)

    if not summaries:
        c.setFont("Helvetica", 11)
        c.drawString(margin_x, y, "No validation results found.")
        c.save()
        print("No summaries found. PDF saved with message only.")
        return

    first_tool = True
    for tool in summaries.keys():
        print(f"\nProcessing validator: {tool}")

        # Page break between validators
        if not first_tool:
            c.showPage()
            y = height - 60
            print(f"  Added page break before {tool}")
        first_tool = False

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin_x, y, tool.upper())
        y -= 24

        if tool == "molprobity":
            y = draw_molprobity_section(c, y, os.path.join(model_dir, tool), width, height, margin_x, margin_bottom)
            continue

        # Generic JSON summary rendering
        data = summaries[tool]
        # Slightly larger truncation for DSSP
        if tool == "dssp":
            display_data = truncate_json_for_display(data, max_items=12)
        else:
            display_data = truncate_json_for_display(data, max_items=5)

        try:
            pretty = json.dumps(display_data, indent=2)
        except Exception:
            pretty = str(display_data)

        lines = pretty.split("\n")
        chunk_size = 45
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk_text = "\n".join(chunk_lines)
            estimated_height = len(chunk_lines) * 10
            if y - estimated_height < margin_bottom:
                c.showPage()
                y = height - 60
                c.setFont("Helvetica-Bold", 14)
                c.drawString(margin_x, y, f"{tool.upper()} (continued)")
                y -= 20

            c.setFont("Courier", 8)
            h = draw_multiline_text(c, margin_x, y, chunk_text,
                                    max_width=width - margin_x * 2,
                                    font_size=8, leading=10)
            y -= (h + 12)

        print(f"  Summary rendered for {tool}")

        # Process SVG images for this validator (SVG-only)
        tool_dir = os.path.join(model_dir, tool)
        if not os.path.isdir(tool_dir):
            continue

        svgs = find_svgs_for_tool(tool_dir)
        if not svgs:
            print(f"  No SVGs found for {tool}")
            continue

        print(f"  Found {len(svgs)} SVG(s) for {tool}")
        for svg_path in svgs:
            print(f"  Processing SVG: {os.path.basename(svg_path)}")
            if cairosvg is None:
                print("    cairosvg not installed: skipping SVG rendering")
                continue

            tmp_png = None
            try:
                tmp_png = convert_svg_to_png_temp(svg_path, dpi=300)
                max_w = width - margin_x * 2
                max_h = 400
                new_w, new_h = fit_image(tmp_png, max_w, max_h)
                if y - new_h - 30 < margin_bottom:
                    c.showPage()
                    y = height - 60

                c.setFont("Helvetica-Bold", 10)
                c.drawString(margin_x, y, f"{tool} — {os.path.basename(svg_path)}")
                y -= 14

                c.drawImage(ImageReader(tmp_png), margin_x, y - new_h, width=new_w, height=new_h)
                y -= (new_h + 18)
                print(f"    Rendered SVG as PNG (temporary)")

            except Exception as e:
                print(f"    Failed to render SVG {svg_path}: {e}")
                c.setFont("Helvetica", 9)
                c.drawString(margin_x, y, f"[Error rendering SVG: {os.path.basename(svg_path)}]")
                y -= 14
            finally:
                if tmp_png:
                    try:
                        os.remove(tmp_png)
                    except Exception:
                        pass

    c.save()
    print(f"\n=== PDF Generation Complete ===")
    print(f"Wrote PDF: {out_pdf}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a consolidated validation PDF for a model directory.")
    parser.add_argument("--model_dir", required=True, help="Directory containing per-tool subfolders")
    parser.add_argument("--out_pdf", required=True, help="Output PDF path")
    parser.add_argument("--validators", type=str, help="Optional: comma-separated list of validators to include in the report.")
    args = parser.parse_args()

    validators_list = None
    if args.validators:
        validators_list = [v.strip() for v in args.validators.split(',') if v.strip()]
        print(f"Filtered validators list: {validators_list}")

    create_pdf(args.model_dir, args.out_pdf, validators_list)
