import sys
import os

# Add parent directory to Python path to import main
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.main import run_validation_flow


def test_validation():
    """
    Tests the validation workflow with a dummy PDB file.
    """
    pdb_file = "e:\\Projects\\Protein_structure_prediction\\scripts\\6NXL.pdb"
    run_validation_flow(pdb_file, selected_tools=["MolProbity", "ERRAT"])


if __name__ == "__main__":
    test_validation()
