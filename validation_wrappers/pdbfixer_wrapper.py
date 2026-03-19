#!/usr/bin/env python3
"""
PDBFixer wrapper.

Usage:
    python validation_wrappers/pdbfixer_wrapper.py --pdb_file path/to/model.pdb --output_dir results/model1/pdbfixer --ph 7.0

What it does:
 - Runs PDBFixer to detect/fix missing residues & atoms
 - Adds missing hydrogens (at pH)
 - Writes a fixed PDB to output_dir/<input_stem>_fixed.pdb
 - Writes a JSON summary: output_dir/pdbfixer_summary.json
 - Returns exit code 0 on success, non-zero on fatal errors
"""
import argparse
import os
import json
import sys
import logging
import shutil

# Try modern imports for PDBFile
try:
    from openmm.app import PDBFile  # preferred if openmm is installed
except Exception:
    try:
        from simtk.openmm.app import PDBFile  # fallback older naming
    except Exception:
        PDBFile = None

# PDBFixer import
try:
    from pdbfixer import PDBFixer
except Exception:
    PDBFixer = None

def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def run_pdbfixer(pdb_file, output_dir, ph=7.0, write_pqr=False):
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='[pdbfixer] %(message)s')
    log = logging.getLogger('pdbfixer_wrapper')

    if PDBFixer is None or PDBFile is None:
        log.error("Required packages missing: pdbfixer and/or openmm. See README for install instructions.")
        return 2

    if not os.path.isfile(pdb_file):
        log.error(f"PDB file not found: {pdb_file}")
        return 3

    pdb_stem = os.path.splitext(os.path.basename(pdb_file))[0]
    fixed_path = os.path.join(output_dir, f"{pdb_stem}_fixed.pdb")
    
    summary = {
        "input_pdb": os.path.abspath(pdb_file),
        "fixed_pdb": None,
        "missing_residues_found": False,
        "missing_residues_count": 0,
        "missing_atoms_found": 0,
        "added_hydrogens": False,
        "warnings": [],
        "status": "skipped"
    }

    if "_fixed" in pdb_stem:
        log.info("PDB file appears to be already fixed. Skipping.")
        ensure_dir(output_dir)
        # copy the file to the output directory for consistency
        shutil.copy(pdb_file, fixed_path)
        summary["fixed_pdb"] = os.path.abspath(fixed_path)
        summary["status"] = "skipped"
        with open(os.path.join(output_dir, "pdbfixer_summary.json"), 'w') as fh:
            json.dump(summary, fh, indent=2)
        return 0
        
    ensure_dir(output_dir)
    try:
        log.info(f"Loading PDB: {pdb_file}")
        fixer = PDBFixer(filename=pdb_file)
    except Exception as e:
        log.exception("Failed to load PDB with PDBFixer:")
        return 4

    fixer.findMissingResidues()
    summary["missing_residues_found"]= bool(fixer.missingResidues)
    summary["missing_residues_count"]= len(fixer.missingResidues) if fixer.missingResidues is not None else 0
    summary["status"] = "processed"
    

    try:
        # Inspect what we will do
        try:
            mr = fixer.missingResidues
            summary["missing_residues_found"] = bool(mr)
            # missingResidues is a dict keyed by chain id - count residues
            if mr:
                count = 0
                for chain, residues in mr.items():
                    # residues is dict mapping resnum -&gt; (not sure) ; do a best-effort count
                    if isinstance(residues, dict):
                        count += len(residues)
                summary["missing_residues_count"] = count
        except Exception:
            # ignore introspection errors
            pass

        # findMissingAtoms() populates fixer.missingAtoms
        log.info("Detecting missing atoms...")
        fixer.findMissingAtoms()
        ma = fixer.missingAtoms
        # missingAtoms structure: dict keyed by (chain, index) -&gt; list of atom names; best-effort size measure
        missing_atoms_count = 0
        if ma:
            try:
                for k, v in ma.items():
                    missing_atoms_count += len(v) if v else 0
            except Exception:
                missing_atoms_count = -1
        summary["missing_atoms_found"] = missing_atoms_count

        # Try to find missing residues (this may be empty)
        log.info("Detecting missing residues...")
        try:
            fixer.findMissingResidues()
        except Exception:
            log.info("findMissingResidues() not available or failed; continuing.")

        # Add missing atoms where possible
        log.info("Adding missing atoms where possible...")
        try:
            fixer.addMissingAtoms()
        except Exception as e:
            log.warning(f"addMissingAtoms() raised: {e}")
            summary["warnings"].append(f"addMissingAtoms_error: {str(e)}")

        # Add hydrogens (pH adjustable)
        log.info(f"Adding missing hydrogens (pH={ph})...")
        try:
            fixer.addMissingHydrogens(pH=ph)
            summary["added_hydrogens"] = True
        except Exception as e:
            log.warning(f"addMissingHydrogens() raised: {e}")
            summary["added_hydrogens"] = False
            summary["warnings"].append(f"addMissingHydrogens_error: {str(e)}")

        # Write fixed PDB
        pdb_stem = os.path.splitext(os.path.basename(pdb_file))[0]
        fixed_path = os.path.join(output_dir, f"{pdb_stem}_fixed.pdb")
        log.info(f"Writing fixed PDB to: {fixed_path}")
        with open(fixed_path, 'w') as out_fh:
            PDBFile.writeFile(fixer.topology, fixer.positions, out_fh)
        summary["fixed_pdb"] = os.path.abspath(fixed_path)

        # Optionally write PQR or other formats if desired (not done here)
    except Exception as e:
        log.exception("Fatal error while running PDBFixer:")
        summary["error"] = str(e)
        # write partial summary for debugging
        with open(os.path.join(output_dir, "pdbfixer_summary.json"), 'w') as fh:
            json.dump(summary, fh, indent=2)
        return 10

    # Save summary JSON
    summary_path = os.path.join(output_dir, "pdbfixer_summary.json")
    with open(summary_path, 'w') as fh:
        json.dump(summary, fh, indent=2)

    log.info("PDBFixer completed successfully.")
    return 0

def parse_args():
    parser = argparse.ArgumentParser(description="PDBFixer wrapper")
    parser.add_argument('--pdb_file', required=True, help="Input PDB file")
    parser.add_argument('--output_dir', required=True, help="Directory to write outputs (fixed PDB + summary.json)")
    parser.add_argument('--ph', type=float, default=7.0, help="pH value used when adding hydrogens (default 7.0)")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    rc = run_pdbfixer(args.pdb_file, args.output_dir, ph=args.ph)
    sys.exit(rc)
