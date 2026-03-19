import os
import shutil
import subprocess
from pathlib import Path

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
PDBFIXER_WRAPPER = ROOT / "validation_wrappers" / "pdbfixer_wrapper.py"
TEMP_DIR = ROOT / "temp_test"
TEMP_DIR.mkdir(exist_ok=True)

# Create a dummy PDB file
pdb_content = """
ATOM      1  N   ALA A   1      27.340  30.360  24.530  1.00 20.00           N
ATOM      2  CA  ALA A   1      28.350  30.450  25.600  1.00 20.00           C
ATOM      3  C   ALA A   1      29.360  29.350  25.340  1.00 20.00           C
ATOM      4  O   ALA A   1      29.740  28.670  26.240  1.00 20.00           O
ATOM      5  CB  ALA A   1      28.000  31.690  26.410  1.00 20.00           C
END
"""
pdb_file = TEMP_DIR / "dummy.pdb"
pdb_file.write_text(pdb_content)

# Run the pdbfixer wrapper
output_dir = TEMP_DIR / "pdbfixer_output"
output_dir.mkdir(exist_ok=True)

cmd = [
    "python",
    str(PDBFIXER_WRAPPER),
    "--pdb_file",
    str(pdb_file),
    "--output_dir",
    str(output_dir),
]
proc = subprocess.run(cmd, capture_output=True, text=True)

# Print the output
print("--- stdout ---")
print(proc.stdout)
print("--- stderr ---")
print(proc.stderr)

# Check the output file
fixed_pdb_file = output_dir / "dummy_fixed.pdb"
if fixed_pdb_file.exists():
    print(f"--- Contents of {fixed_pdb_file} ---")
    print(fixed_pdb_file.read_text())
else:
    print(f"Error: {fixed_pdb_file} was not created.")

# Clean up
# shutil.rmtree(TEMP_DIR)
