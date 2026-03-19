#!/usr/bin/env python3
import os
import json
import argparse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors


def load_summary(model_dir):
    summary_file = os.path.join(model_dir, "modeller_summary.json")
    if not os.path.exists(summary_file):
        raise FileNotFoundError(f"No modeller_summary.json found in {model_dir}")

    with open(summary_file, "r") as f:
        return json.load(f)


def generate_pdf(model_dir, out_pdf):
    summary = load_summary(model_dir)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Modeller Homology Modeling Report</b>", styles["Title"]))
    story.append(Spacer(1, 12))

    # --- Header ---
    story.append(Paragraph("<b>1. Job Details</b>", styles["Heading2"]))
    story.append(Paragraph(f"Job Name: {summary.get('job_name', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"Sequence Length: {summary.get('sequence_length', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"Modeller Version: {summary.get('modeller_version', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"Generated At (UTC): {summary.get('generated_at_utc', 'N/A')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # --- Scores ---
    story.append(Paragraph("<b>2. Model Scores</b>", styles["Heading2"]))
    data = [["Model", "molpdf", "DOPE Score", "GA341 Score", "DOPE Z-score"]]

    for model in summary.get("models", []):
        data.append([
            model.get("model_name", "N/A"),
            f"{model.get('molpdf', 'N/A'):.3f}" if isinstance(model.get('molpdf'), float) else "N/A",
            f"{model.get('dope_score', 'N/A'):.3f}" if isinstance(model.get('dope_score'), float) else "N/A",
            f"{model.get('ga341_score', 'N/A'):.3f}" if isinstance(model.get('ga341_score'), float) else "N/A",
            f"{model.get('dope_zscore', 'N/A'):.3f}" if isinstance(model.get('dope_zscore'), float) else "N/A",
        ])

    table = Table(data, colWidths=[160, 70, 70, 70, 70])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ])
    )
    story.append(table)
    story.append(Spacer(1, 20))

    # --- Best Model ---
    story.append(Paragraph("<b>3. Best Model</b>", styles["Heading2"]))
    best = summary.get("best_model", {})
    if best:
        story.append(Paragraph(f"Best model: {best.get('model_name', 'N/A')}", styles["Normal"]))
        story.append(Paragraph(f"DOPE Score: {best.get('dope_score', 'N/A')}", styles["Normal"]))
        story.append(Paragraph(f"GA341 Score: {best.get('ga341_score', 'N/A')}", styles["Normal"]))
        story.append(Paragraph(f"molpdf: {best.get('molpdf', 'N/A')}", styles["Normal"]))
        story.append(Paragraph(f"DOPE Z-score: {best.get('dope_zscore', 'N/A')}", styles["Normal"]))
        story.append(Spacer(1, 12))

    # --- Template Info ---
    story.append(Paragraph("<b>4. Templates Used</b>", styles["Heading2"]))
    templates = summary.get("templates", [])
    story.append(Paragraph(f"Templates: {', '.join(templates) if templates else 'N/A'}", styles["Normal"]))
    story.append(Paragraph(f"Sequence Identity (%): {summary.get('sequence_identity_pct', 0.0):.2f}", styles["Normal"]))
    story.append(Paragraph(f"Alignment Coverage (%): {summary.get('alignment_coverage_pct', 0.0):.2f}", styles["Normal"]))
    story.append(Spacer(1, 12))

    doc = SimpleDocTemplate(out_pdf, pagesize=letter)
    doc.build(story)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--out_pdf", required=True)
    args = parser.parse_args()

    generate_pdf(args.model_dir, args.out_pdf)


if __name__ == "__main__":
    main()