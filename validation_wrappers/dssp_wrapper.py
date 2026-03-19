#!/usr/bin/env python3
"""
DSSP Wrapper

Usage:
    python validation_wrappers/dssp_wrapper.py --pdb_file path/to/model.pdb --output_dir results/model1/dssp

Requirements:
 - Biopython installed (pip install biopython)
 - mkdssp executable available in system PATH (part of DSSP package)
 - Matplotlib installed

Outputs:
 - dssp_summary.json : JSON file with per-residue data and plot paths
 - dssp.txt : simple text summary
 - dssp_secondary_structure.png/svg : Plot of secondary structure composition
 - dssp_hydropathy_plot.png/svg : Plot of hydropathy vs. accessibility
"""
import argparse
import os
import json
import shutil
import sys
import warnings
from pathlib import Path
from Bio.PDB import PDBParser, DSSP
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import Counter

def find_executable(executable):
    """Finds an executable in the system's PATH."""
    if os.path.isfile(executable):
        return executable
    
    # For Windows, add .exe
    if os.name == 'nt' and not executable.endswith('.exe'):
        executable += '.exe'

    # Search in PATH
    for path in os.environ.get('PATH', '').split(os.pathsep):
        exe_path = os.path.join(path, executable)
        if os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
            return exe_path
    return None


def find_libcifpp_data_dir(resolved_dssp_path):
    """Find a libcifpp directory that contains required DSSP dictionary files."""
    existing = os.environ.get("LIBCIFPP_DATA_DIR")
    if existing:
        p = Path(existing)
        if (p / "components.cif").exists() and (p / "mmcif_pdbx.dic").exists():
            return str(p)

    dssp_path = Path(resolved_dssp_path).resolve()
    py_dir = Path(sys.executable).resolve().parent
    candidates = [
        # Common conda layout
        py_dir / "share" / "libcifpp",
        py_dir / "Library" / "share" / "libcifpp",
        # Relative to mkdssp location
        dssp_path.parent.parent.parent / "share" / "libcifpp",
        dssp_path.parent.parent / "share" / "libcifpp",
    ]

    for c in candidates:
        if (c / "components.cif").exists() and (c / "mmcif_pdbx.dic").exists():
            return str(c)
    return None

def plot_secondary_structure(residues, output_dir):
    ss_list = [r["secondary_structure"] for r in residues]
    
    # Convert DSSP symbols to simplified H/E/C
    ss_map = {'H': 'Helix', 'G': 'Helix', 'I': 'Helix',
              'E': 'Sheet', 'B': 'Sheet',
              'T': 'Coil', 'S': 'Coil', '-': 'Coil'}
    
    ss_simplified = [ss_map.get(ss, 'Coil') for ss in ss_list]
    counts = Counter(ss_simplified)

    labels = ['Helix', 'Sheet', 'Coil']
    values = [counts.get(l, 0) for l in labels]

    plt.figure(figsize=(5, 4))
    plt.bar(labels, values, color=['#e69f00', '#56b4e9', '#999999'])
    plt.ylabel("Residue Count")
    plt.title("Secondary Structure Composition (DSSP)", fontsize=14)
    plt.tight_layout()

    out_png = os.path.join(output_dir, "dssp_secondary_structure.png")
    out_svg = os.path.join(output_dir, "dssp_secondary_structure.svg")
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_svg)
    plt.close()

    return out_png, out_svg

def plot_hydropathy_vs_accessibility(residues, output_dir):
    # Kyte & Doolittle hydropathy scale
    kd = {
        'A': 1.8, 'C': 2.5, 'D': -3.5, 'E': -3.5, 'F': 2.8,
        'G': -0.4, 'H': -3.2, 'I': 4.5, 'K': -3.9, 'L': 3.8,
        'M': 1.9, 'N': -3.5, 'P': -1.6, 'Q': -3.5, 'R': -4.5,
        'S': -0.8, 'T': -0.7, 'V': 4.2, 'W': -0.9, 'Y': -1.3
    }

    hydro = []
    acc = []

    for r in residues:
        aa = r["amino_acid"]
        if aa in kd:
            hydro.append(kd[aa])
            acc.append(r["accessibility"])  # DSSP absolute accessibility

    plt.figure(figsize=(6, 4))
    plt.scatter(hydro, acc, c=hydro, cmap="coolwarm", edgecolor='black', s=50)
    plt.xlabel("Hydropathy (Kyte & Doolittle)")
    plt.ylabel("DSSP Accessibility")
    plt.title("Hydropathy vs Solvent Accessibility", fontsize=14)
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    out_png = os.path.join(output_dir, "dssp_hydropathy_plot.png")
    out_svg = os.path.join(output_dir, "dssp_hydropathy_plot.svg")
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_svg)
    plt.close()

    return out_png, out_svg

def run_dssp(pdb_file, output_dir, dssp_path="mkdssp"):
    os.makedirs(output_dir, exist_ok=True)
    error_log_path = os.path.join(output_dir, "dssp_error.log")

    try:
        resolved_dssp_path = find_executable(dssp_path)
        if not resolved_dssp_path:
            raise FileNotFoundError(
                f"Could not find the '{dssp_path}' executable. "
                "Please ensure it is installed and in your system's PATH, "
                "or provide the full path via the --dssp_path argument."
            )

        # mkdssp (libcifpp) needs dictionary files; set env var automatically when possible.
        libcifpp_dir = find_libcifpp_data_dir(resolved_dssp_path)
        if libcifpp_dir:
            os.environ["LIBCIFPP_DATA_DIR"] = libcifpp_dir

        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("model", pdb_file)
        model = structure[0]
        
        with warnings.catch_warnings():
            # mkdssp 4.x may emit a benign mmCIF parse warning before PDB fallback.
            warnings.filterwarnings(
                "ignore",
                message="parse error at line 1: This file does not seem to be an mmCIF file",
            )
            dssp = DSSP(model, pdb_file, dssp=resolved_dssp_path)

        residues = []
        for res_key in dssp.keys():
            aa, ss, acc = dssp[res_key][1], dssp[res_key][2], dssp[res_key][3]
            chain = res_key[0]
            resnum = res_key[1][1]
            residues.append({
                "chain": chain,
                "residue_number": resnum,
                "amino_acid": aa,
                "secondary_structure": ss,
                "accessibility": acc
            })

        # Plot generation is optional because some Windows envs crash on savefig.
        ss_png, ss_svg, hyd_png, hyd_svg = None, None, None, None
        if os.environ.get("PROSUTRA_ENABLE_PLOTS", "0") == "1":
            ss_png, ss_svg = plot_secondary_structure(residues, output_dir)
            hyd_png, hyd_svg = plot_hydropathy_vs_accessibility(residues, output_dir)

        summary = {
            "total_residues": len(residues),
            "residues": residues,
            "secondary_structure_plot_png": ss_png,
            "secondary_structure_plot_svg": ss_svg,
            "hydropathy_accessibility_png": hyd_png,
            "hydropathy_accessibility_svg": hyd_svg
        }

        # Write outputs
        with open(os.path.join(output_dir, "dssp_summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
        with open(os.path.join(output_dir, "dssp.txt"), "w") as f:
            f.write(f"Residues analyzed: {len(residues)}\n")
            if os.environ.get("PROSUTRA_ENABLE_PLOTS", "0") != "1":
                f.write("Plots disabled (set PROSUTRA_ENABLE_PLOTS=1 to enable).\n")

        print(f"[DSSP] Completed. Results written to {output_dir}")
        return 0
    except Exception as e:
        import traceback
        with open(error_log_path, "w", encoding='utf-8') as f:
            f.write(f"DSSP wrapper failed with an exception:\n")
            f.write(traceback.format_exc())
        print(f"[DSSP] Error: {e}. See {error_log_path} for details.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run DSSP validation on a PDB file")
    parser.add_argument("--pdb_file", required=True, help="Input PDB file")
    parser.add_argument("--output_dir", required=True, help="Output directory for DSSP results")
    parser.add_argument("--dssp_path", default="mkdssp", help="Path to the mkdssp executable")
    args = parser.parse_args()
    raise SystemExit(run_dssp(args.pdb_file, args.output_dir, dssp_path=args.dssp_path))

if __name__ == "__main__":
    main()
