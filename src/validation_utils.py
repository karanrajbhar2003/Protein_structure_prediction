
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# Constants
ROOT = Path(__file__).resolve().parent.parent
JSON_START = "###JSON_START###"
JSON_END = "###JSON_END###"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_embedded_json(text: str):
    """Extracts the first JSON object found between explicit markers in a string."""
    match = re.search(re.escape(JSON_START) + r"(.*?)" + re.escape(JSON_END), text, flags=re.DOTALL)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse embedded JSON: {e}\nJSON string was:\n{json_str}")
            return None
    return None

def run_subprocess(cmd, log_path, cwd=None, env=None):
    """
    Runs a subprocess and logs its stdout and stderr to a specified file.

    Returns the process's return code and the full captured output.
    """
    full_output = ""
    try:
        with open(log_path, 'w', encoding='utf-8', errors='replace') as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=cwd,
                env=env
            )
            for line in iter(process.stdout.readline, ''):
                log_file.write(line)
                full_output += line
        
        retcode = process.wait()
        return retcode, full_output
    except Exception as e:
        error_message = f"Subprocess execution failed: {e}"
        logging.error(error_message)
        if 'log_file' in locals() and not log_file.closed:
            log_file.write(error_message)
        return -1, error_message

def run_pdbfixer(pdb_path: Path, output_dir: Path):
    """
    Runs the PDBFixer wrapper.
    Returns a tuple containing the path to the fixed PDB file and the log file path.
    """
    pdbfixer_dir = output_dir / "pdbfixer"
    pdbfixer_dir.mkdir(exist_ok=True)
    log_path = pdbfixer_dir / "pdbfixer.log"
    
    script_path = ROOT / "validation_wrappers" / "pdbfixer_wrapper.py"
    cmd = [
        "python", str(script_path),
        "--pdb_file", str(pdb_path),
        "--output_dir", str(pdbfixer_dir)
    ]
    
    logging.info(f"Running PDBFixer: {' '.join(cmd)}")
    retcode, _ = run_subprocess(cmd, log_path)
    
    if retcode == 0:
        fixed_pdb = pdbfixer_dir / f"{pdb_path.stem}_fixed.pdb"
        if fixed_pdb.exists():
            logging.info(f"PDBFixer created {fixed_pdb}")
            return fixed_pdb, log_path
        else:
            logging.warning(f"PDBFixer ran but output file not found at {fixed_pdb}")
            return None, log_path
    else:
        logging.error(f"PDBFixer failed with return code {retcode}. Check log at {log_path}")
        return None, log_path

def run_validation_tool(tool_name: str, script_path: Path, pdb_path: Path, output_dir: Path, extra_args=None):
    """
    Runs a single validation tool wrapper.
    Returns a tuple containing a success boolean and the path to the log file.
    """
    tool_dir = output_dir / tool_name
    tool_dir.mkdir(exist_ok=True)
    log_path = tool_dir / f"{tool_name}.log"
    
    cmd = [
        "python", str(script_path),
        "--pdb_file", str(pdb_path),
        "--output_dir", str(tool_dir)
    ]
    if extra_args:
        cmd.extend(extra_args)
        
    logging.info(f"Running {tool_name}: {' '.join(cmd)}")
    retcode, _ = run_subprocess(cmd, log_path)
    
    if retcode == 0:
        logging.info(f"{tool_name} completed successfully.")
        return True, log_path
    else:
        logging.error(f"{tool_name} failed with return code {retcode}. Check log at {log_path}")
        return False, log_path
