#!/usr/bin/env python3
"""
FreeSASA Wrapper

Usage:
    python validation_wrappers/freesasa_wrapper.py --pdb_file path/to/model.pdb --output_dir results/model1/freesasa

Requirements:
 - freesasa-python library (conda install -c conda-forge freesasa-python)
 - biopython library (pip install biopython)
 - matplotlib

Outputs:
 - freesasa_summary.json : JSON file with total and per-residue solvent accessible surface area
 - freesasa.txt : text summary
 - freesasa_profile.png/svg: Per-residue SASA plot
 - freesasa_hydropathy.png/svg: Hydrophobicity vs SASA plot
 - freesasa_pie.png/svg: SASA composition pie chart
"""
import argparse
import os
import json
import freesasa
from Bio.PDB import PDBParser
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def plot_per_residue_sasa(residue_areas, output_dir):
    res_nums = [r['residue_number'] for r in residue_areas]
    total_areas = [r['total_area'] for r in residue_areas]
    sidechain_areas = [r['side_chain'] for r in residue_areas]
    backbone_areas = [r['main_chain'] for r in residue_areas]

    plt.figure(figsize=(10, 4))
    plt.plot(res_nums, total_areas, label="Total", color="black")
    plt.plot(res_nums, sidechain_areas, label="Side Chain", color="red")
    plt.plot(res_nums, backbone_areas, label="Main Chain", color="blue")
    plt.xlabel("Residue Number")
    plt.ylabel("SASA (Å²)")
    plt.title("Per-Residue Solvent Accessible Surface Area")
    plt.legend()
    plt.grid(True, linestyle='--',
 alpha=0.6)
    plt.tight_layout()

    out_png = os.path.join(output_dir, "freesasa_profile.png")
    out_svg = os.path.join(output_dir, "freesasa_profile.svg")
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_svg)
    plt.close()
    return out_png, out_svg

def plot_hydrophobicity_vs_sasa(residue_areas, output_dir):
    kd = {
        'ALA': 1.8, 'ARG': -4.5, 'ASN': -3.5, 'ASP': -3.5, 'CYS': 2.5,
        'GLN': -3.5, 'GLU': -3.5, 'GLY': -0.4, 'HIS': -3.2, 'ILE': 4.5,
        'LEU': 3.8, 'LYS': -3.9, 'MET': 1.9, 'PHE': 2.8, 'PRO': -1.6,
        'SER': -0.8, 'THR': -0.7, 'TRP': -0.9, 'TYR': -1.3, 'VAL': 4.2
    }
    h_values = [kd.get(r['residue_name'], 0) for r in residue_areas]
    total_areas = [r['total_area'] for r in residue_areas]

    plt.figure(figsize=(8, 6))
    sc = plt.scatter(h_values, total_areas, c=total_areas, cmap="coolwarm", alpha=0.8)
    plt.xlabel("Hydropathy (Kyte & Doolittle)")
    plt.ylabel("SASA (Å²)")
    plt.title("Hydrophobicity vs SASA")
    plt.colorbar(sc, label="SASA (Å²)")
    plt.grid(True, linestyle='--',
 alpha=0.4)
    plt.tight_layout()

    out_png = os.path.join(output_dir, "freesasa_hydropathy.png")
    out_svg = os.path.join(output_dir, "freesasa_hydropathy.svg")
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_svg)
    plt.close()
    return out_png, out_svg

def plot_sasa_composition_pie(residue_areas, output_dir):
    total_sidechain = sum(r['side_chain'] for r in residue_areas)
    total_backbone = sum(r['main_chain'] for r in residue_areas)

    plt.figure(figsize=(6, 6))
    plt.pie([total_sidechain, total_backbone], labels=["Side Chain", "Backbone"], autopct='%1.1f%%',
            colors=['#ff9999','#66b3ff'])
    plt.title("SASA Composition")
    plt.tight_layout()
    
    out_png = os.path.join(output_dir, "freesasa_pie.png")
    out_svg = os.path.join(output_dir, "freesasa_pie.svg")
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_svg)
    plt.close()
    return out_png, out_svg

def run_freesasa(pdb_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    error_log_path = os.path.join(output_dir, "freesasa_error.log")

    try:
        print(f"[FreeSASA] Calculating solvent accessible surface area for {pdb_file}")

        residue_map = {}
        try:
            # Use Bio.PDB to parse the file and get residue names, but don't fail if it has issues
            parser = PDBParser(QUIET=True)
            structure_bp = parser.get_structure("s", pdb_file)
            for model in structure_bp:
                for chain in model:
                    for residue in chain:
                        res_id = residue.get_id()
                        res_name = residue.get_resname()
                        res_num = res_id[1]
                        chain_id = chain.get_id()
                        residue_map[(chain_id, res_num)] = res_name
        except Exception as e:
            print(f"[FreeSASA] Warning: Bio.PDB parser failed ('{e}'). Will proceed without residue names.")
            pass

        # Create freesasa.Structure directly from the file
        structure_fs = freesasa.Structure(pdb_file)
        result = freesasa.calc(structure_fs)
        residue_areas_raw = result.residueAreas()

        total_area = result.totalArea()
        
        processed_residue_areas = []
        # Iterate through freesasa's results
        for chain_id, residues in residue_areas_raw.items():
            for res_num_str, area_obj in residues.items():
                res_num = int(res_num_str)
                res_name = residue_map.get((chain_id, res_num), "UNK") # Get name from map, or default to UNK
                
                processed_residue_areas.append({
                    "chain": chain_id,
                    "residue_number": res_num,
                    "residue_name": res_name,
                    "total_area": area_obj.total,
                    "side_chain": area_obj.sideChain,
                    "main_chain": area_obj.mainChain,
                })
        
        # Sort by chain and residue number for consistency
        processed_residue_areas.sort(key=lambda x: (x['chain'], x['residue_number']))

        # Plot generation is optional; some Windows envs crash in savefig.
        profile_png = profile_svg = None
        hydro_png = hydro_svg = None
        pie_png = pie_svg = None
        if os.environ.get("PROSUTRA_ENABLE_PLOTS", "0") == "1":
            profile_png, profile_svg = plot_per_residue_sasa(processed_residue_areas, output_dir)
            hydro_png, hydro_svg = plot_hydrophobicity_vs_sasa(processed_residue_areas, output_dir)
            pie_png, pie_svg = plot_sasa_composition_pie(processed_residue_areas, output_dir)

        summary = {
            "input_pdb": os.path.abspath(pdb_file),
            "total_area": total_area,
            "num_residues": len(processed_residue_areas),
            "residue_areas": processed_residue_areas,
            "profile_plot_png": profile_png,
            "profile_plot_svg": profile_svg,
            "hydropathy_plot_png": hydro_png,
            "hydropathy_plot_svg": hydro_svg,
            "pie_chart_png": pie_png,
            "pie_chart_svg": pie_svg,
        }

        # write outputs
        with open(os.path.join(output_dir, "freesasa_summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
        with open(os.path.join(output_dir, "freesasa.txt"), "w") as f:
            f.write(f"Total solvent-accessible surface area: {total_area:.2f} Å²\n")
            f.write(f"Residues analyzed: {len(processed_residue_areas)}\n")
            if os.environ.get("PROSUTRA_ENABLE_PLOTS", "0") != "1":
                f.write("Plots disabled (set PROSUTRA_ENABLE_PLOTS=1 to enable).\n")

        print(f"[FreeSASA] Completed. Results written to {output_dir}")
        return 0
    except Exception as e:
        import traceback
        with open(error_log_path, "w", encoding='utf-8') as f:
            f.write(f"FreeSASA wrapper failed with an exception:\n")
            f.write(traceback.format_exc())
        print(f"[FreeSASA] Error: {e}. See {error_log_path} for details.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Run FreeSASA on a PDB file")
    parser.add_argument("--pdb_file", required=True, help="Input PDB file")
    parser.add_argument("--output_dir", required=True, help="Output directory for FreeSASA results")
    parser.add_argument("--freesasa_path", default="freesasa", help="Path to the freesasa executable")
    args = parser.parse_args()
    raise SystemExit(run_freesasa(args.pdb_file, args.output_dir))

if __name__ == "__main__":
    main()
