import subprocess
import os
import json
import platform


def run_molprobity(pdb_file, output_dir="results/molprobity"):
    """
    Run MolProbity (via Phenix) on a PDB file and return results as JSON.
    Handles running from Windows by automatically calling through WSL.

    Args:
        pdb_file (str): Path to PDB file.
        output_dir (str): Directory to store results.

    Returns:
        dict: Parsed MolProbity results in JSON schema.
    """

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    phenix_cmd = "phenix.molprobity"
    # Ensure the input path is absolute, as we may be changing directories
    pdb_file_abs = os.path.abspath(pdb_file)
    command = [phenix_cmd, pdb_file_abs]

    # If on Windows, prepend 'wsl' and convert path for WSL
    if platform.system() == "Windows":
        drive, tail = os.path.splitdrive(pdb_file_abs)
        # Convert E:\path\to\file -> /mnt/e/path/to/file
        wsl_path = f"/mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"

        # Construct a command to be run in a login shell inside WSL
        # This ensures .bashrc or .profile is sourced to get the PATH
        wsl_command = f'{phenix_cmd} "{wsl_path}"'
        command = ["wsl", "bash", "-l", "-c", wsl_command]

    try:
        result = subprocess.run(
            command,
            cwd=output_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,  # don't raise exceptions, we handle returncode
        )
    except FileNotFoundError:
        # This error will now trigger if 'wsl' is not found on Windows,
        # or if 'phenix.molprobity' is not in the WSL path.
        return {
            "tool": "MolProbity",
            "status": "error",
            "stderr": (
                "Could not find command. "
                "If on Windows, ensure 'wsl' is in your PATH. "
                "Ensure Phenix is in your PATH inside WSL."
            ),
        }

    stdout, stderr = result.stdout, result.stderr

    # Save raw log (both stdout and stderr)
    log_file = os.path.join(output_dir, "molprobity.log")
    with open(log_file, "w") as f:
        f.write(stdout)
        f.write("\n\n--- STDERR ---\n")
        f.write(stderr)

    # Extract metrics
    clashscore = rama_outliers = favored = rotamer_outliers = None
    for line in stdout.splitlines():
        # Use the summary section for reliable parsing
        if "Ramachandran outliers =" in line:
            try:
                rama_outliers = float(line.split()[-2])
            except (ValueError, IndexError):
                pass
        elif "favored =" in line:  # Catches the Ramachandran favored line
            try:
                favored = float(line.split()[-2])
            except (ValueError, IndexError):
                pass
        elif "Rotamer outliers" in line and "=" in line:
            try:
                rotamer_outliers = float(line.split()[-2])
            except (ValueError, IndexError):
                pass
        elif "Clashscore" in line and "=" in line:
            try:
                clashscore = float(line.split()[-1])
            except (ValueError, IndexError):
                pass

    return {
        "tool": "MolProbity",
        "status": "success" if result.returncode == 0 else "error",
        "metrics": {
            "clashscore": clashscore,
            "ramachandran_outliers": rama_outliers,
            "ramachandran_favored": favored,
            "rotamer_outliers": rotamer_outliers,
        },
        "files": {"log": log_file},
    }


if __name__ == "__main__":
    pdb_path = "test_model.pdb"  # replace with actual PDB file
    result = run_molprobity(pdb_path)
    print(json.dumps(result, indent=2))
