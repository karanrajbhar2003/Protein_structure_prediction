#!/usr/bin/env python3
import sys
import logging
import os
import time
import re
import json
import argparse
from typing import Optional

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from robetta_client import RobettaClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def do_submit(client, args):
    seq = args.sequence.strip().upper().replace("\n", "")
    job_name = args.name.strip()

    # First attempt: RoseTTAFold mode
    job_id = client.submit_job(
        sequence=seq,
        job_name=job_name,
        rosettafold=True,
        cm=False,
        ab=False
    )

    # Fallback: AB mode if RoseTTAFold submission appears unavailable
    if not job_id:
        primary_error = client.last_error or "RoseTTAFold submission failed."
        low_err = primary_error.lower()
        should_try_ab = any(token in low_err for token in [
            "maintenance",
            "unavailable",
            "can't submit",
            "cannot submit",
        ])
        if should_try_ab:
            logging.warning("RoseTTAFold submission failed (%s). Trying AB fallback...", primary_error)
            job_id = client.submit_job(
                sequence=seq,
                job_name=job_name,
                rosettafold=False,
                cm=False,
                ab=True
            )

    if not job_id:
        logging.error("Job submission failed: %s", client.last_error or "Unknown error")
        return 1

    print(f"JOB_ID={job_id}")
    return 0


def do_download(client, args):
    job_id = args.job_id
    outdir = args.output_dir
    os.makedirs(outdir, exist_ok=True)

    # Fetch the entire queue to find our job
    logging.info(f"Fetching queue to find job {job_id}...")
    queue = client.get_job_queue()
    job_to_download = None
    for job in queue:
        if job.get("job_id") == job_id:
            job_to_download = job
            break
    
    if not job_to_download:
        logging.error(f"❌ Job with ID '{job_id}' not found in your queue.")
        return 1

    if job_to_download.get("status", "").lower() != "complete":
        logging.error(f"❌ Job {job_id} is not complete (status: {job_to_download.get('status', 'Unknown')}).")
        return 1
        
    results_link = job_to_download.get("results_link")
    if not results_link:
        logging.error(f"❌ Could not find results link for job {job_id}.")
        return 1

    results_data = client.get_job_results(results_link)
    if not results_data or not results_data["pdb_links"]:
        logging.error("❌ No download links found on the results page.")
        return 1

    downloaded_models = []
    links = results_data.get("pdb_links", [])
    plot_data = results_data.get("plot_data", [])
    
    logging.info(f"Found {len(links)} download links for job {job_id}.")
    for link in links:
        model_num_match = re.search(r"model=(\d+)", link)
        if not model_num_match:
            continue

        model_num = int(model_num_match.group(1))
        fname = f"robetta_{job_id}_model_{model_num}.pdb"
        save_path = os.path.join(outdir, fname)

        if client.download_file(link, save_path):
            model_info = {
                "pdb_file": save_path,
                "confidence": results_data.get("confidence"),
                "model_name": f"Model {model_num}",
                "plot_data_file": None
            }

            # Find corresponding plot data
            for plot in plot_data:
                if plot.get("model_name") == f"Model {model_num}":
                    plot_fname = f"robetta_{job_id}_model_{model_num}_plot_data.json"
                    plot_save_path = os.path.join(outdir, plot_fname)
                    with open(plot_save_path, "w") as f:
                        json.dump(plot, f)
                    model_info["plot_data_file"] = plot_save_path
                    break
            
            downloaded_models.append(model_info)
        else:
            logging.warning(f"Failed to download {link}")

    # Print a JSON object at the end for easy parsing
    print("###DOWNLOADED_FILES_JSON_START###")
    print(json.dumps(downloaded_models, indent=2))
    print("###DOWNLOADED_FILES_JSON_END###")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Submit jobs to or download results from the Robetta server.")
    
    # Credentials can be provided via arguments or environment variables
    parser.add_argument("--username", default=os.environ.get("ROBETTA_USERNAME"), help="Robetta username (or set ROBETTA_USERNAME env var).")
    parser.add_argument("--password", default=os.environ.get("ROBETTA_PASSWORD"), help="Robetta password (or set ROBETTA_PASSWORD env var).")

    sub = parser.add_subparsers(dest="command", required=True)
    
    # Sub-command to submit a modeling job
    p_submit = sub.add_parser("submit", help="Submit a new protein modeling job.")
    p_submit.add_argument("--sequence", required=True, help="Amino acid sequence to model.")
    p_submit.add_argument("--name", required=True, help="A descriptive name for the job.")

    # Sub-command to list jobs in the queue
    p_queue = sub.add_parser("queue", help="List all jobs in your Robetta queue.")
    p_queue.add_argument("--json", action="store_true", help="Output the queue in JSON format.")

    # Sub-command to download results for a completed job
    p_download = sub.add_parser("download", help="Download results for a specific job ID.")
    p_download.add_argument("--job-id", required=True, help="The ID of the job to download.")
    p_download.add_argument("--output-dir", required=True, help="Directory to save the downloaded files.")

    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("Robetta username and password are required. Provide them as arguments or set ROBETTA_USERNAME and ROBETTA_PASSWORD environment variables.")

    client = RobettaClient(username=args.username, password=args.password)
    client.load_cookies()
    client.login()

    if args.command == "submit":
        sys.exit(do_submit(client, args))

    elif args.command == "queue":
        queue = client.get_job_queue()
        if not queue:
            logging.warning("No jobs found in queue or failed to fetch.")
            if args.json:
                print("[]")
            else:
                print("No jobs found in queue.")
            sys.exit(0)

        if args.json:
            print(json.dumps(queue))
        else:
            print(f"{'Job ID':<15} {'Status':<15} {'Target Name':<40}")
            print("-" * 70)
            for job in queue:
                print(f"{job.get('job_id', 'N/A'):<15} {job.get('status', 'N/A'):<15} {job.get('target_name', 'N/A'):<40}")
        sys.exit(0)

    elif args.command == "download":
        sys.exit(do_download(client, args))

    client.logout()


if __name__ == "__main__":
    main()

