# src/robetta_client.py
import requests
import logging
import os
import re
import json
import time
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
from pathlib import Path
import webbrowser

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class RobettaClient:
    """
    Robust Robetta client for submitting jobs and downloading results.

    - Attempts to find hidden 'user' id automatically (submit form -> account page -> myqueue page)
    - Includes captcha solver for simple math captchas visible on submit page
    - Saves debug HTML files for inspection on error
    """

    def __init__(self, username: str = "", password: str = "", base_url: str = "https://robetta.bakerlab.org"):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._timeout = 30
        self.last_error: str = ""
        # Basic browser-like headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        # debug dir
        self.debug_dir = Path("debug_robetta")
        self.debug_dir.mkdir(exist_ok=True)

    # --- Cookie helpers ---
    def load_cookies(self) -> bool:
        if Path("cookies.json").exists():
            try:
                with open("cookies.json", "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.session.cookies.update(data)
                logger.info("Loaded cookies.json")
                return True
            except Exception as e:
                logger.warning("Failed to load cookies.json: %s", e)
        return False

    def save_cookies(self) -> None:
        try:
            with open("cookies.json", "w", encoding="utf-8") as fh:
                json.dump(requests.utils.dict_from_cookiejar(self.session.cookies), fh)
            logger.info("Saved cookies.json")
        except Exception as e:
            logger.warning("Failed to save cookies.json: %s", e)

    # --- login detection & helpers ---
    def _test_login(self) -> bool:
        """Return True if the session appears logged-in (heuristic)."""
        try:
            resp = self.session.get(f"{self.base_url}/myqueue.php", timeout=self._timeout)
            if resp.status_code != 200:
                return False
            txt = resp.text.lower()
            if "log out" in txt or (self.username and self.username.lower() in txt):
                return True
        except Exception as e:
            logger.debug("_test_login error: %s", e)
        return False

    def login(self) -> bool:
        """Login using username/password. Saves cookies on success."""
        if self._test_login():
            logger.info("Already logged in (cookies valid).")
            return True

        login_url = f"{self.base_url}/login.php"
        try:
            resp = self.session.get(login_url, timeout=self._timeout)
        except Exception as e:
            logger.error("Failed to get login page: %s", e)
            return False

        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.find("form")
        if not form:
            fn = self.debug_dir / f"login_page_{int(time.time())}.html"
            fn.write_text(resp.text, encoding="utf-8")
            logger.error("Login form not found, saved %s", fn)
            return False

        # collect inputs
        inputs = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            typ = (inp.get("type") or "text").lower()
            val = inp.get("value") or ""
            inputs[name] = {"type": typ, "value": val}

        # heuristics to choose username/password fields
        pwd_name = None
        for k, v in inputs.items():
            if v["type"] == "password" or re.search(r"pass", k, re.I):
                pwd_name = k
                break

        user_name = None
        for cand in ("email_addr", "email", "username", "user", "login"):
            if cand in inputs:
                user_name = cand
                break
        if not user_name:
            for k, v in inputs.items():
                if v["type"] in ("text", "email") and k != pwd_name:
                    user_name = k
                    break

        if user_name:
            inputs[user_name]["value"] = self.username
        if pwd_name:
            inputs[pwd_name]["value"] = self.password

        payload = {k: v["value"] for k, v in inputs.items()}

        # check simple math captcha
        captcha = self._solve_math_captcha(soup)
        if captcha:
            payload.setdefault("q", captcha)

        action = form.get("action") or "login_action.php"
        post_url = action if action.startswith("http") else f"{self.base_url}/{action.lstrip('/')}"
        try:
            post_resp = self.session.post(post_url, data=payload, timeout=self._timeout)
        except Exception as e:
            logger.error("Login POST failed: %s", e)
            return False

        # Save cookies and verify
        self.save_cookies()
        time.sleep(0.5)
        if self._test_login():
            logger.info("Login successful.")
            return True

        fn = self.debug_dir / f"login_post_{int(time.time())}.html"
        fn.write_text(post_resp.text or "", encoding="utf-8")
        logger.error("Login did not appear successful. Saved %s", fn)
        return False

    def logout(self) -> None:
        try:
            self.session.get(f"{self.base_url}/logout.php", timeout=self._timeout)
        except Exception:
            pass
        logger.info("Logged out.")

    # --- utility: simple captcha solver ---
    def _solve_math_captcha(self, soup: BeautifulSoup) -> Optional[str]:
        if not soup:
            return None
        text = soup.get_text()
        m = re.search(r"(\d+)\s*\+\s*(\d+)", text)
        if m:
            return str(int(m.group(1)) + int(m.group(2)))
        m = re.search(r"(\d+)\s*-\s*(\d+)", text)
        if m:
            return str(int(m.group(1)) - int(m.group(2)))
        return None

    # --- fetch submit page and parse fields ---
    def get_submit_page(self) -> Optional[str]:
        try:
            # ensure login if username/password set
            if self.username and not self._test_login():
                logger.info("Not logged in - attempting login before fetching submit page")
                if not self.login():
                    logger.warning("Login failed before fetching submit page")
            resp = self.session.get(f"{self.base_url}/submit.php", timeout=self._timeout)
            fn = self.debug_dir / f"submit_page_{int(time.time())}.html"
            fn.write_text(resp.text or "", encoding="utf-8")
            return resp.text
        except Exception as e:
            logger.error("Failed to fetch submit page: %s", e)
            return None

    def _parse_hidden_user_from_html(self, html: str) -> Optional[str]:
        """Try multiple heuristics to locate a hidden 'user' field value in HTML."""
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        # 1) direct hidden input name="user"
        inp = soup.find("input", {"name": "user"})
        if inp and inp.get("value"):
            return inp.get("value").strip()
        # 2) any hidden input carrying numeric value that looks like user id
        for h in soup.find_all("input", {"type": "hidden"}):
            val = (h.get("value") or "").strip()
            name = (h.get("name") or "").lower()
            if val and re.fullmatch(r"\d{4,8}", val):
                # prefer fields that look like user id
                if "user" in name or "uid" in name or name == "":
                    return val
        # 3) look for text patterns like value="70069" near "user"
        m = re.search(r'name=["\"]user["\"]\s+value=["\"](\d{4,8})["\"]', html, re.I)
        if m:
            return m.group(1)
        return None

    def _get_user_id(self) -> Optional[str]:
        """Fetch submit page and/or account pages to discover numeric 'user' id required by submit_action."""
        # try submit page
        submit_html = self.get_submit_page()
        uid = self._parse_hidden_user_from_html(submit_html or "")
        if uid:
            logger.info("Found user id on submit page: %s", uid)
            return uid

        # try account/myaccount pages
        try_urls = ["/account.php", "/myaccount.php", "/myqueue.php"]
        for u in try_urls:
            try:
                resp = self.session.get(f"{self.base_url}{u}", timeout=self._timeout)
                fn = self.debug_dir / f"{u.lstrip('/')}_{int(time.time())}.html"
                fn.write_text(resp.text or "", encoding="utf-8")
                uid = self._parse_hidden_user_from_html(resp.text or "")
                if uid:
                    logger.info("Found user id on %s: %s", u, uid)
                    return uid
            except Exception:
                continue
        logger.warning("Could not find numeric user id automatically.")
        return None

    # --- submit job ---
    def submit_job(self,
                   sequence: str,
                   job_name: str,
                   nstruct: int = 1,
                   rosettafold: bool = True,
                   cm: bool = False,
                   ab: bool = False) -> Optional[str]:
        """
        Submit a job. Returns job_id string on success, None on failure.
        Ensures the 'user' hidden field is present.
        """
        self.last_error = ""
        # sanitize sequence (remove whitespace/newlines but keep single-letter codes)
        seq_clean = "".join(sequence.split())
        if len(seq_clean) < 10:
            self.last_error = f"Sequence too short ({len(seq_clean)} aa)."
            logger.error(self.last_error)
            return None

        # attempt to parse submit form to get any hidden fields
        submit_html = self.get_submit_page()
        if submit_html is None:
            self.last_error = "Failed to fetch Robetta submit page."
            logger.error(self.last_error)
            return None
        submit_html_lower = submit_html.lower()
        if "server submissions are currently unavailable due to maintenance" in submit_html_lower:
            self.last_error = "Robetta submissions are currently unavailable due to maintenance."
            logger.error(self.last_error)
            return None
        soup = BeautifulSoup(submit_html, "html.parser")
        form = soup.find("form")
        # compose payload from hidden inputs if available
        payload = {}
        if form:
            for inp in form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                typ = (inp.get("type") or "text").lower()
                val = inp.get("value") or ""
                if typ == "hidden":
                    payload[name] = val

        # ensure 'user' is present
        if "user" not in payload or not str(payload.get("user")).strip():
            uid = self._get_user_id()
            if uid:
                payload["user"] = uid
                logger.info("Using discovered user id: %s", uid)
            else:
                self.last_error = "Could not determine valid Robetta user id from submit/account pages."
                logger.warning("No 'user' in form and fallback discovery failed. Will attempt to include username as 'user' (may be rejected).")
                # fallback: sometimes form accepts numeric account or username, but most recent server needs numeric id
                payload["user"] = self.username or ""

        # fill the rest of minimal fields explicitly (override/ensure)
        payload.update({
            "targetname": job_name,
            "sequence": seq_clean,
            "nstruct": str(nstruct),
            "rosettafold_only": "1" if rosettafold else "0",
            # explicit flags for CM/AB if requested
            "cm_only": "1" if cm else "0",
            "ab_only": "1" if ab else "0",
            "submit": "Submit"
        })

        # solve captcha if present
        captcha = self._solve_math_captcha(soup)
        if captcha:
            payload["q"] = captcha

        # determine post_url from form action if possible
        action = "submit_action.php"
        if form and form.get("action"):
            action = form.get("action")
        post_url = action if action.startswith("http") else f"{self.base_url}/{action.lstrip('/')}"

        logger.info("Submitting job to %s", post_url)
        logger.debug("Payload keys: %s", list(payload.keys()))
        try:
            resp = self.session.post(post_url, data=payload, timeout=self._timeout)
        except Exception as e:
            fn = self.debug_dir / f"submit_post_error_{int(time.time())}.html"
            fn.write_text(str(e), encoding="utf-8")
            self.last_error = f"Submission POST exception: {e}"
            logger.error("Submission POST exception: %s (saved %s)", e, fn)
            return None

        resp_html = resp.text or ""
        resp_file = self.debug_dir / f"submit_response_{int(time.time())}.html"
        resp_file.write_text(resp_html, encoding="utf-8")
        logger.info("Submission response saved to %s (status %s)", resp_file, resp.status_code)

        # quick checks for server messages
        if "missing or bad parameter: user" in resp_html.lower():
            self.last_error = "Robetta rejected submission: missing or bad user parameter."
            logger.error("Server responded: missing or bad parameter: user. Check %s", resp_file)
            return None
        if "invalid user" in resp_html.lower():
            self.last_error = "Robetta rejected submission: invalid user."
            logger.error("Server responded: invalid user. Check %s", resp_file)
            return None
        if "can't submit" in resp_html.lower():
            self.last_error = "Robetta returned 'Can't submit'. Check maintenance status and credentials."
            logger.error("Server returned 'Can't submit'. Check %s", resp_file)
            return None
        if "captcha" in resp_html.lower() or "unable to handle request" in resp_html.lower():
            self.last_error = "Robetta blocked submission (captcha or request handling issue)."
            logger.error("Server reported a block/captcha. Open %s in your browser to inspect.", resp_file)
            try:
                webbrowser.open(f"file://{resp_file.resolve()}")
            except Exception:
                pass
            return None

        # Try to parse job id from response (common patterns)
        m = re.search(r"id=(\d+)", resp_html)
        if m:
            job_id = m.group(1)
            logger.info("Extracted job id: %s", job_id)
            return job_id

        # fallback: check queue for a job matching the name (small delay then query)
        time.sleep(2)
        queue = self.get_job_queue()
        for job in queue:
            if job_name.lower() in job.get("target_name", "").lower():
                logger.info("Found job in queue: %s", job.get("job_id"))
                return job.get("job_id")

        logger.error("Could not determine job id after submission. See %s", resp_file)
        if not self.last_error:
            self.last_error = f"Could not determine job id after submission. See {resp_file}"
        return None

    # --- queue & results helpers ---
    def get_job_queue(self) -> List[Dict[str, str]]:
        queue = []
        url = f"{self.base_url}/myqueue.php"
        try:
            resp = self.session.get(url, timeout=self._timeout)
            debug_file = self.debug_dir / f"myqueue_page_{int(time.time())}.html"
            debug_file.write_text(resp.text, encoding="utf-8")

            if resp.status_code != 200:
                logger.error(f"Failed to fetch queue page. Status: {resp.status_code}. See {debug_file}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Use a more specific selector to find the correct table
            jobs_div = soup.find("div", {"class": "table"})
            if not jobs_div:
                logger.warning(f"Could not find the main jobs <div class='table'>. See {debug_file}")
                return []
            table = jobs_div.find("table")
            if not table:
                logger.warning(f"Could not find a <table> inside the jobs div. See {debug_file}")
                return []

            rows = table.find_all("tr")
            if len(rows) < 2:
                logger.info("Queue table is empty or has only a header.")
                return []

            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all("th")]
            
            # Map columns using the correct header names from the HTML
            col_map = {}
            try:
                col_map['id'] = headers.index('job id')
                col_map['status'] = headers.index('status')
                col_map['name'] = headers.index('target') # Corrected from 'target name'
            except ValueError as e:
                logger.error(f"Could not map expected headers ('job id', 'status', 'target') from the table. Header parsing error: {e}. Headers found: {headers}. See {debug_file}")
                return []

            for r in rows[1:]:
                cells = r.find_all("td")
                if len(cells) <= max(col_map.values()):
                    continue

                id_cell = cells[col_map['id']]
                link = id_cell.find("a", href=re.compile(r"results\.php\?id=\d+"))
                
                if not link:
                    continue

                job_id = link.get_text(strip=True)
                
                # FIX: Handle both relative and absolute URLs
                href = link['href']
                if href.startswith("http"):
                    results_url = href
                else:
                    results_url = f"{self.base_url}/{href.lstrip('/')}"
                    
                status = cells[col_map['status']].get_text(strip=True)
                target_name = cells[col_map['name']].get_text(strip=True)

                queue.append({
                    "job_id": job_id,
                    "target_name": target_name,
                    "status": status,
                    "results_link": results_url
                })

            if not queue:
                 logger.warning(f"Parsed queue page and table, but found 0 job rows. The HTML structure may have changed. See {debug_file}")
            else:
                 logger.info(f"Successfully parsed {len(queue)} jobs from the queue page.")

        except Exception as e:
            logger.error(f"An exception occurred in get_job_queue: {e}", exc_info=True)
        
        return queue

    def download_file(self, url: str, save_path: str) -> bool:
        """Downloads a file from a URL to a local path."""
        try:
            with self.session.get(url, timeout=self._timeout, stream=True) as resp:
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Downloaded {url} to {save_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False

    def get_job_results(self, results_page_url: str) -> Dict:
        results = {
            "pdb_links": [],
            "confidence": None,
            "plot_data": []
        }
        try:
            resp = self.session.get(results_page_url, timeout=self._timeout)
            resp.raise_for_status()

            debug_file = self.debug_dir / f"results_page_{int(time.time())}.html"
            debug_file.write_text(resp.text, encoding="utf-8")
            logger.info(f"Saved results page to {debug_file}")
            
            html_content = resp.text
            soup = BeautifulSoup(html_content, "html.parser")

            # --- Extract Confidence Score ---
            try:
                domains_table = soup.find("table", {"id": "domains"})
                if domains_table:
                    first_row = domains_table.find("tr", id=re.compile(r"cut\d+domain\d+"))
                    if first_row:
                        cells = first_row.find_all("td")
                        if len(cells) > 3:
                            confidence_str = cells[3].get_text(strip=True)
                            results["confidence"] = float(confidence_str)
                            logger.info(f"Found confidence score: {results['confidence']}")
            except Exception as e:
                logger.warning(f"Could not extract confidence score: {e}")

            # --- Extract Plot Data ---
            try:
                script_tags = soup.find_all("script")
                js_content = "\n".join(str(s) for s in script_tags)
                
                # Find all data_bfact variables
                plot_data_matches = re.findall(r"var\s+(data_bfact\d+)\s*=\s*(\[.*?\]);", js_content, re.DOTALL)
                for match in plot_data_matches:
                    var_name, json_like_data = match
                    model_num = int(re.search(r'\d+', var_name).group())
                    
                    # The data is javascript, not strict JSON, so we need to parse it carefully
                    # This is a simplified parser that assumes the structure is consistent
                    x_match = re.search(r"x:\s*(\[.*?\])", json_like_data, re.DOTALL)
                    y_match = re.search(r"y:\s*(\[.*?\])", json_like_data, re.DOTALL)
                    
                    if x_match and y_match:
                        x_data_str = x_match.group(1).replace('[', '').replace(']', '')
                        y_data_str = y_match.group(1).replace('[', '').replace(']', '')
                        
                        x_data = [int(v.strip()) for v in x_data_str.split(',') if v.strip()]
                        y_data = [float(v.strip()) for v in y_data_str.split(',') if v.strip()]
                        
                        results["plot_data"].append({
                            "model_name": f"Model {model_num}",
                            "x": x_data,
                            "y": y_data
                        })
                logger.info(f"Found plot data for {len(results['plot_data'])} models.")

            except Exception as e:
                logger.warning(f"Could not extract plot data: {e}")


            # --- Heuristic 1: Find the main "Download All" link ---
            main_download_link = soup.find("a", href=re.compile(r"models_download\.php\?id=\d+"))
            if main_download_link:
                href = main_download_link['href']
                full_url = href if href.startswith("http") else f"{self.base_url}/{href.lstrip('/')}"
                results["pdb_links"].append(full_url)
                logger.info(f"Found main download link: {full_url}")

            # --- Heuristic 2: Scrape JS for individual model links ---
            script_tags = soup.find_all("script")
            js_content = "\n".join(str(s) for s in script_tags)

            token_match = re.search(r"token=([a-zA-Z0-9\.]+)", js_content)
            job_id_match = re.search(r'id=(\d+)', results_page_url)

            if token_match and job_id_match:
                token = token_match.group(1)
                job_id = job_id_match.group(1)
                logger.info(f"Found download token '{token}' and job ID '{job_id}' in JavaScript.")

                model_tabs = soup.find_all("a", href=re.compile(r"#model\d+"))
                num_models = len(model_tabs)
                if num_models > 0:
                    logger.info(f"Found {num_models} model tabs. Generating individual download links.")
                    for i in range(1, num_models + 1):
                        dl_url = f"{self.base_url}/model_download.php?id={job_id}&model={i}&token={token}"
                        results["pdb_links"].append(dl_url)
                else:
                    logger.warning("Found a token but couldn't determine the number of models from tabs.")

            # --- Fallback: Original simple `<a>` tag search ---
            if not results["pdb_links"]:
                logger.info("Heuristics failed, trying simple search for <a> tags.")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if any(ext in href.lower() for ext in (".pdb", ".tgz", ".zip", ".tar")) or "model_download.php" in href or "models_download.php" in href:
                        full_url = href if href.startswith("http") else f"{self.base_url}/{href.lstrip('/')}"
                        results["pdb_links"].append(full_url)
            
            results["pdb_links"] = list(dict.fromkeys(results["pdb_links"])) # dedupe

        except Exception as e:
            logger.error(f"get_job_results error: {e}", exc_info=True)
        
        if not results["pdb_links"]:
            logger.warning(f"Could not find any download links on the results page. See {debug_file}")
            
        return results

    # Compatibility alias so Streamlit & CLI don't break
    def test_login(self):
        return self._test_login()
