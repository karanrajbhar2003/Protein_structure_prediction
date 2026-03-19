
import argparse
import sys
from pathlib import Path
import shutil
import time

# Add src directory to Python path to allow importing validation_utils
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "src"))

import validation_utils

# Define the order and script paths for all available validators
ALL_VALIDATORS = {
    "dssp": ROOT / "validation_wrappers/dssp_wrapper.py",
    "freesasa": ROOT / "validation_wrappers/freesasa_wrapper.py",
    "molprobity": ROOT / "validation_wrappers/molprobity_wrapper.py",
    "prosa": ROOT / "validation_wrappers/prosa_wrapper.py",
    "voromqa": ROOT / "validation_wrappers/voromqa_wrapper.py",
    "qmean": ROOT / "validation_wrappers/qmean_wrapper.py",
    "modeller": ROOT / "validation_wrappers/modeller_wrapper.py",
}

def main():
    parser = argparse.ArgumentParser(description="Run a validation pipeline on a PDB file.")
    parser.add_argument("pdb_file", help="Path to the input PDB file.")
    parser.add_argument("--project_name", default="cli_validation_project", help="Name of the project for organizing results.")
    parser.add_argument("--job_name", help="Optional job name. If not provided, one will be generated from the PDB file name and timestamp.")
    parser.add_argument("--validators", help=f"Comma-separated list of validators to run. Defaults to all. Available: {','.join(ALL_VALIDATORS.keys())}")
    
    # --- Arguments for specific tools ---
    parser.add_argument("--voromqa_path", help="Path to the VoroMQA executable.")
    parser.add_argument("--email", help="Email for QMEAN API.")
    parser.add_argument("--token", help="SWISS-MODEL API token for QMEAN.")

    args = parser.parse_args()

    pdb_file_initial = Path(args.pdb_file)
    if not pdb_file_initial.exists():
        print(f"Error: PDB file not found at {pdb_file_initial}")
        sys.exit(1)

    # --- Determine which validators to run ---
    validators_to_run = []
    if args.validators:
        for v_name in args.validators.split(','):
            v_name = v_name.strip().lower()
            if v_name in ALL_VALIDATORS:
                validators_to_run.append((v_name, ALL_VALIDATORS[v_name]))
            else:
                print(f"Warning: Unknown validator '{v_name}' skipped.")
    else:
        validators_to_run = list(ALL_VALIDATORS.items())

    # --- Set up directory structure ---
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    job_name = args.job_name or f"{pdb_file_initial.stem}_{timestamp}"
    
    results_dir = ROOT / "results" / args.project_name / job_name
    if results_dir.exists():
        print(f"Warning: Results directory {results_dir} already exists. Overwriting.")
        shutil.rmtree(results_dir)
    
    input_dir = results_dir / "input"
    fixed_dir = results_dir / "fixed"
    validation_dir = results_dir / "validation"
    
    for d in [input_dir, fixed_dir, validation_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print(f"Results will be saved in: {results_dir}")

    # Copy original PDB to 'input' directory
    shutil.copy(pdb_file_initial, input_dir / "original.pdb")
    pdb_for_processing = input_dir / "original.pdb"

    # --- 1. Run PDBFixer as a mandatory first step ---
    print("\n--- Running PDBFixer ---")
    fixed_pdb_path = validation_utils.run_pdbfixer(pdb_for_processing, validation_dir)
    
    pdb_for_validation = None
    if fixed_pdb_path:
        print(f"PDBFixer completed. Using fixed PDB: {fixed_pdb_path}")
        # Copy to 'fixed' dir for consistency
        shutil.copy(fixed_pdb_path, fixed_dir / "fixed.pdb")
        pdb_for_validation = fixed_dir / "fixed.pdb"
    else:
        print("PDBFixer failed or did not produce an output. Using original PDB for validation.")
        pdb_for_validation = pdb_for_processing

    # --- 2. Run selected validators on the (potentially fixed) PDB ---
    print(f"\n--- Running Validators on {pdb_for_validation.name} ---")
    for tool_name, script_path in validators_to_run:
        extra_args = []
        if tool_name == "voromqa":
            if not args.voromqa_path:
                print("Skipping VoroMQA: --voromqa_path not provided.")
                continue
            extra_args.extend(["--voromqa_path", args.voromqa_path])
        elif tool_name == "qmean":
            if not args.email or not args.token:
                print("Skipping QMEAN: --email and --token not provided.")
                continue
            extra_args.extend(["--email", args.email, "--token", args.token])

        success = validation_utils.run_validation_tool(
            tool_name=tool_name,
            script_path=script_path,
            pdb_path=pdb_for_validation,
            output_dir=validation_dir,
            extra_args=extra_args
        )
        status = "succeeded" if success else "failed"
        print(f"-> {tool_name}... {status}")

    print("\nValidation pipeline complete.")
    print(f"Find all results and logs in: {results_dir}")

if __name__ == "__main__":
    main()