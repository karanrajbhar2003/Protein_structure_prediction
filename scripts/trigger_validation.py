import requests
import json
from pathlib import Path

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = ROOT / "electron-app" / "results"
PROJECT_NAME = "my_protein_project"
project_dir = PROJECTS_ROOT / PROJECT_NAME
modeller_models_dir = project_dir / "models" / "modeller"
modeller_models_dir.mkdir(parents=True, exist_ok=True)

# Create a dummy PDB file
pdb_content = """
ATOM      1  N   ALA A   1      27.340  30.360  24.530  1.00 20.00           N
ATOM      2  CA  ALA A   1      28.350  30.450  25.600  1.00 20.00           C
ATOM      3  C   ALA A   1      29.360  29.350  25.340  1.00 20.00           C
ATOM      4  O   ALA A   1      29.740  28.670  26.240  1.00 20.00           O
ATOM      5  CB  ALA A   1      28.000  31.690  26.410  1.00 20.00           C
END
"""
pdb_file = modeller_models_dir / "dummy.pdb"
pdb_file.write_text(pdb_content)

# Prepare the validation request
validation_request = {
    "pdb_model_names": ["dummy.pdb"],
    "project_name": PROJECT_NAME,
    "validators": {
        "pdbfixer": True,
        "freesasa": True
    }
}

# Make the API call
url = "http://127.0.0.1:8091/api/run-validation"
try:
    response = requests.post(url, json=validation_request)
    print(response.text)
except requests.exceptions.ConnectionError as e:
    print(f"Connection failed: {e}")
    print("Please make sure the api_server.py is running.")

