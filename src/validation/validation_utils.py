import logging
import os
import json
import sys

# Add the validation_wrappers directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'validation_wrappers')))

from molprobity_wrapper import run_molprobity_local as run_molprobity

logger = logging.getLogger(__name__)

# --- Validation Tools ---
available_tools = {
    "MolProbity": run_molprobity,
}

def run_validation_flow(pdb_file, selected_tools=None):
    """
    Runs the validation workflow.
    If selected_tools is None, it prompts the user to select tools.
    """
    logging.info(
        f"--- Starting Validation Workflow for {os.path.basename(pdb_file)} ---"
    )

    VALIDATION_RESULTS_DIR = os.path.join("results", "validation")

    if selected_tools is None:
        print("\nSelect validation tools to run:")
        tool_choices = {}
        for i, tool_name in enumerate(available_tools.keys(), 1):
            tool_choices[str(i)] = tool_name
            print(f"  {i}. {tool_name}")

        selected_indices = input(
            "Enter the numbers of the tools to run (e.g., 1 3): "
        ).split()
        selected_tools = [
            tool_choices[i] for i in selected_indices if i in tool_choices
        ]

    if not selected_tools:
        logging.warning("No valid tools selected. Skipping validation.")
        return

    merged_results = {}
    for tool_name in selected_tools:
        logging.info(f"Running {tool_name}...")
        run_tool = available_tools[tool_name]
        try:
            result = run_tool(pdb_file, VALIDATION_RESULTS_DIR)
            merged_results[tool_name] = result
        except Exception as e:
            logging.error(f"Error running {tool_name}: {e}")
            merged_results[tool_name] = {
                "tool_name": tool_name,
                "status": "error",
                "metrics": {},
                "raw_log": None,
            }

    # Save merged results
    merged_results_file = os.path.join(
        VALIDATION_RESULTS_DIR, f"{os.path.basename(pdb_file)}_validation_results.json"
    )
    with open(merged_results_file, "w") as f:
        json.dump(merged_results, f, indent=2)

    logging.info(f"Validation results saved to {merged_results_file}")
    logging.info("--- Validation Workflow Finished ---")

def validate_pdb_file(pdb_file, output_dir):
    """Validates a PDB file using a suite of validation tools."""
    logger.info(f"Running validation on {pdb_file}")

    os.makedirs(output_dir, exist_ok=True)
    molprobity_results = run_molprobity(pdb_file, output_dir)

    logger.info("Validation complete.")
    logger.info(f"MolProbity results: {molprobity_results}")

    return {
        "molprobity": molprobity_results,
    }