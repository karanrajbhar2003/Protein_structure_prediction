import os
import json
import random


def run_errat(pdb_file, output_dir="results/validation"):
    """
    Returns a dummy ERRAT result for testing purposes.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    dummy_results = {
        "tool_name": "ERRAT",
        "status": "success",
        "metrics": {"quality_score": f"{random.uniform(80, 99):.1f}"},
        "summary": "ERRAT analysis completed successfully (dummy data).",
        "metadata": {"pdb_file": os.path.basename(pdb_file), "output_dir": output_dir},
        "raw_log": "dummy_errat_log.txt",
    }

    log_file = os.path.join(output_dir, "dummy_errat_log.txt")
    with open(log_file, "w") as f:
        f.write("This is a dummy log file for ERRAT.")

    results_file = os.path.join(output_dir, "errat_results.json")
    with open(results_file, "w") as f:
        json.dump(dummy_results, f, indent=2)

    return dummy_results
