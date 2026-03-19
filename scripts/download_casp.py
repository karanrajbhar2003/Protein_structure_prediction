#!/usr/bin/env python3
import requests
import tarfile
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://predictioncenter.org/download_area"
CASP_VERSION = "CASP14"
OUTPUT_DIR = "casp_data/CASP14"

NATIVE_URL = f"{BASE_URL}/{CASP_VERSION}/results/sda/"
PRED_URL   = f"{BASE_URL}/{CASP_VERSION}/predictions/regular/"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_and_extract(url, subdir):
    target_dir = os.path.join(OUTPUT_DIR, subdir)
    os.makedirs(target_dir, exist_ok=True)

    print(f"\n🔍 Scraping {url}")
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a"):
        href = link.get("href", "")
        if href.endswith((".tgz", ".tar.gz")):
            file_url = urljoin(url, href)
            fname = os.path.basename(href)
            fpath = os.path.join(target_dir, fname)

            # Correctly determine the name of the directory that the tarball would create
            if fname.endswith(".tar.gz"):
                extracted_dir_name = fname[:-7]
            else: # .tgz
                extracted_dir_name = fname[:-4]
            
            if os.path.exists(os.path.join(target_dir, extracted_dir_name)):
                print(f"✔ Already extracted: {fname}")
                continue

            print(f"⬇ Downloading {fname}")
            try:
                r = requests.get(file_url, stream=True)
                r.raise_for_status() # Raise an exception for bad status codes
                with open(fpath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

                print(f"📦 Extracting {fname}")
                with tarfile.open(fpath) as tar:
                    tar.extractall(target_dir)

            except requests.exceptions.RequestException as e:
                print(f"❌ Error downloading {fname}: {e}")
            except tarfile.ReadError as e:
                print(f"❌ Error extracting {fname}: {e}. It might be a corrupted or empty file.")
            except Exception as e:
                print(f"❌ An unexpected error occurred with {fname}: {e}")
            finally:
                # Ensure the tarball is removed even if errors occur
                if os.path.exists(fpath):
                    os.remove(fpath)

def main():
    download_and_extract(NATIVE_URL, "native")
    download_and_extract(PRED_URL, "models")
    print("\n✅ CASP download & extraction complete.")

if __name__ == "__main__":
    main()
