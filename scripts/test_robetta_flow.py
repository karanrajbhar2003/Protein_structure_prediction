import sys
import logging
import os
import re
from typing import Optional

# Add src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from robetta_client import RobettaClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def run_test():
    """
    Tests the Robetta client by downloading results from an existing job
    and submitting a new one.
    """
    # --- Configuration ---
    username = os.environ.get("ROBETTA_USERNAME", "")
    password = os.environ.get("ROBETTA_PASSWORD", "")
    if not username or not password:
        logging.error(
            "Set ROBETTA_USERNAME and ROBETTA_PASSWORD environment variables before running this script."
        )
        return

    # 1. Test downloading results from a completed job
    existing_job_id = "685931"

    # 2. Test submitting a new job
    new_job_name = "keratin"
    new_job_sequence = "MTTCSRQFTSSSSMKGSCGIGGGIGGGSSRISSVLAGGSCRAPSTYGGGLSVSSSRFSSGGACGLGGGYGGGFSSSSSSFGSGFGGGYGGGLGAGLGGGFGGGFAGGDGLLVGSEKVTMQNLNDRLASYLDKVRALEEANADLEVKIRDWYQRQRPAEIKDYSPYFKTIEDLRNKILTATVDNANVLLQIDNARLAADDFRTKYETELNLRMSVEADINGLRRVLDELTLARADLEMQIESLKEELAYLKKNHEEEMNALRGQVGGDVNVEMDAAPGVDLSRILNEMRDQYEKMAEKNRKDAEEWFFTKTEELNREVATNSELVQSGKSEISELRRTMQNLEIELQSQLSMKASLENSLEETKGRYCMQLAQIQEMIGSVEEQLAQLRCEMEQQNQEYKILLDVKTRLEQEIATYRRLLEGEDAHLSSSQFSSGSQSSRDVTSSSRQIRTKVMDVHDGKVVSTHEQVLRTKN"

    results_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "results"
    )
    os.makedirs(results_dir, exist_ok=True)

    # --- Client Initialization and Login ---
    client = RobettaClient(username, password)

    if not client.login():
        logging.error("Login failed. Exiting.")
        return

    # --- Part 1: Download results from existing job ---
    logging.info(f"--- Checking status for existing job ID: {existing_job_id} ---")
    job_info = client.get_job_status_by_id(existing_job_id)

    if job_info and job_info.get("status") == "Complete":
        logging.info(f"Job {existing_job_id} is complete. Fetching download links.")
        results_link = job_info.get("results_link")
        download_links = client.get_job_results_links(results_link)

        if download_links:
            logging.info(f"Found {len(download_links)} models to download.")
            for link in download_links:
                # Extract a clean name for the file
                model_num_match = re.search(r"model=(\d+)", link)
                job_id_match = re.search(r"id=(\d+)", link)

                file_name = f"job_{job_id_match.group(1) if job_id_match else existing_job_id}_model_{model_num_match.group(1) if model_num_match else 'unknown'}.pdb"
                save_path = os.path.join(results_dir, file_name)

                logging.info(f"Downloading model from {link} to {save_path}")
                client.download_file(link, save_path)
        else:
            logging.warning(
                f"No download links found for job {existing_job_id}, though it was marked complete."
            )

    elif job_info:
        logging.warning(
            f"Job {existing_job_id} is not complete. Status: {job_info.get('status')}"
        )
    else:
        logging.error(f"Could not retrieve information for job ID {existing_job_id}.")

    # --- Part 2: Submit a new job ---
    logging.info(f"--- Submitting new job: '{new_job_name}' ---")
    new_job_id = client.submit_job(new_job_sequence, new_job_name)

    if new_job_id:
        logging.info(
            f"Successfully submitted job '{new_job_name}' with ID: {new_job_id}"
        )
    else:
        logging.error(
            f"Failed to submit job '{new_job_name}'. Check logs and submission_error.html for details."
        )

    # --- Logout ---
    client.logout()
    logging.info("Test run finished.")


if __name__ == "__main__":
    run_test()
