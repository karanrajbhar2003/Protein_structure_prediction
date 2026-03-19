#!/usr/bin/env python3
import argparse
import os
import sys
import json
import subprocess
import time
from pathlib import Path

# --- Configuration ---
# Ensure the script's directory is in the path to find other scripts
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.append(str(ROOT_DIR))

CONFIG_FILE = SCRIPT_DIR / "config.json"

def load_config():
    """Loads configuration from config.json."""
    if not CONFIG_FILE.exists():
        print(f"Warning: {CONFIG_FILE} not found. Using defaults.")
        return {{}}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def run_command(cmd, display_output=True):
    """Runs a command and optionally displays its output in real-time."""
    print(f"Running command: {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    full_output = ""
    if display_output:
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
            full_output += line
    
    process.wait()
    if process.returncode != 0:
        print(f"Error: Command returned non-zero exit code {process.returncode}")
    
    return process.returncode, full_output


def model_main(args):
    """Handler for the 'model' subcommand."""
    config = load_config()

    # --- FASTA Input ---
    if args.fasta_file:
        sequence = Path(args.fasta_file).read_text()
    elif args.sequence:
        sequence = args.sequence
    else:
        print("Error: Either --sequence or --fasta_file is required.")
        sys.exit(1)

    # --- Job Name ---
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    job_name = args.job_name or f"job_{timestamp}"

    # --- Run Modeller ---
    if args.modeller:
        print("\n--- Running Modeller ---")
        modeller_out_dir = ROOT_DIR / "results" / args.project_name / "model_generation" / "modeller" / f"{job_name}"
        modeller_out_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "python", str(SCRIPT_DIR / "run_modeller_job.py"),
            "--sequence", sequence,
            "--job_name", job_name,
            "--results_dir", str(modeller_out_dir),
            "--num_models", str(args.num_models)
        ]
        run_command(cmd)

    # --- Run Robetta ---
    if args.robetta:
        print("\n--- Running Robetta ---")
        robetta_user = config.get("robetta_username")
        robetta_pass = config.get("robetta_password")
        if not robetta_user or not robetta_pass:
            print("Error: Robetta username and password must be set in config.json")
            sys.exit(1)
        
        cmd = [
            "python", str(SCRIPT_DIR / "run_robetta_job.py"),
            "--username", robetta_user,
            "--password", robetta_pass,
            "submit",
            "--sequence", sequence,
            "--name", job_name
        ]
        run_command(cmd)

def validate_main(args):
    """Handler for the 'validate' subcommand."""
    config = load_config()
    pdb_file = Path(args.pdb_file).resolve()
    if not pdb_file.exists():
        print(f"Error: PDB file not found at {pdb_file}")
        sys.exit(1)

    # --- Create results directory ---
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    job_name = f"{pdb_file.stem}_{timestamp}"
    results_dir = ROOT_DIR / "results" / args.project_name / job_name
    
    input_dir = results_dir / "input"
    fixed_dir = results_dir / "fixed"
    validation_dir = results_dir / "validation"
    for d in [input_dir, fixed_dir, validation_dir]:
        d.mkdir(parents=True, exist_ok=True)
    
    print(f"Results will be saved in: {results_dir}")

    # --- Run PDBFixer ---
    print("\n--- Running PDBFixer ---")
    fixed_pdb = fixed_dir / f"{pdb_file.stem}_fixed.pdb"
    pdbfixer_cmd = [
        "python", str(ROOT_DIR / "validation_wrappers" / "pdbfixer_wrapper.py"),
        "--pdb_file", str(pdb_file),
        "--output_pdb", str(fixed_pdb)
    ]
    run_command(pdbfixer_cmd)

    pdb_for_validation = fixed_pdb if fixed_pdb.exists() and fixed_pdb.stat().st_size > 0 else pdb_file
    print(f"Using PDB for validation: {pdb_for_validation}")

    # --- Run selected validators ---
    for validator in args.validators:
        print(f"\n--- Running {validator} ---")
        validator_out_dir = validation_dir / validator
        validator_out_dir.mkdir(exist_ok=True)

        script_path = ROOT_DIR / "validation_wrappers" / f"{validator}_wrapper.py"
        if not script_path.exists():
            print(f"Warning: Wrapper script not found for '{validator}', skipping.")
            continue

        cmd = ["python", str(script_path), "--pdb_file", str(pdb_for_validation), "--output_dir", str(validator_out_dir)]

        # Handle special arguments
        if validator == "voromqa":
            voromqa_path = config.get("voromqa_path")
            if voromqa_path:
                cmd.extend(["--voromqa_path", voromqa_path])
            else:
                print("Warning: voromqa_path not in config.json, voromqa may fail if not in PATH.")
        
        elif validator == "qmean":
            qmean_email = config.get("qmean_email")
            qmean_token = config.get("qmean_token")
            if not qmean_email or not qmean_token:
                print("Error: QMEAN email and token must be set in config.json")
                continue
            cmd.extend(["--email", qmean_email, "--token", qmean_token])
        
        elif validator == "molprobity":
            phenix_path = config.get("phenix_path")
            if phenix_path:
                cmd.extend(["--phenix_path", phenix_path])

        run_command(cmd)
    
    print("\nValidation pipeline complete.")

def report_main(args):
    """Handler for the 'report' subcommand."""
    model_dir = Path(args.model_dir).resolve()
    if not model_dir.is_dir():
        print(f"Error: Model directory not found at {model_dir}")
        sys.exit(1)

    out_pdf = Path(args.out_pdf).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- Generating PDF Report ---")
    cmd = [
        "python", str(ROOT_DIR / "tools" / "generate_validation_pdf.py"),
        "--model_dir", str(model_dir),
        "--out_pdf", str(out_pdf)
    ]
    run_command(cmd)
    print(f"\nPDF report generated at: {out_pdf}")


def main():
    parser = argparse.ArgumentParser(description="Main CLI for the protein modeling and validation pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Modeling Sub-command ---
    p_model = subparsers.add_parser("model", help="Run protein structure modeling.")
    p_model.add_argument("--sequence", help="Amino acid sequence.")
    p_model.add_argument("--fasta-file", help="Path to a FASTA file.")
    p_model.add_argument("--job-name", help="Name for the job.")
    p_model.add_argument("--project-name", default="my_protein_project", help="Name of the project directory.")
    p_model.add_argument("--modeller", action="store_true", help="Run Modeller.")
    p_model.add_argument("--robetta", action="store_true", help="Run Robetta.")
    p_model.add_argument("--num-models", type=int, default=5, help="Number of models for Modeller to generate.")
    p_model.set_defaults(func=model_main)

    # --- Validation Sub-command ---
    p_validate = subparsers.add_parser("validate", help="Run validation on a PDB file.")
    p_validate.add_argument("--pdb-file", required=True, help="Path to the PDB file to validate.")
    p_validate.add_argument("--project-name", default="my_protein_project", help="Name of the project directory.")
    p_validate.add_argument("--validators", nargs='+', default=["dssp", "freesasa", "molprobity", "prosa", "voromqa", "qmean"],
                            help="List of validators to run.")
    p_validate.set_defaults(func=validate_main)
    
    # --- Report Sub-command ---
    p_report = subparsers.add_parser("report", help="Generate a PDF report from validation results.")
    p_report.add_argument("--model-dir", required=True, help="Directory containing the validation results.")
    p_report.add_argument("--out-pdf", required=True, help="Path to save the output PDF report.")
    p_report.set_defaults(func=report_main)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
