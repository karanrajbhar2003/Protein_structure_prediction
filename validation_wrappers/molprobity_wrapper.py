#!/usr/bin/env python3
r"""
molprobity_wrapper.py

Run MolProbity (via Phenix) and optionally generate a Ramachandran plot.

Usage (Windows):
  python molprobity_wrapper.py --pdb_file E:\path\to\model.pdb --output_dir E:\path\to\out

Usage (WSL/Linux):
  python3 molprobity_wrapper.py --pdb_file /home/mahesh/model.pdb --output_dir /home/mahesh/out
"""
import os
import sys
import json
import argparse
import subprocess
import shutil
import platform
import re

# matplotlib is optional. If not available, we'll still save rama data JSON.
try:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    HAS_MPL = True
except Exception:
    HAS_MPL = False

# Default phenix bin fallback (WSL path)
DEFAULT_PHENIX_BIN = "/home/mahesh/phenix/phenix-1.21.2-5419/build/bin"

HARMLESS_PATTERNS = [
    "dials command line completion not available",
    'libtbx.find_in_repositories: cannot locate "dials/util/autocomplete.sh"',
    "source: filename argument required",
    "source: usage: source filename [arguments]",
]

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

def to_wsl_path(path: str) -> str:
    """Convert a Windows path (C:\\...) to WSL style (/mnt/c/...)."""
    if not path:
        return path
    path = os.path.abspath(path)
    if path.startswith("/mnt/") or path.startswith("/home/") or path.startswith("/root/"):
        return path
    drive, tail = os.path.splitdrive(path)
    if not drive:
        return path.replace("\\", "/")
    drive_letter = drive.rstrip(":").lower()
    tail = tail.replace("\\", "/")
    if tail.startswith("/"):
        tail = tail[1:]
    return f"/mnt/{drive_letter}/{tail}"

def filter_stderr_text(stderr_text: str) -> str:
    """Remove harmless known warnings from stderr_text; return the filtered string."""
    if not stderr_text:
        return ""
    out_lines = []
    for line in stderr_text.splitlines():
        low = line.lower()
        if any(pat.lower() in low for pat in HARMLESS_PATTERNS):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)

def run_in_wsl(script_path, pdb_file, output_dir, phenix_path=None):
    """Run this same script inside WSL with converted paths and print captured results."""
    wsl_script = to_wsl_path(script_path)
    wsl_pdb = to_wsl_path(pdb_file)
    wsl_out = to_wsl_path(output_dir)

    inner_cmd = f"python3 '{wsl_script}' --pdb_file '{wsl_pdb}' --output_dir '{wsl_out}'"
    if phenix_path:
        inner_cmd += f" --phenix_path '{phenix_path}'"

    cmd = ["wsl", "bash", "-ic", inner_cmd]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if proc.stdout:
            sys.stdout.write(proc.stdout)

        filtered_err = filter_stderr_text(proc.stderr or "")
        if filtered_err.strip():
            sys.stderr.write(filtered_err + ("\n" if not filtered_err.endswith("\n") else ""))

        sys.exit(proc.returncode)
        
    except subprocess.TimeoutExpired:
        print("Error: WSL process timed out", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: WSL execution failed: {e}", file=sys.stderr)
        sys.exit(1)

def find_executable(name: str, phenix_path: str = None):
    """Find an executable either in PATH or at provided phenix_path or default phenix bin."""
    exe = shutil.which(name)
    if exe:
        return exe

    candidates = []
    if phenix_path:
        candidates.append(os.path.join(phenix_path, name))
    candidates.append(os.path.join(DEFAULT_PHENIX_BIN, name))

    if platform.system().lower().startswith("win"):
        win_exts = ["", ".exe", ".bat", ".cmd"]
    else:
        win_exts = [""]

    for base in candidates:
        for ext in win_exts:
            candidate = base + ext
            if os.path.exists(candidate):
                return candidate
    return None

def create_ramachandran_regions():
    """
    Create the traditional Ramachandran allowed regions based on statistical analysis.
    Returns a 2D array where values represent different allowed regions.
    """
    # Create 360x360 grid for phi/psi space (-180 to 180)
    phi_range = np.linspace(-180, 180, 360)
    psi_range = np.linspace(-180, 180, 360)
    
    # Initialize regions array (0 = disallowed, 1 = generously allowed, 2 = allowed, 3 = most favored)
    regions = np.zeros((360, 360))
    
    # Define regions based on Ramachandran statistics
    for i, phi in enumerate(phi_range):
        for j, psi in enumerate(psi_range):
            # Alpha-helix region (right-handed) - refined boundaries
            if -100 <= phi <= -30 and -67 <= psi <= 50:
                if -80 <= phi <= -50 and -50 <= psi <= -10:
                    regions[j, i] = 3  # Most favored
                else:
                    regions[j, i] = 2  # Allowed
            
            # Beta-strand region - refined boundaries
            elif -180 <= phi <= -90 and 90 <= psi <= 180:
                if -150 <= phi <= -110 and 110 <= psi <= 150:
                    regions[j, i] = 3  # Most favored
                else:
                    regions[j, i] = 2  # Allowed
            
            # Left-handed alpha-helix region (rare, mostly Gly)
            elif 30 <= phi <= 100 and 30 <= psi <= 100:
                if 45 <= phi <= 85 and 45 <= psi <= 85:
                    regions[j, i] = 2  # Allowed
                else:
                    regions[j, i] = 1  # Generously allowed
            
            # Additional allowed regions - more conservative
            elif (-180 <= phi <= -90 and 50 <= psi <= 90) or \
                 (-100 <= phi <= -60 and 90 <= psi <= 180) or \
                 (90 <= phi <= 180 and -180 <= psi <= -120):
                regions[j, i] = 1  # Generously allowed
    
    return regions, phi_range, psi_range

def run_ramalyze(pdb_file, output_dir, phenix_path=None):
    """Run phenix.ramalyze, parse its output, save JSON, and generate enhanced Ramachandran plot."""
    os.makedirs(output_dir, exist_ok=True)
    ramalyze_cmd = find_executable("phenix.ramalyze", phenix_path)
    if not ramalyze_cmd:
        return None

    try:
        proc = subprocess.run(
            [ramalyze_cmd, pdb_file],
            cwd=output_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
    except Exception:
        return None

    phi, psi = [], []
    residue_info = []
    
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("residue:") or line.startswith("SUMMARY"):
            continue
        fields = line.split(":")
        if len(fields) >= 4:
            try:
                residue = fields[0].strip()
                phi_val = float(fields[2])
                psi_val = float(fields[3])
                phi.append(phi_val)
                psi.append(psi_val)
                residue_info.append(residue)
            except ValueError:
                continue

    if not phi:
        return None

    # Save data
    data_file = os.path.join(output_dir, "ramachandran_data.json")
    with open(data_file, "w") as f:
        json.dump({
            "phi": phi, 
            "psi": psi, 
            "residues": residue_info
        }, f, indent=2)

    plot_paths = {}
    if HAS_MPL:
        # Create figure with specific layout for external elements
        fig = plt.figure(figsize=(16, 8))
        
        # Create main plot area (left 60% of figure)
        ax = fig.add_subplot(1, 1, 1)
        ax.set_position([0.1, 0.15, 0.5, 0.7])  # [left, bottom, width, height]
        
        # Create Ramachandran regions
        regions, phi_range, psi_range = create_ramachandran_regions()
        
        # Define colors: white (disallowed), light beige (generously), yellow (allowed), red (most favored)
        colors = ['white', '#F0F0DC', '#FFD700', '#DC143C']  # white, beige, gold, crimson
        cmap = ListedColormap(colors)
        
        # Plot the background regions
        im = ax.imshow(regions, extent=[-180, 180, -180, 180], 
                      cmap=cmap, vmin=0, vmax=3, origin='lower', alpha=0.85)
        
        # Plot data points - slightly larger and better contrast
        scatter = ax.scatter(phi, psi, s=40, c='navy', alpha=0.9, edgecolors='white', linewidth=0.8)
        
        # Customize plot - enhanced font sizes for publication quality
        ax.set_xlabel('φ (Phi) degrees', fontsize=18, fontweight='bold')
        ax.set_ylabel('ψ (Psi) degrees', fontsize=18, fontweight='bold')
        ax.set_title('Ramachandran Plot', fontsize=20, fontweight='bold', pad=30)
        
        # Set limits and ticks
        ax.set_xlim(-180, 180)
        ax.set_ylim(-180, 180)
        ax.set_xticks(np.arange(-180, 181, 45))
        ax.set_yticks(np.arange(-180, 181, 45))
        ax.tick_params(labelsize=14)
        
        # Add very light grid for clean aesthetic
        ax.grid(True, linestyle='--', alpha=0.25, color='gray', linewidth=0.4)
        ax.set_axisbelow(True)
        
        # Add region labels
        ax.text(-65, -35, 'α', fontsize=24, fontweight='bold', ha='center', va='center', 
                bbox=dict(boxstyle='circle', facecolor='white', alpha=0.8))
        ax.text(-130, 135, 'β', fontsize=24, fontweight='bold', ha='center', va='center',
                bbox=dict(boxstyle='circle', facecolor='white', alpha=0.8))
        ax.text(65, 65, 'L', fontsize=20, fontweight='bold', ha='center', va='center',
                bbox=dict(boxstyle='circle', facecolor='white', alpha=0.8))
        
        # Add reference lines
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.4, linewidth=0.8)
        ax.axvline(x=0, color='black', linestyle='-', alpha=0.4, linewidth=0.8)
        
        # Calculate statistics correctly
        total_residues = len(phi)
        most_favored = allowed = generously_allowed = outliers = 0
        
        for p, s in zip(phi, psi):
            # Convert to array indices
            phi_idx = int((p + 180) * 359 / 360)
            psi_idx = int((s + 180) * 359 / 360)
            phi_idx = max(0, min(359, phi_idx))
            psi_idx = max(0, min(359, psi_idx))
            
            region_val = regions[psi_idx, phi_idx]
            if region_val == 3:
                most_favored += 1
            elif region_val == 2:
                allowed += 1
            elif region_val == 1:
                generously_allowed += 1
            else:
                outliers += 1
        
        # Add legend completely outside plot area (right side, top)
        legend_elements = [
            Patch(facecolor='#DC143C', label='Most favored regions'),
            Patch(facecolor='#FFD700', label='Additionally allowed regions'),  
            Patch(facecolor='#F0F0DC', label='Generously allowed regions'),
            Patch(facecolor='white', edgecolor='black', label='Disallowed regions'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='navy', 
                      markersize=10, label='Residue positions')
        ]
        
        # Position legend in right area of figure
        legend = fig.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(0.65, 0.9), 
                           frameon=True, fancybox=True, shadow=True, fontsize=13, title='Legend',
                           title_fontsize=14)
        legend.get_frame().set_alpha(0.98)
        
        # Add statistics text completely outside plot area (right side, bottom)
        stats_text = f"""Ramachandran Statistics:
Total residues: {total_residues}
Most favored: {most_favored} ({most_favored/total_residues*100:.1f}%)
Additionally allowed: {allowed} ({allowed/total_residues*100:.1f}%)
Generously allowed: {generously_allowed} ({generously_allowed/total_residues*100:.1f}%)
Outliers: {outliers} ({outliers/total_residues*100:.1f}%)

Favored (most + additional): {most_favored + allowed} ({(most_favored + allowed)/total_residues*100:.1f}%)"""
        
        # Position stats text in right area of figure
        fig.text(0.65, 0.45, stats_text, fontsize=13, verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#f8f9fa', alpha=0.98, 
                         edgecolor='gray', linewidth=1))
        
        # Save both SVG and PNG formats
        svg_path = os.path.join(output_dir, "ramachandran_plot.svg")
        png_path = os.path.join(output_dir, "ramachandran_plot.png")
        
        plt.savefig(svg_path, format="svg", dpi=300, bbox_inches='tight', pad_inches=0.3)
        plt.savefig(png_path, format="png", dpi=300, bbox_inches='tight', pad_inches=0.3)
        plt.close()
        
        plot_paths = {"svg": svg_path, "png": png_path}

    return plot_paths

def run_molprobity_local(pdb_file, output_dir, phenix_path=None):
    """Run phenix.molprobity (assumes running inside WSL/Linux where phenix is available)."""
    os.makedirs(output_dir, exist_ok=True)
    pdb_file_abs = os.path.abspath(pdb_file)

    phenix_cmd = find_executable("phenix.molprobity", phenix_path)
    if not phenix_cmd:
        return {"tool": "MolProbity", "status": "error",
                "stderr": "phenix.molprobity not found. Use --phenix_path or ensure Phenix in PATH."}

    try:
        proc = subprocess.run(
            [phenix_cmd, pdb_file_abs, "output.prefix=molprobity", "output.overwrite=True"],
            cwd=output_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
    except Exception as e:
        return {"tool": "MolProbity", "status": "error", "stderr": str(e)}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    filtered_stderr = filter_stderr_text(stderr)
    log_file = os.path.join(output_dir, "molprobity.log")
    with open(log_file, "w", encoding="utf-8") as fh:
        fh.write(stdout)
        fh.write("\n\n--- STDERR (filtered) ---\n")
        fh.write(filtered_stderr)

    # Parse MolProbity output - improved parsing
    molprobity_summary = {
        "molprobity_score": None, "clashscore": None,
        "ramachandran": {"favored": None, "allowed": None, "outliers": None},
        "rotamers": {"outliers": None},
        "cbeta_deviations": None,
        "bond_rmsd": None, "angle_rmsd": None,
        "worst_clashes": []
    }
    
    # --- NEW: Robust parsing of the summary block ---
    in_summary = False
    for line in stdout.splitlines():
        L = line.strip()
        
        if L.startswith("="*20) and "Summary" in L:
            in_summary = True
            continue

        if not in_summary:
            continue
            
        # Inside summary block
        if "=" in L:
            key, val = L.split("=", 1)
            key = key.strip().lower()
            val = val.strip()
            
            if "molprobity score" in key:
                match = re.search(r"([\d.]+)", val)
                if match: molprobity_summary["molprobity_score"] = float(match.group(1))
            elif "clashscore" in key:
                match = re.search(r"([\d.]+)", val)
                if match: molprobity_summary["clashscore"] = float(match.group(1))
            elif "ramachandran outliers" in key:
                match = re.search(r"([\d.]+)%", val)
                if match: molprobity_summary["ramachandran"]["outliers"] = float(match.group(1))
            elif key.startswith("favored") and "rama" not in key: # Avoid "Ramachandran favored"
                 match = re.search(r"([\d.]+)%", val)
                 if match: molprobity_summary["ramachandran"]["favored"] = float(match.group(1))
            elif "rotamer outliers" in key:
                match = re.search(r"([\d.]+)%", val)
                if match: molprobity_summary["rotamers"]["outliers"] = float(match.group(1))
            elif "c-beta deviations" in key:
                match = re.search(r"(\d+)", val)
                if match: molprobity_summary["cbeta_deviations"] = int(match.group(1))
            elif "rms(bonds)" in key:
                match = re.search(r"([\d.]+)", val)
                if match: molprobity_summary["bond_rmsd"] = float(match.group(1))
            elif "rms(angles)" in key:
                match = re.search(r"([\d.]+)", val)
                if match: molprobity_summary["angle_rmsd"] = float(match.group(1))

    # Post-process: The summary block doesn't have "allowed", so we calculate it.
    # We need to parse the main block for this one value. This is a bit ugly but necessary.
    for line in stdout.splitlines():
        low_L = line.lower()
        if "ramachandran plot" in low_L and "allowed" in low_L:
             match = re.search(r"allowed\s*:\s*([\d.]+)%", low_L)
             if match:
                 molprobity_summary["ramachandran"]["allowed"] = float(match.group(1))
                 break

    # Parse probe.txt for worst clashes
    probe_file = os.path.join(output_dir, "molprobity_probe.txt")
    probe_clashes = []
    if os.path.exists(probe_file):
        with open(probe_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("CLASH:"):
                    # Universal parser for different MolProbity versions
                    # Handles formats like:
                    # CLASH: A:45:ARG:NH1 B:36:GLU:OE1 overlap=0.78
                    # CLASH: A:45:ARG:NH1   B:36:GLU:OE1    overlap=0.78
                    # CLASH: A:45:ARG:NH1 B:36:GLU:OE1 clash overlap 0.78
                    # CLASH: A:45:ARG:NH1 B:36:GLU:OE1 dist=2.1 overlap=0.78
                    # CLASH: A:45:ARG:NH1-B:36:GLU:OE1 overlap=0.78
                    
                    # Remove leading "CLASH:" and split everything else
                    parts = re.split(r"\s+", line.replace("CLASH:", "").strip())

                    # Detect atom labels (e.g., A:45:ARG:NH1) and handle hyphenated cases
                    raw_atoms = [p for p in parts if ":" in p and p.count(":") >= 3]
                    atoms = []
                    for atom_part in raw_atoms:
                        atoms.extend(re.split(r'-(?=[A-Z]:)', atom_part))

                    # Find overlap value
                    overlap = None
                    for p in parts:
                        # Match formats like overlap=0.78 or overlap 0.78
                        m = re.search(r"overlap\s*=?\s*([0-9.]+)", p)
                        if m:
                            overlap = float(m.group(1))
                            break
                    
                    # Ensure we have at least two atoms and an overlap value
                    if overlap is not None and len(atoms) >= 2:
                        atom1, atom2 = atoms[:2]
                        probe_clashes.append({
                            "atom1": atom1,
                            "atom2": atom2,
                            "overlap": overlap
                        })
    
    molprobity_summary["worst_clashes"] = sorted(
        probe_clashes, key=lambda x: x["overlap"], reverse=True
    )[:10]


    rama_plots = run_ramalyze(pdb_file_abs, output_dir, phenix_path=phenix_path)

    # Save summary JSON
    summary_path = os.path.join(output_dir, "molprobity_summary.json")
    with open(summary_path, "w") as f:
        json.dump(molprobity_summary, f, indent=4)

    result = {
        "tool": "MolProbity",
        "status": "success" if (
            proc.returncode == 0 and 
            molprobity_summary["molprobity_score"] is not None
        ) else "error",
        "metrics": molprobity_summary,
        "files": {
            "log": log_file,
            "summary_json": summary_path,
            "probe_txt": probe_file if os.path.exists(probe_file) else None,
            "ramachandran_plot_svg": rama_plots.get("svg") if rama_plots else None,
            "ramachandran_plot_png": rama_plots.get("png") if rama_plots else None,
            "ramachandran_data": os.path.join(output_dir, "ramachandran_data.json")
                if os.path.exists(os.path.join(output_dir, "ramachandran_data.json")) else None
        }
    }
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Run MolProbity validation on a PDB file.")
    parser.add_argument("--pdb_file", required=True, help="Path to the input PDB file.")
    parser.add_argument("--phenix_path", help="Optional: path to Phenix bin directory (WSL path).")
    parser.add_argument("--output_dir", default="results/molprobity", help="Directory for output files.")
    args = parser.parse_args()

    is_windows = platform.system().lower().startswith("win")

    result = run_molprobity_local(args.pdb_file, args.output_dir, phenix_path=args.phenix_path)
    local_ok = result.get("status") == "success"

    if local_ok:
        print(json.dumps(result, indent=2))
        sys.exit(0)

    if is_windows and is_wsl_available():
        print("[MolProbity] Local execution failed. Trying WSL fallback...", file=sys.stderr)
        run_in_wsl(__file__, args.pdb_file, args.output_dir, phenix_path=args.phenix_path)
        return

    if is_windows:
        stderr = result.get("stderr", "")
        note = (
            "WSL fallback is not available on this system. "
            "Install/enable WSL or configure a native Windows Phenix executable "
            "(phenix.molprobity) via PATH or --phenix_path."
        )
        result["stderr"] = f"{stderr}\n{note}".strip()

    print(json.dumps(result, indent=2))
    sys.exit(1)

if __name__ == "__main__":
    main()
