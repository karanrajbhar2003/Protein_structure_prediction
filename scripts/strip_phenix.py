import os
import shutil
import subprocess
import logging

# --- Configuration ---
PHENIX_PATH = "/home/mahesh/phenix/phenix-1.21.2-5419"
BACKUP_DIR = os.path.expanduser("~/phenix_unused")
LOG_FILE = "strip_log.txt"

# Core modules required for MolProbity to function
ESSENTIAL_MODULES = [
    "molprobity",
    "reduce",
    "probe",
    "dangle",
    "cctbx_project",
    "phenix_regression",
    "phenix",
    "iotbx",
    "libtbx",
    "mmtbx",
    "scitbx",
]

# Modules known to be required from error traces
KNOWN_REQUIRED = ["phaser", "chem_data", "amber_adaptbx"]

# --- Dummy PDB for Testing ---
DUMMY_PDB_CONTENT = """\
ATOM      1  N   ALA A   1      27.340  30.210  24.330  1.00  0.00           N
ATOM      2  CA  ALA A   1      28.160  29.040  24.690  1.00  0.00           C
ATOM      3  C   ALA A   1      27.460  28.010  25.580  1.00  0.00           C
ATOM      4  O   ALA A   1      26.250  28.040  25.830  1.00  0.00           O
ATOM      5  CB  ALA A   1      29.590  29.430  24.220  1.00  0.00           C
"""


def setup_logging():
    """Sets up logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )


def create_dummy_pdb():
    """Creates a dummy PDB file for testing."""
    with open("test.pdb", "w") as f:
        f.write(DUMMY_PDB_CONTENT)
    logging.info("Created dummy PDB file: test.pdb")


def move_and_log(src, dst):
    """Moves a directory and logs the action."""
    try:
        if os.path.exists(dst):
            shutil.rmtree(dst)  # Remove if already exists
        shutil.move(src, dst)
        logging.info(f"Moved: {src} -> {dst}")
    except Exception as e:
        logging.error(f"Failed to move {src}: {e}")


def strip_phenix():
    """Moves non-essential Phenix modules to a backup directory."""
    logging.info("--- Starting Phenix Stripping ---")
    modules_path = os.path.join(PHENIX_PATH, "modules")
    if not os.path.exists(modules_path):
        logging.error(f"Phenix modules path not found: {modules_path}")
        return False

    os.makedirs(BACKUP_DIR, exist_ok=True)
    logging.info(f"Backup directory: {BACKUP_DIR}")

    keep = set(ESSENTIAL_MODULES + KNOWN_REQUIRED)

    for module_name in os.listdir(modules_path):
        if module_name not in keep:
            src_path = os.path.join(modules_path, module_name)
            dst_path = os.path.join(BACKUP_DIR, module_name)
            if os.path.exists(src_path):
                move_and_log(src_path, dst_path)

    logging.info("--- Stripping Complete ---")
    return True


def run_test():
    """Runs a test command to verify MolProbity functionality."""
    logging.info("--- Running MolProbity Test ---")
    create_dummy_pdb()

    command = os.path.join(PHENIX_PATH, "build", "bin", "phenix.molprobity")
    try:
        result = subprocess.run(
            [command, "test.pdb"], check=True, capture_output=True, text=True
        )
        logging.info("MolProbity test executed successfully.")
        logging.info("stdout:\n" + result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logging.error("MolProbity test failed!")
        logging.error("stdout:\n" + e.stdout)
        logging.error("stderr:\n" + e.stderr)
        return False
    except FileNotFoundError:
        logging.error(f"MolProbity command not found: {command}")
        return False


def restore_phenix():
    """Restores all Phenix modules from the backup directory."""
    logging.info("--- Starting Phenix Restoration ---")
    modules_path = os.path.join(PHENIX_PATH, "modules")
    if not os.path.exists(BACKUP_DIR):
        logging.warning("Backup directory not found. Nothing to restore.")
        return

    for module_name in os.listdir(BACKUP_DIR):
        src_path = os.path.join(BACKUP_DIR, module_name)
        dst_path = os.path.join(modules_path, module_name)
        if os.path.exists(src_path):
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            move_and_log(src_path, dst_path)

    logging.info("--- Phenix Restoration Complete ---")


def main():
    """Main function to orchestrate the stripping and testing process."""
    setup_logging()

    if not strip_phenix():
        print("❌ Stripping failed.")
        return

    if run_test():
        print("\n✅ Phenix successfully stripped down to MolProbity-only mode.")
        print("You can safely delete the backup directory if not needed:")
        print(f"   rm -rf {BACKUP_DIR}")
    else:
        print("\n⚠️ MolProbity test failed.")
        print("Some extra modules may still be required.")
        print(f"Check logs in {LOG_FILE} for missing dependencies.")
        print("If you want to restore Phenix fully, run this script with:")
        print("   restore_phenix()")


if __name__ == "__main__":
    main()
