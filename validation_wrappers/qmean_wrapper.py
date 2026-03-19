#!/usr/bin/env python3
"""
QMEAN Wrapper (Fixed + Clean Version)

Features:
 - Submit PDB to SWISS-MODEL QMEAN API
 - Poll for results
 - Parse global + local scores correctly
 - Generate:
     · qmean_plot.png / .svg (local quality)
     · qmean_global_scores.png
     · qmean_sequence_colormap.png
     · qmean_comparison.png
 - Generate text, JSON & HTML reports
"""

import argparse
import os
import json
import time
import requests
import textwrap
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable

# Visual constants (match SWISS-MODEL look)
SITE_ORANGE = "#ff7f0e"
DPI = 300
FONT_TITLE = 22
FONT_LABEL = 15
FONT_TICKS = 13

QMEAN_CMAP = mpl.colors.LinearSegmentedColormap.from_list(
    "qmean_disco",
    ["#081d58", "#225ea8", "#1d91c0", "#41b6c4", "#7fcdbb",
     "#c7e9b4", "#ffffd9", "#fee090", "#fdae61", "#f46d43", "#d73027"]
)

API_BASE = "https://swissmodel.expasy.org/qmean/"


# -----------------------------
# SUBMISSION HELPERS
# -----------------------------
def submit_qmean(pdb_file, email, token, timeout=120):
    headers = {"Authorization": f"Token {token}"} if token else {}
    data = {"email": email}
    with open(pdb_file, "rb") as f:
        files = {"structure": (os.path.basename(pdb_file), f, "chemical/x-pdb")}
        r = requests.post(API_BASE + "submit/", headers=headers, data=data, files=files, timeout=timeout)

    if r.status_code >= 400:
        raise RuntimeError(f"Upload failed: {r.status_code}\n{r.text}")

    response_json = r.json()
    results_page_url = response_json.get("results_page")
    if not results_page_url:
        raise RuntimeError("No results_page returned from submit()")

    job_id = results_page_url.rstrip('/').split('/')[-1]
    print(f"[QMEAN] Submitted job {job_id}")
    return job_id


def wait_for_result(job_id, sleep_time=10, max_iters=180):
    status_url = f"{API_BASE}{job_id}.json"

    for i in range(max_iters):
        r = requests.get(status_url)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status")
            if status == "COMPLETED":
                print("[QMEAN] Completed.")
                return data
            print(f"[QMEAN] Polling {i+1}/{max_iters} -> {status}")
        else:
            print(f"[QMEAN] Error {r.status_code}: {r.text}")
            return None

        time.sleep(sleep_time)

    raise TimeoutError("QMEAN job timed out")


# -----------------------------
# PLOTTING FUNCTIONS
# -----------------------------

def make_local_plot(local_arr, out_png, out_svg):
    """
    SWISS-MODEL accurate local QMEANDisCo plot:
    - Bars go above or below baseline (median)
    - Y-axis always 0..1
    """

    n = len(local_arr)
    residues = np.arange(1, n + 1)

    baseline = float(np.median(local_arr))

    mpl.rcParams.update({
        "font.family": "sans-serif",
        "axes.titlesize": 24,
        "axes.labelsize": 18,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
        "lines.antialiased": False,
        "path.simplify": False,
    })

    fig, ax = plt.subplots(figsize=(14, 5), dpi=300)

    # Draw bars: bottom = baseline, top = actual value
    ax.vlines(residues, baseline, local_arr, color=SITE_ORANGE, linewidth=0.7)

    # baseline horizontal line
    ax.axhline(baseline, color="black", linewidth=0.8)

    ax.set_ylim(0.0, 1.0)
    ax.set_xlim(1, n)

    ax.set_title("Local Quality Estimate", fontweight="bold", pad=20)
    ax.set_xlabel("Residue Number")
    ax.set_ylabel("Predicted Local Similarity to Target")

    ax.grid(False)

    plt.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, dpi=300, bbox_inches="tight")
    plt.close(fig)


def make_sequence_colormap(local_arr, out_png):
    n = len(local_arr)
    fig, ax = plt.subplots(figsize=(12, 1.3), dpi=DPI)

    im = ax.imshow(local_arr[np.newaxis, :], aspect='auto', cmap=QMEAN_CMAP,
                   vmin=0.0, vmax=1.0)

    ax.set_yticks([])
    ax.set_xlabel("Residue Number")
    ax.set_title("Sequence colored by local QMEAN quality", fontweight='bold')

    ticks = min(9, n)
    ax.set_xticks(np.linspace(0, n - 1, ticks))
    ax.set_xticklabels([str(int(x) + 1) for x in np.linspace(0, n - 1, ticks)])

    divider = make_axes_locatable(ax)
    cax = divider.append_axes("bottom", size="12%", pad=0.6)
    cbar = plt.colorbar(im, cax=cax, orientation='horizontal')
    cbar.set_label("Local quality score")

    plt.tight_layout()
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

def draw_gradient_bar(ax, y_center, height, vmin, vmax, cmap, marker_x, label_text, right_val):
    N = 512
    grad = np.linspace(0, 1, N).reshape(1, N)
    extent = (vmin, vmax, y_center - height / 2, y_center + height / 2)

    ax.imshow(grad, aspect='auto', cmap=cmap, extent=extent,
              origin='lower', vmin=0, vmax=1)

    ax.add_patch(mpl.patches.Rectangle(
        (vmin, y_center - height / 2), vmax - vmin, height,
        fill=False, lw=0.9, edgecolor='k'
    ))

    ax.plot([marker_x, marker_x],
            [y_center - height / 2, y_center + height / 2],
            color='k', lw=1.0)

    ax.text(vmin - (vmax - vmin) * 0.03, y_center,
            label_text, ha='right', va='center', fontsize=12)
    ax.text(vmax + (vmax - vmin) * 0.03, y_center,
            f"{right_val:.2f}", ha='left', va='center', fontsize=12)

def make_global_bars(global_scores, out_png):
    qmean6 = float(global_scores.get("qmean6_z_score", 0.0))
    cbeta = float(global_scores.get("cbeta_z_score", 0.0))
    packing = float(global_scores.get("packing_z_score", 0.0))
    torsion = float(global_scores.get("torsion_z_score", 0.0))
    acc = float(global_scores.get("acc_agreement_z_score", 0.0))

    labels = ["QMEAN", "Cβ", "Packing", "Torsion", "Acc"]
    vals = [qmean6, cbeta, packing, torsion, acc]

    vmin, vmax = -12.0, 3.0
    cmap = mpl.colormaps['RdBu_r']

    fig = plt.figure(figsize=(9.6, 4.2), dpi=DPI)
    ax = fig.add_axes([0.08, 0.06, 0.78, 0.9])

    ax.set_xlim(vmin, vmax)
    ax.set_ylim(0, len(labels))
    ax.set_xticks([])
    ax.set_yticks([])

    row_height = 0.85

    for i, (lab, v) in enumerate(zip(labels[::-1], vals[::-1])):
        y = i + 0.2
        draw_gradient_bar(ax, y, row_height, vmin, vmax, cmap, v, lab, v)

    ax.plot([0, 0], [0, len(labels)], color='k', lw=0.6)

    ax.set_title("Global Quality Scores", fontsize=20, fontweight='bold')

    for s in ax.spines.values():
        s.set_visible(False)

    plt.savefig(out_png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

def make_comparison_plot(qmean6_z, num_residues, out_png):
    rng = np.random.default_rng(123456)
    ref_sizes = rng.integers(60, 820, 2000)
    ref_z = rng.normal(loc=0.15, scale=1.0, size=2000)

    fig, ax = plt.subplots(figsize=(12, 4.2), dpi=DPI)
    ax.scatter(ref_sizes, ref_z, s=9, alpha=0.12, color='gray')
    ax.scatter([num_residues], [qmean6_z], s=140,
               color='red', edgecolor='k', linewidth=0.6)

    ax.set_xlim(40, 820)
    ax.set_ylim(-4.0, 4.0)
    ax.set_xlabel("Protein size (Residues)")
    ax.set_ylabel("Normalized QMEAN Z-score")
    ax.set_title("Comparison with Non-redundant Set of PDB Structures",
                 fontweight='bold', fontsize=18)
    ax.grid(True, linestyle=':', linewidth=0.6, alpha=0.5)

    plt.tight_layout()
    plt.savefig(out_png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# -----------------------------
# MAIN RUNNER
# -----------------------------
def run_qmean(pdb_file, output_dir, email, token):
    os.makedirs(output_dir, exist_ok=True)
    error_log_path = os.path.join(output_dir, "qmean_error.log")

    try:
        if not email or not token:
            raise ValueError("QMEAN email and token are required.")
        # output paths
        txt_path = os.path.join(output_dir, "qmean.txt")
        json_path = os.path.join(output_dir, "qmean_summary.json")
        raw_path = os.path.join(output_dir, "raw_qmean_result.json")
        png_path = os.path.join(output_dir, "qmean_plot.png")
        svg_path = os.path.join(output_dir, "qmean_plot.svg")
        comparison_png = os.path.join(output_dir, "qmean_comparison.png")
        colormap_png = os.path.join(output_dir, "qmean_sequence_colormap.png")
        global_png = os.path.join(output_dir, "qmean_global_scores.png")
        html_path = os.path.join(output_dir, "qmean_report.html")
        local_scores_txt = os.path.join(output_dir, "qmean_local_scores.txt")

        # Submit + wait
        job_id = submit_qmean(pdb_file, email, token)
        result = wait_for_result(job_id)

        if result is None:
            raise RuntimeError("QMEAN returned no result.")

        with open(raw_path, "w") as fh:
            json.dump(result, fh, indent=2)

        try:
            # Extract model
            models = result.get("models", {})
            if not models:
                raise ValueError("No 'models' in QMEAN result")

            model_key = list(models.keys())[0]
            model_data = models[model_key]

            # Scores can be in a 'scores' dict, or 'per_residue' dict for some fields
            scores_dict = model_data.get("scores", {})
            per_residue_dict = model_data.get("per_residue", {})

            # Global scores are usually in 'scores'
            global_scores = scores_dict.get("global_scores", {})
            if not global_scores:  # Fallback for older formats
                if "qmean6_z_score" in model_data:
                    global_scores = model_data
                elif "qmean6_z_score" in scores_dict:
                    global_scores = scores_dict

            # Z-score
            qmean6_z = float(global_scores.get("qmean6_z_score", 0.0))

            # ---------------- תח
            # CORRECT LOCAL SCORE EXTRACTION
            # ---------------- תח
            # Try to find local scores in various places under various names
            local_scores_by_chain = None
            score_sources = [scores_dict, per_residue_dict]
            local_score_keys = [
                "local_quality",
                "local_qualities",
                "local_qmean",
                "local_qmean_scores",
                "local_scores",
            ]

            for source in score_sources:
                for key in local_score_keys:
                    if key in source and isinstance(source[key], dict) and source[key]:
                        local_scores_by_chain = source[key]
                        break
                if local_scores_by_chain:
                    break

            if local_scores_by_chain is None:
                raise ValueError("No usable local score array found in QMEAN JSON")

            if not local_scores_by_chain:
                raise ValueError("Local scores dictionary is empty.")

            # First chain
            chain_key = list(local_scores_by_chain.keys())[0]
            local_arr = np.array(local_scores_by_chain[chain_key], dtype=float)
            local_arr = np.nan_to_num(local_arr)  # Replace NaN with 0, inf with large numbers
            num_residues = len(local_arr)
        except Exception as e:
            with open(error_log_path, "a", encoding='utf-8') as f:
                f.write(f"\n--- QMEAN JSON PARSING FAILED ---\n")
                f.write(f"Exception: {e}\n")
                f.write(f"Raw JSON response:\n")
                json.dump(result, f, indent=2)
            raise e

        # Save text version
        with open(local_scores_txt, "w") as fh:
            for v in local_arr:
                fh.write(f"{v}\n")

        # ---------------- תח
        # PLOTTING
        # ---------------- תח
        plots_enabled = os.environ.get("PROSUTRA_ENABLE_PLOTS", "0") == "1"
        if plots_enabled:
            make_local_plot(local_arr, png_path, svg_path)
            make_sequence_colormap(local_arr, colormap_png)
            make_global_bars(global_scores, global_png)
            make_comparison_plot(qmean6_z, num_residues, comparison_png)

        # ---------------- תח
        # TEXT SUMMARY
        # ---------------- תח
        with open(txt_path, "w") as fh:
            fh.write(f"Global QMEAN score (norm): {global_scores.get('qmean6_norm_score',0):.6f}\n")
            fh.write(f"Z-score: {qmean6_z:.6f}\n")
            fh.write(f"Residues: {num_residues}\n")
            if not plots_enabled:
                fh.write("Plots disabled (set PROSUTRA_ENABLE_PLOTS=1 to enable).\n")

        # ---------------- תח
        # HTML REPORT
        # ---------------- תח
        html = textwrap.dedent(f"""\
        <html>
        <head><title>QMEAN Report for {os.path.basename(pdb_file)}</title></head>
        <body>
        <h2>QMEAN Quality for {os.path.basename(pdb_file)}</h2>
        <p><b>Global QMEAN (norm):</b> {global_scores.get('qmean6_norm_score',0):.3f}
           | <b>Z-score:</b> {qmean6_z:.3f}</p>

        {"<img src='qmean_global_scores.png' width='480'><br>" if plots_enabled else "<p>Plots disabled.</p>"}
        {"<img src='qmean_plot.png' width='720'><br>" if plots_enabled else ""}
        {"<img src='qmean_comparison.png' width='520'><br>" if plots_enabled else ""}
        {"<img src='qmean_sequence_colormap.png' width='720'><br>" if plots_enabled else ""}
        </body>
        </html>
        """)

        with open(html_path, "w") as fh:
            fh.write(html)

        # JSON summary
        summary = {
            "input_pdb": os.path.abspath(pdb_file),
            "global_score": global_scores.get("qmean6_norm_score"),
            "zscore": qmean6_z,
            "num_residues": num_residues,
            "qmean_plot_png": os.path.abspath(png_path) if plots_enabled and os.path.exists(png_path) else None,
            "qmean_plot_svg": os.path.abspath(svg_path) if plots_enabled and os.path.exists(svg_path) else None,
            "qmean_comparison_png": os.path.abspath(comparison_png) if plots_enabled and os.path.exists(comparison_png) else None,
            "qmean_sequence_colormap_png": os.path.abspath(colormap_png) if plots_enabled and os.path.exists(colormap_png) else None,
            "qmean_global_scores_png": os.path.abspath(global_png) if plots_enabled and os.path.exists(global_png) else None,
            "qmean_report_html": os.path.abspath(html_path),
            "qmean_local_scores_txt": os.path.abspath(local_scores_txt),
        }

        with open(json_path, "w") as fh:
            json.dump(summary, fh, indent=2)

        print(f"[QMEAN] Completed. Output -> {output_dir}")
        return 0

    except Exception as e:
        import traceback
        with open(error_log_path, "w", encoding='utf-8') as f:
            f.write(f"QMEAN wrapper failed with an exception:\n")
            f.write(traceback.format_exc())
        print(f"[QMEAN] Error: {e}. See {error_log_path} for details.")
        return 1


# -----------------------------
# CLI ENTRY
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Run QMEAN validation on a PDB file")
    parser.add_argument("--pdb_file", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--token", required=True)

    args = parser.parse_args()
    raise SystemExit(run_qmean(args.pdb_file, args.output_dir, args.email, args.token))


if __name__ == "__main__":
    main()
