import logging
import os
import time
import uuid
from robetta_client import RobettaClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def test_robetta_client_functionality():
    """
    Tests the core functionality of the RobettaClient by submitting a job,
    monitoring its status, and attempting to download results.
    """
    test_username = os.environ.get("ROBETTA_USERNAME")
    test_password = os.environ.get("ROBETTA_PASSWORD")

    if not test_username or not test_password:
        logging.error(
            "Please set the ROBETTA_USERNAME and ROBETTA_PASSWORD environment variables for testing."
        )
        return

    client = RobettaClient(test_username, test_password)
    job_id = None
    test_target_name = f"TestJob_{uuid.uuid4().hex[:8]}"
    test_sequence = "AGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCTAGCT"
    results_dir = "./test_results"

    try:
        if not client.login():
            logging.error("Test failed: Login unsuccessful.")
            return
        logging.info("Login successful for testing.")

        logging.info(f"Submitting test job: {test_target_name}")
        job_id = client.submit_job(test_sequence, test_target_name)
        if not job_id:
            logging.error("Test failed: Job submission unsuccessful.")
            return
        logging.info(f"Test job submitted with ID: {job_id}")

        # Monitor job status
        timeout = 600  # 10 minutes timeout
        start_time = time.time()
        job_complete = False

        while time.time() - start_time < timeout:
            job_status = client.get_job_status_by_id(job_id)
            if job_status:
                status = job_status.get("status")
                logging.info(f"Job {job_id} status: {status}")
                if status == "Complete":
                    job_complete = True
                    break
                elif status in ["Active", "Pending", "Submitted"]:
                    time.sleep(30)  # Check every 30 seconds
                else:
                    logging.error(
                        f"Test failed: Job {job_id} has unexpected status: {status}"
                    )
                    return
            else:
                logging.warning(f"Job {job_id} not found in queue. Retrying...")
                time.sleep(30)

        if not job_complete:
            logging.error(
                f"Test failed: Job {job_id} did not complete within {timeout} seconds."
            )
            return

        # Download results
        if job_status and job_status.get("results_link"):
            full_results_link = client.base_url + job_status["results_link"]
            download_links = client.get_job_results_links(full_results_link)

            if not download_links:
                logging.warning(
                    f"No download links found for job {job_id}. This might be expected for some job types or an issue."
                )
            else:
                os.makedirs(results_dir, exist_ok=True)
                download_success_count = 0
                for link in download_links:
                    try:
                        file_name = (
                            os.path.basename(link).split("?")[0] + ".pdb"
                        )  # Simple way to get a filename
                        destination_path = os.path.join(results_dir, file_name)
                        if client.download_file(link, destination_path):
                            download_success_count += 1
                            logging.info(f"Successfully downloaded {file_name}")
                        else:
                            logging.error(f"Failed to download {file_name}")
                    except Exception as e:
                        logging.error(f"Error during download of {link}: {e}")

                if download_success_count > 0:
                    logging.info(
                        f"Test successful: Downloaded {download_success_count} models for job {job_id}."
                    )
                else:
                    logging.warning(
                        f"Test completed, but no models were successfully downloaded for job {job_id}."
                    )
        else:
            logging.warning(f"No results link available for job {job_id}.")

    except Exception as e:
        logging.error(f"An unexpected error occurred during testing: {e}")
    finally:
        if client:
            client.logout()
            logging.info("Logged out from Robetta.")
        # Optional: Clean up downloaded files
        # if os.path.exists(results_dir):
        #     import shutil
        #     shutil.rmtree(results_dir)
        #     logging.info(f"Cleaned up test results directory: {results_dir}")


if __name__ == "__main__":
    test_robetta_client_functionality()
