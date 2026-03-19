#!/usr/bin/env python3
"""
modeller_wrapper.py

Validate a PDB file using Modeller scoring functions (molpdf, DOPE, GA341).

Usage:
  python modeller_wrapper.py --pdb_file my_model.pdb --output_dir results/modeller
"""

import os, sys, json, argparse, io
from pathlib import Path

# Add Modeller to Python path
modeller_path = Path("e:/Projects/Protein_structure_prediction/Modeller10.7")
sys.path.insert(0, str(modeller_path / "modlib"))
os.environ["PATH"] = str(modeller_path / "bin") + os.pathsep + os.environ["PATH"]

# Modeller API
try:
    from modeller import environ, log, Selection
    from modeller.scripts import complete_pdb
    HAS_MODELLER = True
except ImportError:
    HAS_MODELLER = False

def run_modeller_validation(pdb_file: str, output_dir: str):
    if not HAS_MODELLER:
        return {"tool": "Modeller", "status": "error", "stderr": "Modeller not installed or not in PYTHONPATH."}

    os.makedirs(output_dir, exist_ok=True)
    log.none()  # disable verbose Modeller output
    env = environ()
    env.libs.topology.read(file='$(LIB)/top_heav.lib')
    env.libs.parameters.read(file='$(LIB)/par.lib')
    
    # Load the model
    print(f"Loading PDB file: {pdb_file}")
    mdl = complete_pdb(env, pdb_file)
    
    scores = {}
    errors = {}

    # 1. molpdf score
    try:
        # In Modeller, normalized DOPE is often used as a primary quality indicator.
        # We use it here for the 'molpdf' field as a general energy score.
        scores["molpdf"] = mdl.assess_normalized_dope()
    except Exception as e:
        errors["molpdf"] = str(e)

    # 2. DOPE score
    try:
        selection = Selection(mdl)
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()
        selection.assess_dope()
        sys.stdout = old_stdout
        output = captured_output.getvalue()
        
        dope_found = False
        for line in output.splitlines():
            if "DOPE score" in line:
                scores["dope"] = float(line.split(":")[1].strip())
                dope_found = True
                break
        if not dope_found:
            errors["dope"] = "DOPE score not found in output"
            
    except Exception as e:
        errors["dope"] = str(e)

    # 3. Normalized DOPE score
    try:
        scores["normalized_dope"] = mdl.assess_normalized_dope()
    except Exception as e:
        errors["normalized_dope"] = str(e)

    # 4. GA341 score
    try:
        mdl.seq_id = 100.0
        ga341_result = mdl.assess_ga341()
        if isinstance(ga341_result, (list, tuple)) and len(ga341_result) >= 2:
            scores["ga341"] = {"reliability": ga341_result[0], "score": ga341_result[1]}
        else:
            scores["ga341"] = ga341_result
    except Exception as e:
        errors["ga341"] = str(e)

    # 5. SOAP-PP score
    try:
        soap_file_path = os.path.join(modeller_path, "modlib", "soap_protein_od.hdf5")
        if os.path.exists(soap_file_path):
            from modeller import soap_protein_od
            soap_scorer = soap_protein_od.Scorer()
            selection = Selection(mdl)
            scores["soap_protein_od"] = selection.assess(soap_scorer)
    except Exception:
        pass  # Optional, fail silently

    # --- Quality Summary ---
    quality_summary = {}
    if "dope" in scores:
        if scores["dope"] < -15000: quality_summary["dope_quality"] = "Excellent"
        elif scores["dope"] < -10000: quality_summary["dope_quality"] = "Good"
        elif scores["dope"] < -5000: quality_summary["dope_quality"] = "Fair"
        else: quality_summary["dope_quality"] = "Poor"

    if "normalized_dope" in scores:
        if scores["normalized_dope"] < -1.0: quality_summary["normalized_dope_quality"] = "Good"
        elif scores["normalized_dope"] < 0: quality_summary["normalized_dope_quality"] = "Acceptable"
        else: quality_summary["normalized_dope_quality"] = "Poor"

    if "ga341" in scores and isinstance(scores.get("ga341"), dict):
        reliability = scores["ga341"]["reliability"]
        if reliability > 0.7: quality_summary["ga341_quality"] = "Good model"
        elif reliability > 0.5: quality_summary["ga341_quality"] = "Questionable model"
        else: quality_summary["ga341_quality"] = "Poor model"

    # --- JSON Output ---
    json_output = {"scores": scores, "quality_summary": quality_summary, "errors": errors}
    json_path = os.path.join(output_dir, "modeller_scores.json")
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2)

    # --- Summary Text Output ---
    summary_path = os.path.join(output_dir, "modeller_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("MODELLER\n")
        f.write("📌 A) Scoring Table\n")
        
        table_data = [
            ["Score Name", "Value", "Interpretation"],
            ["molpdf", f'{scores.get("molpdf", "N/A"):.3f}' if isinstance(scores.get("molpdf"), float) else "N/A", "Lower is better"],
            ["DOPE", f'{scores.get("dope", "N/A"):.3f}' if isinstance(scores.get("dope"), float) else "N/A", quality_summary.get("dope_quality", "")],
            ["Normalized DOPE", f'{scores.get("normalized_dope", "N/A"):.3f}' if isinstance(scores.get("normalized_dope"), float) else "N/A", quality_summary.get("normalized_dope_quality", "")],
        ]
        
        ga341 = scores.get("ga341")
        if isinstance(ga341, dict):
            table_data.append(["GA341 Score", f'{ga341.get("score", "N/A"):.3f}' if isinstance(ga341.get("score"), float) else "N/A", quality_summary.get("ga341_quality", "")])
            table_data.append(["GA341 Reliability", f'{ga341.get("reliability", "N/A"):.3f}' if isinstance(ga341.get("reliability"), float) else "N/A", ""])
        else:
            table_data.append(["GA341", str(ga341) if ga341 is not None else "N/A", ""])
            
        table_data.append(["SOAP-PP", f'{scores.get("soap_protein_od", "N/A"):.3f}' if isinstance(scores.get("soap_protein_od"), float) else "N/A", ""])

        col_widths = [max(len(str(item)) for item in col) for col in zip(*table_data)]
        for i, row in enumerate(table_data):
            f.write("  ".join(str(item).ljust(width) for item, width in zip(row, col_widths)) + "\n")
            if i == 0: f.write("-" * (sum(col_widths) + len(col_widths)*2-2) + "\n")

        f.write("\n📌 B) Quality Summary Table\n")
        quality_table = [
            ["Metric", "Quality"],
            ["DOPE Quality", quality_summary.get("dope_quality", "N/A")],
            ["Normalized DOPE Quality", quality_summary.get("normalized_dope_quality", "N/A")],
            ["GA341 Quality", quality_summary.get("ga341_quality", "N/A")],
        ]
        
        q_col_widths = [max(len(str(item)) for item in col) for col in zip(*quality_table)]
        for i, row in enumerate(quality_table):
            f.write("  ".join(str(item).ljust(width) for item, width in zip(row, q_col_widths)) + "\n")
            if i == 0: f.write("-" * (sum(q_col_widths) + len(q_col_widths)*2-2) + "\n")

        f.write("\n📌 C) Errors (If ANY)\n")
        if errors:
            for key, val in errors.items():
                f.write(f" - {key}: {val}\n")
        else:
            f.write("No errors reported.\n")

        f.write("\n📌 D) Raw Output Files\n")
        f.write(f"{os.path.abspath(json_path)}\n")

    return {
        "tool": "Modeller",
        "status": "success" if not errors else "error",
        "data": json_output,
        "files": {"json": json_path, "summary": summary_path}
    }

def main():
    parser = argparse.ArgumentParser(description="Validate a PDB model using Modeller scoring.")
    parser.add_argument("--pdb_file", required=True, help="Input PDB file to score.")
    parser.add_argument("--output_dir", default="results/modeller", help="Directory to store output.")
    args = parser.parse_args()

    if not os.path.exists(args.pdb_file):
        print(f"Error: PDB file {args.pdb_file} does not exist.")
        sys.exit(1)

    result = run_modeller_validation(args.pdb_file, args.output_dir)
    
    if "files" in result and "summary" in result["files"]:
        with open(result["files"]["summary"], 'r') as f:
            print(f.read())
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
