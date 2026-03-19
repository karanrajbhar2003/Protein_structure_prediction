"""
modeller_utils.py — Clean, final working version
Loads local Modeller installation and runs homology modelling.
"""

import sys
import os
import shutil
import urllib.request
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# -----------------------------------------------------------
# 1) Automatic Modeller Path Loader (Windows-compatible)
# -----------------------------------------------------------

# Default install location (your folder!)
DEFAULT_MODELLER_DIR = Path(r"E:\Projects\Protein_structure_prediction\Modeller10.7")


def configure_modeller(modeller_dir: Path = DEFAULT_MODELLER_DIR):
    """Ensure Modeller is importable by fixing sys.path and PATH."""
    modeller_dir = Path(modeller_dir)

    modlib = modeller_dir / "modlib"
    bin_dir = modeller_dir / "bin"
    lib_dir = modeller_dir / "lib"

    if not modlib.exists():
        logger.error(f"Modeller modlib directory not found: {modlib}")
        return False

    # Set MODELLER_PATH environment variable
    os.environ["MODELLER_PATH"] = str(modeller_dir)
    logger.debug(f"MODELLER_PATH set to {os.environ['MODELLER_PATH']}")

    # 1. Add modlib to sys.path
    if str(modlib) not in sys.path:
        sys.path.insert(0, str(modlib))

    # 2. Add directories to PATH for DLL loading
    for d in [bin_dir, lib_dir]:
        if d.exists() and str(d) not in os.environ["PATH"]:
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]

    # 3. License key
    os.environ["KEY_MODELLER"] = "MODELIRANJE"

    # 4. Test import
    try:
        import modeller  # noqa
        from modeller.automodel import AutoModel  # noqa
        logger.info("Modeller successfully loaded.")
        return True
    except Exception as e:
        logger.error(f"Modeller import failed: {e}")
        return False


# Initialize Modeller immediately
if not configure_modeller():
    raise RuntimeError("❌ Modeller could not be loaded. Check installation path.")


# Now that Modeller is loaded, do proper imports
from modeller import Environ, Model, Alignment
from modeller.automodel import assess, AutoModel

# Custom class to report progress
class ProgressAutoModel(AutoModel):
    def assess_dope(self, model):
        # This method is called for each model, making it a good hook for progress.
        # The 'model' argument is a standard Python object with model info.
        # We can figure out the current model number from its filename (e.g., jobname.B99990001.pdb)
        try:
            model_num = int(model['name'].split('.')[-2][-4:])
            progress = ((model_num) / self.ending_model) * 100
            print(f"###MODELLER_PROGRESS### {progress:.0f}% ({model_num}/{self.ending_model})")
        except:
            # Fallback if parsing fails
            print("###MODELLER_PROGRESS### intermediate")
        
        return super().assess_dope(model)


# -----------------------------------------------------------
# 2) Utilities
# -----------------------------------------------------------

def download_pdb(pdb_id, output_dir):
    """Downloads a PDB file from RCSB."""
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    pdb_file = os.path.join(output_dir, f"{pdb_id}.pdb")

    try:
        logger.info(f"Downloading template {pdb_id}...")
        urllib.request.urlretrieve(url, pdb_file)
        return pdb_file
    except Exception as e:
        logger.error(f"Failed to download {pdb_id}: {e}")
        return None


def get_chain_range(pdb_file: str, chain_id: str):
    """Extract first & last residue indices for a template chain."""
    first, last = None, None
    with open(pdb_file) as f:
        for line in f:
            if line.startswith("ATOM") and line[21] == chain_id:
                resnum = line[22:26].strip()
                if first is None:
                    first = resnum
                last = resnum

    if first is None or last is None:
        raise ValueError(f"Chain {chain_id} not found in {pdb_file}")

    return first, last


# -----------------------------------------------------------
# 3) Core Homology Modelling Function
# -----------------------------------------------------------

def run_modeller_homology_modeling(
    target_sequence: str,
    job_name: str,
    modeller_path: str,
    pdb_db_path: str,
    results_dir: str,
    license_key: str,
    num_models: int = 5,
    evalue_cutoff: float = 0.001,
    templates: list[str] | None = None,
    assess_methods: tuple = (assess.DOPE, assess.GA341),
):
    """Run Modeller homology modeling with provided sequence + templates."""

    env = Environ()
    env.io.atom_files_directory = [
        ".",
        os.path.join(modeller_path, "atom_files"),
    ]

    env.io.hetatm = True
    env.io.water = True

    # Official topology & parameter files
    env.libs.topology.read(file="$(LIB)/top_heav.lib")
    env.libs.parameters.read(file="$(LIB)/par.lib")

    # Default template
    if not templates:
        templates = ["1l65A"]

    # --- Directory and Path Handling ---
    # We will run Modeller directly in the results_dir.
    # It's critical to wrap chdir in a try/finally to ensure we always return.
    original_cwd = os.getcwd()
    os.makedirs(results_dir, exist_ok=True)
    
    model_outputs = []
    final_alignment_path = ""
    final_log_path = os.path.join(results_dir, f"{job_name}_modeller.log")

    try:
        os.chdir(results_dir)

        # Write PIR sequence file
        pir_file = f"{job_name}.pir"
        with open(pir_file, "w") as f:
            f.write(f">P1;{job_name}\n")
            f.write(f"sequence:{job_name}:::::::0.00:0.00\n")
            f.write(f"{target_sequence}*\n")

        aln = Alignment(env)
        aln.append(file=pir_file, align_codes=job_name)

        # Process templates
        for template in templates:
            pdb_id, chain_id = template[:4], template[4]
            # Download PDBs into the results dir
            pdb_path = download_pdb(pdb_id, results_dir)
            if not pdb_path:
                logger.warning(f"Skipping missing template {template}.")
                continue

            try:
                first, last = get_chain_range(pdb_path, chain_id)
                mdl = Model(
                    env,
                    file=pdb_id,
                    model_segment=(f"{first}:{chain_id}", f"{last}:{chain_id}"),
                )
                aln.append_model(mdl, align_codes=template, atom_files=f"{pdb_id}.pdb")

            except Exception as e:
                logger.error(f"Template {template} failed: {e}")
                continue

        # Align
        aln_file = f"{job_name}-ali.pir"
        pap_file = f"{job_name}-ali.pap"
        aln.write(file=aln_file, alignment_format="PIR")
        aln.write(file=pap_file, alignment_format="PAP")
        final_alignment_path = os.path.join(results_dir, pap_file) # Store absolute path

        # Build models
        a = ProgressAutoModel(
            env,
            alnfile=aln_file,
            knowns=templates,
            sequence=job_name,
            assess_methods=assess_methods,
        )

        a.starting_model = 1
        a.ending_model = num_models
        print("###MODELLER_PROGRESS### START")
        a.make()
        print("###MODELLER_PROGRESS### END")
        
        # Collect models - paths are now relative to results_dir
        for m in a.outputs:
            if not m.get("failure"):
                # Construct absolute path for the final result
                model_path = os.path.join(results_dir, m["name"])
                model_outputs.append({
                    "path": model_path,
                    "molpdf": m.get("molpdf"),
                    "dope_score": m.get("DOPE score"),
                    "ga341_score": m.get("GA341 score"),
                })
            else:
                logger.warning(f"Model failed: {m['name']}")
        
        # Rename the log file
        if os.path.exists("modeller.log"):
            shutil.move("modeller.log", final_log_path)

    finally:
        os.chdir(original_cwd) # Always change back to original directory


    return {
        "models": model_outputs,
        "alignment_file": final_alignment_path,
        "log_file": final_log_path,
        "templates": templates,
    }
