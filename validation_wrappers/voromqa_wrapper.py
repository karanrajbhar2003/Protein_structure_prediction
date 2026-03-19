#!/usr/bin/env python3
"""
VoroMQA Wrapper
---------------
Runs the local `voronota-js-voromqa` tool to evaluate protein structure quality.

Outputs:
 - voromqa_summary.json : JSON summary (global and per-residue scores)
 - voromqa.txt          : raw output table
 - voromqa_profile.png  : per-residue plot (PNG)
 - voromqa_profile.svg  : per-residue plot (SVG)
"""
import argparse
import os
import json
import subprocess
import sys
import platform
import tempfile
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
import numpy as np
import re
from Bio.PDB import DSSP, PDBParser
import shutil

def is_wsl_available() -> bool:
    """Best-effort check whether WSL can be invoked on this machine."""
    try:
        proc = subprocess.run(
            ["wsl", "--status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False

def convert_path_to_wsl(path):
    """Converts a Windows path to a WSL path."""
    path = path.replace('\\', '/')
    drive, tail = os.path.splitdrive(path)
    drive = drive.replace(':', '').lower()
    return f"/mnt/{drive}{tail}"

def run_in_wsl(script_path, pdb_file, output_dir, voromqa_path):
    """Run this same script inside WSL with converted paths."""
    wsl_script = convert_path_to_wsl(script_path)
    wsl_pdb = convert_path_to_wsl(pdb_file)
    wsl_out = convert_path_to_wsl(output_dir)
    wsl_voromqa = convert_path_to_wsl(voromqa_path)
    cmd = [
        "wsl", "python3", wsl_script,
        "--pdb_file", wsl_pdb,
        "--output_dir", wsl_out,
        "--voromqa_path", wsl_voromqa
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if proc.stdout:
            sys.stdout.write(proc.stdout)

        if proc.stderr:
            sys.stderr.write(proc.stderr)

        sys.exit(proc.returncode)
        
    except subprocess.TimeoutExpired:
        print("Error: WSL process timed out", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: WSL execution failed: {e}", file=sys.stderr)
        sys.exit(1)

def run_voromqa_local(pdb_file, output_dir, voromqa_exe):
    os.makedirs(output_dir, exist_ok=True)
    txt_path = os.path.join(output_dir, "voromqa_residue_scores.txt")
    json_path = os.path.join(output_dir, "voromqa_summary.json")
    png_path = os.path.join(output_dir, "voromqa_profile.png")
    svg_path = os.path.join(output_dir, "voromqa_profile.svg")

    print(f"[VoroMQA] Running on {pdb_file}")
    # voronota-voromqa shell internals can break on spaced paths.
    # Run with no-space temporary paths, then copy the outputs back.
    temp_run_dir = tempfile.mkdtemp(prefix="voromqa_run_")
    safe_input = os.path.join(temp_run_dir, "input.pdb")
    safe_scores = os.path.join(temp_run_dir, "voromqa_residue_scores.txt")
    shutil.copyfile(pdb_file, safe_input)
    cmd = [voromqa_exe, "--input", safe_input, "--output-residue-scores", safe_scores]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[VoroMQA] Error running command: {e}")
        print(f"[VoroMQA] Stderr: {e.stderr}")
        shutil.rmtree(temp_run_dir, ignore_errors=True)
        return 1
    except Exception as e:
        print(f"[VoroMQA] Error running command: {e}")
        shutil.rmtree(temp_run_dir, ignore_errors=True)
        return 1

    if not os.path.exists(safe_scores):
        print(f"[VoroMQA] Error: residue score file was not produced: {safe_scores}")
        shutil.rmtree(temp_run_dir, ignore_errors=True)
        return 1
    shutil.copyfile(safe_scores, txt_path)
    shutil.rmtree(temp_run_dir, ignore_errors=True)

    # Parse the VoroMQA stdout for global score
    global_score = None
    residues = None
    if result.stdout:
        parts = result.stdout.strip().split()
        if len(parts) > 2:
            try:
                global_score = float(parts[1])
                residues = int(parts[2])
            except (ValueError, IndexError):
                pass

    print(f"[VoroMQA] Global score: {global_score}, Residues: {residues}")

    # Parse residue scores from the output file
    x, y = [], []
    if os.path.exists(txt_path):
        with open(txt_path) as f:
            for line in f:
                if line.startswith("#") or line.strip() == "":
                    continue
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        match = re.search(r'r<(\d+)>', parts[0])
                        if match:
                            x.append(int(match.group(1)))
                            y.append(float(parts[-1]))
                    except (ValueError, IndexError):
                        continue

    # --- Enhanced VoroMQA-like Plot with DSSP Support ---
    plt.figure(figsize=(11.5, 4.5), dpi=200)
    ax = plt.gca()

    # Safety checks
    if not x or not y:
        print("[VoroMQA] No residue scores found to plot.")
        return 1

    # --- Plot raw (gray) and smoothed (black) curves ---
    ax.plot(x, y, color='gray', linewidth=1.0, alpha=0.6, label='Raw local scores')
    window = 7
    smooth = np.convolve(y, np.ones(window)/window, mode='same')
    ax.plot(x, smooth, color='black', linewidth=2.4, label='Smoothed local scores')

    # --- Set axes formatting ---
    ax.set_xlim(min(x), max(x))
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Residue number", fontsize=12)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(f"VoroMQA Local Quality Profile (Global Score={global_score:.3f})", fontsize=13)
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.tick_params(axis='both', labelsize=10)

    # --- DSSP secondary structure extraction (automatic) ---
    ss_data = None
    try:
        if shutil.which("mkdssp") is None:
            print("[VoroMQA] Warning: mkdssp executable not found. Skipping secondary structure visualization.")
        else:
            parser = PDBParser(QUIET=True)
            structure = parser.get_structure("model", pdb_file)
            model = structure[0]
            dssp = DSSP(model, pdb_file, dssp='mkdssp')  # requires DSSP installed
            ss_data = [dssp[key][2] for key in list(dssp.keys())]
            if len(ss_data) != len(x):
                ss_data = None
    except Exception as e:
        print(f"[VoroMQA] DSSP parsing skipped ({e})")

    # --- Quality & Secondary Structure Bars ---
    try:
        cmap = plt.get_cmap('coolwarm')
        norm = mcolors.Normalize(vmin=0, vmax=1)

        # Color map for secondary structure types
        ss_colors = {'H': '#e69f00', 'E': '#56b4e9', 'C': '#999999'}

        # Create new axes for color bars
        ax_ss = ax.inset_axes([0, 1.02, 1, 0.08])
        ax_ss.set_xlim(ax.get_xlim())
        ax_ss.set_ylim(0, 1)
        ax_ss.axis('off')

        # Plot quality color strip (blue → red)
        for xi, yi in zip(x, y):
            ax_ss.add_patch(Rectangle((xi - 0.5, 0), 1.0, 0.4, color=cmap(norm(yi)), lw=0))

        # Plot secondary structure strip (if DSSP data available)
        if ss_data:
            for xi, ss in zip(x, ss_data):
                color = ss_colors.get(ss, 'lightgray')
                ax_ss.add_patch(Rectangle((xi - 0.5, 0.45), 1.0, 0.45, color=color, lw=0))

        # Adjust spacing for clean layout
        plt.subplots_adjust(top=0.90)
        ax_ss.set_position([0.125, 0.93, 0.775, 0.05])

    except Exception as e:
        print(f"[VoroMQA] Warning: color bar rendering skipped ({e})")

    # --- Add clean legend for secondary structure colors ---
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D([0], [0], color='#e69f00', lw=6, label='Helix (H)'),
        Line2D([0], [0], color='#56b4e9', lw=6, label='Sheet (E)'),
        Line2D([0], [0], color='#999999', lw=6, label='Coil (C)')
    ]

    if ss_data:
        # Create legend above the plot, with extra space
        ax.legend(
            handles=legend_elements,
            loc='upper center',
            bbox_to_anchor=(0.5, 1.32),  # raised higher
            frameon=False,
            fontsize=9,
            ncol=3,
            handlelength=1.8,
            columnspacing=1.5
        )

        # Adjust top margins so it doesn’t overlap the bars
        plt.subplots_adjust(top=0.84)

    plt.tight_layout()
    plt.savefig(png_path, dpi=200, bbox_inches='tight')
    plt.savefig(svg_path, bbox_inches='tight')
    plt.close()

    # --- Save summary JSON ---
    summary = {
        "input_pdb": os.path.abspath(pdb_file),
        "global_score_dark": global_score,
        "residues": residues,
        "voromqa_profile_png": os.path.abspath(png_path),
        "voromqa_profile_svg": os.path.abspath(svg_path),
    }
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[VoroMQA] Completed successfully. Results written to {output_dir}")
    return 0

def find_voromqa_executable():
    # Check common names for the executable
    if platform.system().lower().startswith("win"):
        exe_names = ["voronota-voromqa.exe", "voronota-voromqa"]
    else:
        exe_names = ["voronota-voromqa", "voronota-voromqa.exe"]

    # 1. Check in project's VoroMQA directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    voromqa_dir = os.path.join(project_root, "VoroMQA")
    if os.path.isdir(voromqa_dir):
        for root, _, files in os.walk(voromqa_dir):
            for name in files:
                if name in exe_names:
                    return os.path.join(root, name)

    # 2. Check system PATH
    for name in exe_names:
        exe_path = shutil.which(name)
        if exe_path:
            return exe_path

    return None

def main():
    parser = argparse.ArgumentParser(description="Run VoroMQA on a PDB file")
    parser.add_argument("--pdb_file", required=True, help="Input PDB file")
    parser.add_argument("--output_dir", required=True, help="Output directory for results")
    parser.add_argument("--voromqa_path", required=False, help="Path to the VoroMQA executable (optional, will be auto-detected)")
    args = parser.parse_args()

    voromqa_exe = args.voromqa_path or find_voromqa_executable()

    is_windows = platform.system().lower().startswith("win")

    # Prefer the native Windows executable when both variants exist.
    if is_windows and voromqa_exe:
        exe_with_ext = f"{voromqa_exe}.exe" if not voromqa_exe.lower().endswith(".exe") else voromqa_exe
        if os.path.exists(exe_with_ext):
            voromqa_exe = exe_with_ext

    if not voromqa_exe or not os.path.exists(voromqa_exe):
        print("[VoroMQA] Error: VoroMQA executable not found.", file=sys.stderr)
        print("[VoroMQA] Please provide the path using --voromqa_path or ensure it's in the system PATH.", file=sys.stderr)
        sys.exit(1)
    
    print(f"[VoroMQA] Using executable: {voromqa_exe}")

    local_rc = run_voromqa_local(args.pdb_file, args.output_dir, voromqa_exe)
    if local_rc == 0:
        sys.exit(0)

    if is_windows and is_wsl_available():
        print("[VoroMQA] Local execution failed. Trying WSL fallback...", file=sys.stderr)
        run_in_wsl(__file__, args.pdb_file, args.output_dir, voromqa_exe)
        return

    if is_windows:
        print(
            "[VoroMQA] WSL fallback is not available. "
            "Use the native Windows executable (voronota-voromqa.exe).",
            file=sys.stderr,
        )
    sys.exit(1)

if __name__ == "__main__":
    main()
