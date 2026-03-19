import sys
import logging
import os
import time
import re
import argparse
from typing import Optional
from datetime import datetime

# Allow importing from src if needed
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from modeller_utils import run_modeller_homology_modeling

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Modeller Configuration ---
# IMPORTANT: It is recommended to set this as an environment variable
MODELLER_LICENSE_KEY = os.getenv("MODELLER_KEY", "MODELIRANJE")

# Cross-platform path handling for Modeller installation
MODELLER_PATH = os.getenv("MODELLER_PATH")
if not MODELLER_PATH:
    raise EnvironmentError("MODELLER_PATH environment variable is not set. Please point it to your Modeller installation directory.")

os.environ["MODINSTALL"] = MODELLER_PATH
logging.debug(f"MODINSTALL set to {os.environ['MODINSTALL']}")

# Path to the Modeller PDB database (pdb_95.pir.gz)
PDB_DB_PATH = os.getenv("PDB_DB_PATH")
if not PDB_DB_PATH:
    PDB_DB_PATH = os.path.join(MODELLER_PATH, "pdb_95.pir.gz")

    PDB_DB_PATH = os.path.normpath(PDB_DB_PATH)


def parse_alignment_file(alignment_file, job_name, template_codes):
    """Parse alignment file to compute sequence identity and coverage."""
    seq_identity = 0.0
    coverage = 0.0
    try:
        with open(alignment_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            sequences = {}
            current_seq_name = ""
            for line in lines:
                if line.startswith('>P1;'):
                    current_seq_name = line.split(';')[1].strip()
                    sequences[current_seq_name] = ""
                elif current_seq_name and not line.startswith('>') and line.strip():
                    sequences[current_seq_name] += line.strip()

            target_seq = sequences.get(job_name)
            template_seq = sequences.get(template_codes[0]) if template_codes else None

            if target_seq and template_seq:
                aligned_len = 0
                identical = 0
                for t, s in zip(template_seq, target_seq):
                    if t != '-' and s != '-':
                        aligned_len += 1
                        if t == s:
                            identical += 1

                if aligned_len > 0:
                    seq_identity = (identical / aligned_len) * 100

                target_len = len(target_seq.replace('-', ''))
                if target_len > 0:
                    coverage = (aligned_len / target_len) * 100

    except Exception as e:
        logging.warning(f"Could not parse alignment file for identity and coverage: {e}")

    return seq_identity, coverage


def generate_modeller_report(job_name, sequence, modeller_results, results_dir):
    """Generate a human-readable text report summarizing Modeller results."""
    report = []
    now = datetime.now()

    modeller_version = "Not found"
    dope_z_scores = {}
    try:
        with open(modeller_results['log_file'], 'r') as f:
            log_content = f.read()
            version_match = re.search(r"^Modeller (\S+)", log_content, re.MULTILINE)
            if version_match:
                modeller_version = version_match.group(1)
            for match in re.finditer(r"(\S+\.pdb)\s+DOPE Z-score:\s+(-?\d+\.\d+)", log_content):
                dope_z_scores[match.group(1)] = float(match.group(2))
    except Exception as e:
        logging.warning(f"Could not parse modeller log file: {e}")

    seq_identity, coverage = parse_alignment_file(
        modeller_results['alignment_file'],
        job_name,
        modeller_results['templates']
    )

    # --- 1. Header ---
    report.append("1. Report Header")
    report.append("----------------")
    report.append(f"Project/Run ID: {job_name}")
    report.append(f"Date & Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Modeller Version: {modeller_version}")
    report.append(f"Script name: {os.path.basename(__file__)}\n")

    # --- 2. Target Info ---
    report.append("2. Target Information")
    report.append("---------------------")
    report.append(f"Target Sequence ID / Name: {job_name}")
    report.append(f"Sequence Length: {len(sequence)}")
    report.append("FASTA sequence:")
    for i in range(0, len(sequence), 80):
        report.append(sequence[i:i+80])
    report.append("\n")

    # --- 3. Template Info ---
    report.append("3. Template Information")
    report.append("-----------------------")
    if modeller_results.get("templates"):
        report.append(f"Template PDB ID(s) + chain(s): {', '.join(modeller_results['templates'])}")
    else:
        report.append("Template PDB ID(s) + chain(s): Not available")
    report.append(f"Sequence identity (%): {seq_identity:.2f}")
    report.append(f"Alignment coverage (%): {coverage:.2f}")
    report.append("\nAlignment snapshot (from .ali file):")
    try:
        with open(modeller_results['alignment_file'], 'r') as f:
            report.append(f.read())
    except Exception as e:
        report.append(f"Could not read alignment file: {e}")
    report.append("\n")

    # --- 4. Model Summary ---
    report.append("4. Model Generation Summary")
    report.append("---------------------------")
    models_info = modeller_results.get("models", [])
    report.append(f"Number of models generated: {len(models_info)}")
    if models_info:
        report.append("\nTable of model scores:")
        report.append("Model Name\tDOPE Score\tGA341 Score\tmolpdf\tDOPE Z-score")
        for model in models_info:
            model_name = os.path.basename(model['path'])
            z_score = dope_z_scores.get(model_name, 'N/A')
            report.append(f"{model_name}\t{model.get('dope_score', 'N/A')}\t{model.get('ga341_score', 'N/A')}\t{model.get('molpdf', 'N/A')}\t{z_score}")
    report.append("\n")

    # --- 5. Best Model ---
    report.append("5. Best Model(s)")
    report.append("----------------")
    best_model = min(models_info, key=lambda x: x.get('dope_score', float('inf'))) if models_info else None
    if best_model:
        best_model_name = os.path.basename(best_model['path'])
        best_z_score = dope_z_scores.get(best_model_name, 'N/A')
        report.append(f"Best model name: {best_model_name}")
        report.append(f"Summary of scores: DOPE={best_model.get('dope_score', 'N/A')}, "
                      f"GA341={best_model.get('ga341_score', 'N/A')}, "
                      f"molpdf={best_model.get('molpdf', 'N/A')}, DOPE Z-score={best_z_score}")
        report.append(f"File path to final PDB model: {best_model['path']}")
    else:
        report.append("No best model found.")
    report.append("\n")

    # --- 6. Visualization Outputs ---
    report.append("6. Visualization Outputs")
    report.append("------------------------")
    report.append("Per-residue DOPE profile plot: Not generated by this script.")
    report.append("Superposition snapshot: Not generated by this script.\n")

    # --- 7. Output File Index ---
    report.append("7. Output File Index")
    report.append("--------------------")
    report.append("*.pdb -> Predicted structure(s)")
    report.append(".ali / .pir -> Alignment files")
    report.append(".log -> Modeller log file")
    report.append("report.txt -> This report\n")

    # --- 8. Final Summary ---
    report.append("8. Final Summary (Digest)")
    report.append("-------------------------")
    report.append(f"Target: [{job_name}, {len(sequence)}]")
    if modeller_results.get("templates"):
        report.append(f"Template(s): [{', '.join(modeller_results['templates'])}, {seq_identity:.2f}, {coverage:.2f}]")
    else:
        report.append("Template(s): [Not available, Not implemented, Not implemented]")
    report.append(f"Models Generated: {len(models_info)}")
    if best_model:
        best_model_name = os.path.basename(best_model['path'])
        best_z_score = dope_z_scores.get(best_model_name, 'N/A')
        report.append(f"Best Model: {best_model_name}")
        report.append(f"DOPE Score: {best_model.get('dope_score', 'N/A')}")
        report.append(f"GA341: {best_model.get('ga341_score', 'N/A')}")
        report.append(f"DOPE Z-score: {best_z_score}")
        report.append(f"File Path: {best_model['path']}")
    report.append("\n")

    # Write report
    report_path = os.path.join(results_dir, f"{job_name}_report.txt")
    with open(report_path, 'w') as f:
        f.write("\n".join(report))
    logging.info(f"Generated report at: {report_path}")


def main():
    logging.info("Starting Modeller Homology Modeling demonstration...")

    parser = argparse.ArgumentParser(description="Run Modeller homology modeling.")
    parser.add_argument("--sequence", required=True, help="Amino acid sequence for modeling.")
    parser.add_argument("--job_name", required=True, help="Name for the Modeller job.")
    parser.add_argument("--num_models", type=int, default=5, help="Number of models to generate (default: 5).")
    parser.add_argument("--evalue_cutoff", type=float, default=0.001, help="E-value cutoff for template selection (default: 0.001).")
    parser.add_argument("--templates", nargs="+", help="Optional: specify template PDB IDs + chains, e.g., 1crnA 2plvB.")
    parser.add_argument("--no-validation", action="store_true", help="Disable model validation after generation.")
    parser.add_argument("--results_dir", type=str, help="Optional: specify output directory for Modeller results.")
    args = parser.parse_args()

    sequence = args.sequence
    job_name = args.job_name
    num_models = args.num_models
    evalue_cutoff = args.evalue_cutoff

    # --- Results Directory Configuration ---
    if args.results_dir:
        current_modeller_results_dir = args.results_dir
    else:
        BASE_RESULTS_DIR = "results"
        current_modeller_results_dir = os.path.join(BASE_RESULTS_DIR, "model_generated", "modeller")
    os.makedirs(current_modeller_results_dir, exist_ok=True)
    # --- End Modeller Configuration ---

    if not MODELLER_LICENSE_KEY or MODELLER_LICENSE_KEY == "YOUR_MODELLER_LICENSE_KEY_HERE":
        logging.error("Modeller license key is not set. Please update MODELLER_LICENSE_KEY in this script.")
        return

    if not os.path.exists(MODELLER_PATH):
        logging.error(f"Modeller installation path not found: {MODELLER_PATH}")
        return

    if not os.path.exists(PDB_DB_PATH):
        logging.error(f"Modeller PDB database not found: {PDB_DB_PATH}. Please ensure it's downloaded and placed correctly.")
        return

    logging.info(f"Running Modeller for homologous modeling for target: {job_name}...")
    logging.info(f"  Sequence: {sequence[:50]}... (length: {len(sequence)})")
    logging.info(f"  Number of models: {num_models}")
    logging.info(f"  E-value cutoff: {evalue_cutoff}")

    modeller_results = run_modeller_homology_modeling(
        target_sequence=sequence,
        job_name=job_name,
        modeller_path=MODELLER_PATH,
        pdb_db_path=PDB_DB_PATH,
        results_dir=current_modeller_results_dir,
        license_key=MODELLER_LICENSE_KEY,
        num_models=num_models,
        evalue_cutoff=evalue_cutoff,
        templates=args.templates,  # NEW: allow user to pass templates
    )

    if modeller_results and modeller_results["models"]:
        modeller_generated_models_info = modeller_results["models"]
        logging.info(f"Modeller successfully generated {len(modeller_generated_models_info)} models.")
        best_model = None

        for model_info in modeller_generated_models_info:
            model_path = model_info["path"]
            dope_score = model_info.get("dope_score")
            ga341_score = model_info.get("ga341_score")

            logging.info(f"  - Model: {os.path.basename(model_path)}")
            if dope_score is not None:
                logging.info(f"    DOPE score: {dope_score:.3f}")
            if ga341_score is not None:
                logging.info(f"    GA341 score: {ga341_score[0]:.3f}" if isinstance(ga341_score, (list, tuple)) else f"    GA341 score: {ga341_score}")

            if dope_score is not None:
                if best_model is None or dope_score < best_model["dope_score"]:
                    best_model = {"path": model_path, "dope_score": dope_score, "ga341_score": ga341_score}

        ...
        if best_model:
            logging.info("\n--- Best Model Summary ---")
            logging.info(f"Path: {os.path.basename(best_model['path'])}")
            logging.info(f"DOPE score: {best_model['dope_score']:.3f}")
            if best_model["ga341_score"] is not None:
                score = best_model["ga341_score"]
                logging.info(f"GA341 score: {score[0]:.3f}" if isinstance(score, (list, tuple)) else f"GA341 score: {score}")
            logging.info("--------------------------")

        generate_modeller_report(job_name, sequence, modeller_results, current_modeller_results_dir)

        # --- JSON Output for Streamlit App ---
        results_for_streamlit = {
            "models": modeller_results.get("models", []),
            "templates": modeller_results.get("templates", []),
        }
        print("###MODELLER_JSON_START###")
        import json
        print(json.dumps(results_for_streamlit, indent=2))
        print("###MODELLER_JSON_END###")

    else:
        logging.warning("Modeller did not generate any models. Check logs for errors.")


if __name__ == "__main__":
    main()
