import sys
import os

# Add Modeller's python library path to sys.path
modeller_install_dir = r"e:\Projects\Protein structure prediction\Modeller10.7"
modeller_modlib_path = os.path.join(modeller_install_dir, "modlib")
if modeller_modlib_path not in sys.path:
    sys.path.insert(0, modeller_modlib_path)

from modeller import *

env = Environ()

# Set Modeller license key
env.license = "MODELIRANJE"

sdb = SequenceDB(env)
try:
    sdb.read(
        seq_database_file="e:/Projects/Protein structure prediction/Modeller10.7/pdb_95.pir.gz",
        seq_database_format="PIR",
        chains_list="ALL",
        minmax_db_seq_len=(30, 4000),
        clean_sequences=True,
    )
    print("Successfully read sequence database.")
except Exception as e:
    print(f"Error reading sequence database: {e}")
