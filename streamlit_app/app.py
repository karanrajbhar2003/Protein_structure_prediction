#!/usr/bin/env python3
"""
Streamlit app for ProteinGuide — fixed ROOT ordering
"""

import matplotlib.pyplot as plt
import streamlit as st
import time
st.info(f"Script last ran at: {time.time()}")

import tempfile
import os
import subprocess
import json
import re
from pathlib import Path
import shutil
import logging
import sys

# ----------------------------------
# ✔ FIX: DEFINE ROOT BEFORE USING IT
# ----------------------------------
ROOT = Path(__file__).resolve().parent.parent

# now it's safe
sys.path.append(str(ROOT / "src"))
from robetta_client import RobettaClient

CONFIG_FILE = ROOT / "streamlit_app" / "config.json"

# --- helper utilities ---

def load_config():
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                pass
    config.setdefault("robetta_user", "")
    config.setdefault("robetta_pass", "")
    config.setdefault("qmean_email", "")
    config.setdefault("qmean_token", "")
    config.setdefault("voromqa_path", "")
    return config


def save_config(config_dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_dict, f, indent=2)


def clean_sequence(raw):
    # remove header
    lines = raw.splitlines()
    seq = ''.join([l.strip() for l in lines if not l.startswith(">")])

    # keep only valid amino acid letters
    seq = re.sub(r'[^ACDEFGHIKLMNPQRSTVWY]', '', seq.upper())

    return seq


config = load_config()

st.set_page_config(page_title="ProSutra", layout="wide")

st.title("Prosutra — Modeling & Validation Dashboard (Prototype)")

# --- utility: extract embedded JSON from long stdout ---
JSON_START = "###MODELLER_JSON_START###"
JSON_END = "###MODELLER_JSON_END###"

def extract_embedded_json(text: str):
    """Look for explicit JSON markers in a long log and return parsed JSON or None."""
    m = re.search(re.escape(JSON_START) + r"(.*?)" + re.escape(JSON_END), text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def read_summary_json_from_dir(d: Path, tool_name: str = "modeller"):
    """Try to read <tool>_summary.json or modeller_summary.json from directory.
    Returns dict or None."""
    candidates = [d / f"{tool_name}_summary.json", d / "modeller_summary.json"]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                return None
    return None


# --- subprocess helpers with streaming UI ---

def stream_subprocess(cmd, display_container=None, cwd=None, env=None):
    """Run subprocess, stream stdout/stderr to Streamlit display container, return (returncode, full_output)."""
    if display_container is None:
        display_container = st.empty()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', cwd=cwd, env=env)
    full_output = ""
    log_text = ""
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            log_text += line
            # update display (replace to avoid many elements)
            display_container.text(log_text)
            full_output += line
    rc = proc.wait()
    return rc, full_output


# --- UI: top-level generate report block ---
st.header("Generate Report")
if "results_dir" in st.session_state:
    results_dir = Path(st.session_state["results_dir"])
    model_name = results_dir.name
    st.info(f"Ready to generate report for: {model_name}")

    if st.button("Generate PDF Report"):
        st.info("Generating PDF — this may take a moment.")
        pdf_out = results_dir / (model_name + "_validation_report.pdf")
        gen_cmd = ["python", str(ROOT / "tools" / "generate_validation_pdf.py"),
                   "--model_dir", str(results_dir),
                   "--out_pdf", str(pdf_out)]
        if "selected_validators" in st.session_state and st.session_state["selected_validators"]:
            gen_cmd.extend(["--validators", ",".join(st.session_state["selected_validators"])])

        st.write("Command:")
        st.code(" ".join(gen_cmd))
        rc, full_output = stream_subprocess(gen_cmd, display_container=st.empty())
        st.write(f"Return code: {rc}")
        if rc == 0 and pdf_out.exists():
            st.success("PDF created.")
            with open(pdf_out, "rb") as fh:
                # unique key to avoid duplicate-element error
                st.download_button("Download report", fh.read(), file_name=pdf_out.name, key=f"download_report_{pdf_out.name}")
        else:
            st.error("PDF generation failed.")
else:
    st.info("Run a validation to see the 'Generate PDF Report' button here.")

# --- Sidebar controls & form inputs (unchanged logic mostly) ---
st.sidebar.header("Mode")
modeling_mode = st.sidebar.radio("Mode", ("Run New Model", "Use Existing PDB for Validation"))
project_name = st.sidebar.text_input("Project Name", "my_protein_project")

if modeling_mode == "Use Existing PDB for Validation":
    st.sidebar.header("Model / Input")
    pdb_upload = st.sidebar.file_uploader("Upload PDB file", type=["pdb", "ent"])
    use_existing = st.sidebar.checkbox("Use existing PDB path (enter below)")
    pdb_path_input = st.sidebar.text_input("PDB path (if using existing)", value="")
else:
    pdb_upload = None
    use_existing = False
    pdb_path_input = ""


st.sidebar.header("Tool Paths & Credentials")
robetta_user = st.sidebar.text_input("Robetta Username", value=config.get("robetta_user", ""))
robetta_pass = st.sidebar.text_input("Robetta Password", value=config.get("robetta_pass", ""), type="password")

voromqa_path_input = st.sidebar.text_input("VoroMQA Path", value=config.get("voromqa_path", ""))

qmean_email = st.sidebar.text_input("QMEAN Email", value=config.get("qmean_email", ""))
qmean_token = st.sidebar.text_input("QMEAN Token", value=config.get("qmean_token", ""), type="password")

if st.sidebar.button("Save Credentials & Paths"):
    config["robetta_user"] = robetta_user
    config["robetta_pass"] = robetta_pass
    config["voromqa_path"] = voromqa_path_input
    config["qmean_email"] = qmean_email
    config["qmean_token"] = qmean_token
    save_config(config)
    st.sidebar.success("Credentials and paths saved.")

st.sidebar.header("Validators")
validators = {
    "pdbfixer": st.sidebar.checkbox("PDBFixer", True),
    "dssp": st.sidebar.checkbox("DSSP", True),
    "freesasa": st.sidebar.checkbox("FreeSASA", True),
    "molprobity": st.sidebar.checkbox("MolProbity", True),
    "prosa": st.sidebar.checkbox("ProSA (local+web)", True),
    "voromqa": st.sidebar.checkbox("VoroMQA", True),
    "qmean": st.sidebar.checkbox("QMEAN (SWISS-MODEL API)", True),
    "modeller": st.sidebar.checkbox("Modeller", True),
}
run_validation_button = st.sidebar.button("Run selected validators")

# Workspace
workspace = ROOT / "streamlit_workspace"
workspace.mkdir(exist_ok=True)


def save_uploaded(uploaded_file):
    dest = workspace / uploaded_file.name
    with open(dest, "wb") as fh:
        fh.write(uploaded_file.getbuffer())
    return str(dest)


# run_modeling_job improved: capture output, extract JSON markers or fallback to summary file
def run_modeling_job(script_relpath, fasta_path, out_dir, extra_args=None):

    # 1. Read FASTA correctly → Modeller needs SEQUENCE, not file
    with open(fasta_path, "r") as f:
        seq = "".join([line.strip() for line in f if not line.startswith(">")])

    # 2. Build correct command
    cmd = [
        "python",
        str(ROOT / script_relpath),
        "--sequence", seq,
        "--job_name", Path(out_dir).name,
        "--results_dir", str(out_dir)
    ]

    # 3. Add user-specified extra args (like --num_models)
    if extra_args:
        cmd.extend(extra_args)

    # 4. Run with log streaming
    disp = st.empty()
    rc, full_output = stream_subprocess(cmd, display_container=disp)

    # Extract JSON etc.
    parsed = extract_embedded_json(full_output)
    if parsed:
        return rc, parsed, full_output
    
    summary = read_summary_json_from_dir(Path(out_dir), tool_name="modeller")
    if summary:
        return rc, summary, full_output
    
    return rc, None, full_output


# run_wrapper: generic for validators (existing function preserved with small safety)
def run_wrapper(script_relpath, pdb_path, out_dir, extra_args=None):
    cmd = ["python", str(ROOT / script_relpath), "--pdb_file", str(pdb_path), "--output_dir", str(out_dir)]
    if extra_args:
        cmd += extra_args
    
    st.info(f"Executing command: {' '.join(cmd)}")

    # Use a placeholder for the streaming output
    display_container = st.empty()
    rc, full_output = stream_subprocess(cmd, display_container=display_container)

    # If the process failed, show the full log in an expander for debugging
    if rc != 0:
        with st.expander("Error Log", expanded=True):
            st.error(f"Subprocess failed with exit code {rc}.")
            st.text(f"Command: {' '.join(cmd)}")
            st.text("Full Output:")
            st.text(full_output)

    # The rest of the function for successful runs
    tool_name = Path(script_relpath).stem.replace("_wrapper", "")
    summary = read_summary_json_from_dir(Path(out_dir), tool_name=tool_name)
    if summary:
        st.write(f"Read summary for {tool_name}:")
        st.json(summary)
    else:
        st.write(f"No summary file found for {tool_name}.")

    return rc, full_output


def show_tool_outputs(tool_dir):
    tool_dir = Path(tool_dir)
    if not tool_dir.exists():
        st.info(f"No outputs found at {tool_dir}")
        return
    # show JSON summary
    for fname in tool_dir.glob("*_summary.json"):
        with open(fname) as fh:
            try:
                data = json.load(fh)
                st.subheader(f"{tool_dir.name} summary")
                st.json(data)
            except Exception:
                st.text(f"Could not parse {fname}")
    # show images
    imgs = list(tool_dir.glob("*.png")) + list(tool_dir.glob("*.svg"))
    for img in imgs:
        try:
            st.image(str(img), caption=f"{tool_dir.name}: {img.name}", use_column_width=True)
        except Exception:
            st.text(f"Could not display image: {img}")


# Modeling UI
if modeling_mode == "Run New Model":
    with st.expander("Protein Modeling", expanded=True):
        run_modeller = st.checkbox("Run Modeller", value=False)
        run_robetta = st.checkbox("Run Robetta", value=False)

        fasta_content = st.text_area("Paste FASTA sequence here")
        fasta_upload = st.file_uploader("Or upload a FASTA file", type=["fasta", "fa"])
        job_name_input = st.text_input("Job Name (optional)")

        # New: number of modeller models option
        modeller_num_models = st.number_input("Number of models to generate (Modeller)", min_value=1, max_value=50, value=5)

        if fasta_upload:
            fasta_content = fasta_upload.read().decode("utf-8")
            st.text_area("FASTA sequence", value=fasta_content, height=200)

        run_modeling_button = st.button("Run Modeling")

        if run_modeling_button:
            if not fasta_content:
                st.error("Please provide a FASTA sequence.")
            else:
                with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".fasta") as tmp_fasta:
                    tmp_fasta.write(fasta_content)
                    tmp_fasta_path = tmp_fasta.name

                timestamp = time.strftime('%Y%m%d_%H%M%S')

                # Determine job name
                if job_name_input:
                    job_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', job_name_input)
                else:
                    job_name_raw = fasta_content.splitlines()[0][1:].strip() if fasta_content.startswith('>') else f"job_{timestamp}"
                    job_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', job_name_raw)

                if "generated_models" not in st.session_state:
                    st.session_state["generated_models"] = []

                if run_modeller:
                    with st.spinner("Running Modeller..."):
                        modeller_out_dir = ROOT / "results" / project_name / "model_generation_folder" / "modeller" / f"{job_name}_{timestamp}"
                        modeller_out_dir.mkdir(parents=True, exist_ok=True)
                        st.header("Running Modeller...")
                        extra_args = ["--num_models", str(modeller_num_models)]
                        rc, modeller_results, full_output = run_modeling_job("scripts/run_modeller_job.py", tmp_fasta_path, str(modeller_out_dir), extra_args=extra_args)

                        if rc == 0:
                            st.success("Modeller job finished.")

                            # If modeller_results were not parsed from stdout, create empty dict
                            if modeller_results is None:
                                modeller_results = {}

                            # Build a normalized summary dictionary
                            summary = {
                                "job_name": job_name,
                                "sequence_length": len(fasta_content.replace("\n", "")),
                                "modeller_version": "10.7",
                                "generated_at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                "templates": modeller_results.get("templates", []),
                                "models": modeller_results.get("models", []),
                            }

                            # Best model selection
                            if summary["models"]:
                                best = min(summary["models"], key=lambda m: m.get("dope_score", 9e9))
                                summary["best_model"] = best
                            else:
                                summary["best_model"] = {}

                            # Write the required modeller_summary.json file
                            summary_file = modeller_out_dir / "modeller_summary.json"
                            with open(summary_file, "w") as f:
                                json.dump(summary, f, indent=2)
                            st.success(f"Saved summary JSON → {summary_file}")

                            # Show results in UI
                            st.json(summary)

                            # --- Keep other functionality working ---
                            # Store results in session state for PDF button and other tools
                            st.session_state["modeller_results"] = summary
                            st.session_state["modeller_results_dir"] = str(modeller_out_dir)

                            # Store PDB model list for the "Generated Models" display
                            models_from_summary = summary.get("models", [])
                            if models_from_summary:
                                model_paths = [modeller_out_dir / m["model_name"] for m in models_from_summary if "model_name" in m]
                                st.session_state["generated_models"] = [str(p) for p in model_paths if p.exists()]
                            else: # Fallback to globbing if models not in summary
                                models = sorted(modeller_out_dir.glob("*.pdb"))
                                st.session_state["generated_models"] = [str(m) for m in models]


                            # PDF Generator Button
                            if "modeller_pdf_path" not in st.session_state:
                                st.session_state.modeller_pdf_path = None

                            if st.button("Generate PDF Report (Modeller)"):
                                results_dir = Path(st.session_state["modeller_results_dir"])
                                pdf_file = results_dir / "modeller_report.pdf"
                                st.session_state.modeller_pdf_path = None # Reset on new attempt

                                with st.spinner("Generating PDF..."):
                                    pdf_cmd = [
                                        "python",
                                        str(ROOT / "tools" / "generate_modeller_pdf.py"),
                                        "--model_dir", str(results_dir),
                                        "--out_pdf", str(pdf_file)
                                    ]
                                    proc = subprocess.run(pdf_cmd, capture_output=True, text=True)
                                
                                st.text(proc.stdout) # Show output for debugging

                                if proc.returncode == 0 and pdf_file.exists():
                                    st.success("PDF generated successfully.")
                                    st.session_state.modeller_pdf_path = str(pdf_file)
                                else:
                                    st.error("PDF generation failed.")
                                    st.text(proc.stderr) # Show stderr on failure

                            if st.session_state.modeller_pdf_path:
                                with open(st.session_state.modeller_pdf_path, "rb") as f:
                                    st.download_button(
                                        "Download Modeller PDF Report",
                                        f.read(),
                                        file_name="modeller_report.pdf",
                                        key="modeller_pdf_btn"
                                    )
                        else:
                            st.error("Modeller job failed.")

                if run_robetta:
                    st.header("Running Robetta...")
                    with st.spinner("Submitting Robetta job..."):
                        client = RobettaClient(username=robetta_user, password=robetta_pass)
                        # load cookies if you want to reuse prior session
                        client.load_cookies()
                        if not client.test_login():    # now works because alias exists
                            if not client.login():
                                st.error("Robetta login failed (check credentials or debug files).")
                                st.stop()

                        job_id = client.submit_job(sequence=clean_sequence(fasta_content), job_name=job_name,
                                                   rosettafold=True,
                                                   nstruct=1)
                        if job_id:
                            st.success(f"Submitted job, id={job_id}")
                        else:
                            st.error("Failed to submit Robetta job. Check debug_robetta/submit_response_*.html")

                os.unlink(tmp_fasta_path)

    # Robetta job management and generated models UI unchanged (kept from original app)
    with st.expander("Robetta Job Management"):
        if st.button("Refresh Robetta Job Queue"):
            with st.spinner("Fetching Robetta job queue…"):
                queue_cmd = [
                    "python",
                    str(ROOT / "scripts" / "run_robetta_job.py"),
                    "--username", robetta_user,
                    "--password", robetta_pass,
                    "queue",
                    "--json"
                ]

                proc = subprocess.run(queue_cmd, capture_output=True, text=True)

                raw_output = proc.stdout.strip()
                st.code(raw_output)

                try:
                    queue_data = json.loads(raw_output)
                    st.session_state.robetta_queue = queue_data
                    st.success("Job queue updated.")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("Robetta queue returned non-JSON output.")
                    st.stop()

        if "robetta_queue" in st.session_state and st.session_state.robetta_queue:
            st.subheader("Your Robetta Jobs")
            st.dataframe(st.session_state.robetta_queue)

            completed = [job for job in st.session_state.robetta_queue if job["status"].lower() == "complete"]

            if completed:
                job_labels = [f"{job['job_id']} — {job['target_name']}" for job in completed]
                selected = st.selectbox("Select completed job to download", job_labels)

                if st.button("Download Selected Job"):
                    job_id = selected.split("—")[0].strip()

                    # FIX: Ensure project_name is not empty and add debug info
                    proj_name = project_name.strip()
                    if not proj_name:
                        proj_name = "my_protein_project" # Fallback
                    
                    output_directory = ROOT / "results" / proj_name / "robetta_models"

                    download_cmd = [
                        "python", str(ROOT/"scripts"/"run_robetta_job.py"),
                        "--username", robetta_user,
                        "--password", robetta_pass,
                        "download",
                        "--job-id", job_id,
                        "--output-dir", str(output_directory)
                    ]

                    st.info(f"Running command: {' '.join(download_cmd)}")

                    with st.spinner(f"Downloading models for job {job_id}..."):
                        proc = subprocess.run(download_cmd, capture_output=True, text=True)
                    
                    st.success("Download process finished.")
                    
                    # Display logs in an expander
                    with st.expander("Show Download Logs"):
                        st.text(proc.stdout)
                        if proc.stderr:
                            st.text(proc.stderr)

                    # --- NEW: Parse the output for downloaded files ---
                    output = proc.stdout
                    match = re.search(r"###DOWNLOADED_FILES_JSON_START###\s*(.*?)\s*###DOWNLOADED_FILES_JSON_END###", output, re.DOTALL)
                    if match:
                        try:
                            downloaded_models = json.loads(match.group(1))
                            st.success(f"Successfully parsed {len(downloaded_models)} downloaded models.")
                            
                            if "generated_models" not in st.session_state:
                                st.session_state["generated_models"] = []

                            # Append new models, avoiding duplicates
                            existing_pdbs = [m["pdb_file"] for m in st.session_state["generated_models"]]
                            for model_info in downloaded_models:
                                if model_info["pdb_file"] not in existing_pdbs:
                                    st.session_state["generated_models"].append(model_info)
                            
                            st.info("Model list updated. Rerunning to refresh display.")
                            time.sleep(1) # Brief pause to let user see the message
                            st.rerun()

                        except json.JSONDecodeError as e:
                            st.error(f"Failed to parse the list of downloaded files from the script output: {e}")
                    else:
                        st.warning("Could not find the list of downloaded files in the script output. The model list will not be updated.")

    if "generated_models" in st.session_state and st.session_state["generated_models"]:
        st.header("Generated Models")
        
        # Create columns for layout
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Model Details")
            for idx, model_info in enumerate(st.session_state["generated_models"]):
                mp = Path(model_info["pdb_file"])
                st.write(f"**{model_info.get('model_name', mp.name)}**")
                
                confidence = model_info.get('confidence')
                if confidence:
                    st.write(f"Confidence: {confidence:.2f}")

                # Download button for the PDB
                with open(mp, "rb") as f:
                    st.download_button(f"Download {mp.name}", f.read(), file_name=mp.name, key=f"download_model_{idx}_{mp.name}")

                # Plot
                if model_info.get("plot_data_file"):
                    plot_data_file = Path(model_info["plot_data_file"])
                    if plot_data_file.exists():
                        with open(plot_data_file, "r") as f:
                            plot_data = json.load(f)
                        
                        fig, ax = plt.subplots()
                        ax.plot(plot_data["x"], plot_data["y"])
                        ax.set_xlabel("Position")
                        ax.set_ylabel("Angstrom Error Estimate")
                        ax.set_title(f"Error Estimate for {model_info.get('model_name', mp.name)}")
                        st.pyplot(fig)

        with col2:
            st.subheader("Select Model for Validation")
            model_options = [m["pdb_file"] for m in st.session_state["generated_models"]]
            selected_model = st.selectbox("Select a model for validation", options=model_options, format_func=lambda x: Path(x).name)
            if selected_model:
                st.session_state["selected_pdb"] = selected_model
                st.success(f"Selected {Path(selected_model).name} for validation.")

# Main action: validation pipeline
if run_validation_button:
    st.session_state['selected_validators'] = [v for v, selected in validators.items() if selected]
    
    # --- 1. Get the initial PDB file ---
    pdb_file_initial = None
    if "selected_pdb" in st.session_state and st.session_state['selected_pdb']:
        pdb_file_initial = st.session_state['selected_pdb']
        st.info(f"Using selected model for validation: {pdb_file_initial}")
    elif modeling_mode == "Use Existing PDB for Validation":
        if pdb_upload:
            pdb_file_initial = save_uploaded(pdb_upload)
        elif use_existing and pdb_path_input:
            pdb_file_initial = pdb_path_input.strip()
            if not os.path.exists(pdb_file_initial):
                st.error("Provided PDB path does not exist.")
                st.stop()
        else:
            st.error("Please upload a PDB or provide an existing path.")
            st.stop()

    if pdb_file_initial:
        # --- 2. Set up the new directory structure ---
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        model_name = Path(pdb_file_initial).stem
        job_name = f"{model_name}_{timestamp}"
        
        results_dir = ROOT / "results" / project_name / job_name
        if results_dir.exists():
            shutil.rmtree(results_dir)
        
        input_dir = results_dir / "input"
        fixed_dir = results_dir / "fixed"
        validation_dir = results_dir / "validation"
        
        input_dir.mkdir(parents=True, exist_ok=True)
        fixed_dir.mkdir(parents=True, exist_ok=True)
        validation_dir.mkdir(parents=True, exist_ok=True)

        st.session_state["results_dir"] = str(results_dir)

        # Copy original PDB to the 'input' directory
        shutil.copy(pdb_file_initial, input_dir / "original.pdb")
        pdb_for_validation = str(input_dir / "original.pdb")

        # --- 3. Run PDBFixer as a separate, initial step ---
        if validators.get("pdbfixer"):
            st.header("Running PDBFixer...")
            pdbfixer_out_dir = validation_dir / "pdbfixer"
            pdbfixer_out_dir.mkdir(exist_ok=True)
            
            rc, _ = run_wrapper(
                "validation_wrappers/pdbfixer_wrapper.py",
                pdb_for_validation,
                pdbfixer_out_dir
            )

            if rc == 0:
                st.success("PDBFixer finished.")
                # The fixed PDB is expected to be in the output dir with a specific name
                fixed_pdb_path = pdbfixer_out_dir / f"{Path(pdb_for_validation).stem}_fixed.pdb"
                if fixed_pdb_path.exists():
                    st.info(f"Using fixed PDB for subsequent validations: {fixed_pdb_path}")
                    # Copy to the 'fixed' directory for clarity
                    shutil.copy(fixed_pdb_path, fixed_dir / "fixed.pdb")
                    pdb_for_validation = str(fixed_pdb_path)
                else:
                    st.warning("PDBFixer ran, but the fixed PDB was not found. Continuing with the original PDB.")
            else:
                st.error("PDBFixer failed. Subsequent validations will use the original PDB.")
        
        # --- 4. Run the rest of the validators ---
        wrapper_order = [
            ("dssp", "validation_wrappers/dssp_wrapper.py"),
            ("freesasa", "validation_wrappers/freesasa_wrapper.py"),
            ("molprobity", "validation_wrappers/molprobity_wrapper.py"),
            ("prosa", "validation_wrappers/prosa_wrapper.py"),
            ("voromqa", "validation_wrappers/voromqa_wrapper.py"),
            ("qmean", "validation_wrappers/qmean_wrapper.py"),
            ("modeller", "validation_wrappers/modeller_wrapper.py"),
        ]

        st.info("Starting validation pipeline... output logs will stream below.")
        for key, script in wrapper_order:
            if not validators.get(key, False):
                st.text(f"Skipping {key}")
                continue
            
            outdir = validation_dir / key
            outdir.mkdir(parents=True, exist_ok=True)
            st.header(f"Running {key} ...")
            
            extra = []
            if key == "voromqa":
                if not voromqa_path_input or not Path(voromqa_path_input).is_file():
                    st.error("VoroMQA path is not a valid file. Please check the path in the sidebar.")
                    continue
                extra.extend(["--voromqa_path", voromqa_path_input])
            elif key == "qmean":
                if not qmean_email or not qmean_token:
                    st.error("QMEAN email and token are required.")
                    continue
                extra.extend(["--email", qmean_email, "--token", qmean_token])

            rc, full_output = run_wrapper(script, pdb_for_validation, outdir, extra_args=extra)
            
            if rc != 0:
                st.error(f"{key} failed (exit {rc}). Check wrapper logs.")
            else:
                st.success(f"{key} finished.")
                show_tool_outputs(outdir)
        
        st.success("Validation pipeline complete.")

else:
    st.info("Select a mode from the sidebar to begin.")
