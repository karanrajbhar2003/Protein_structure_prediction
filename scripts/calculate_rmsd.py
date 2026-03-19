import sys
from modeller import *

# --- Get the PDB file paths from the command line ---
if len(sys.argv) != 3:
    print("Usage: python calculate_rmsd.py <pdb_file_1> <pdb_file_2>")
    sys.exit(1)

pdb_file_1 = sys.argv[1]
pdb_file_2 = sys.argv[2]

# --- Initialize MODELLER environment ---
env = Environ()
log.verbose()

# --- Read the two structures ---
mdl = Model(env, file=pdb_file_1)
ref = Model(env, file=pdb_file_2)

# --- Select all atoms for superposition ---
selection = Selection(mdl.atoms)

# --- Create an alignment object ---
aln = Alignment(env)
aln.append_model(mdl, align_codes="model")
aln.append_model(ref, align_codes="reference")

# --- Align the sequences ---
aln.align()

# --- Superpose the structures ---
# Use the selection to superpose
rmsd_val = selection.superpose(ref, aln)

# --- Print the RMSD ---
print(f"RMSD between {pdb_file_1} and {pdb_file_2}: {rmsd_val.rms:.3f} Å")
