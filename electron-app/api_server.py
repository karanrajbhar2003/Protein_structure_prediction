import matplotlib
matplotlib.use('Agg')
from typing import List, Dict
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import re
import os
import shutil
from fastapi.middleware.cors import CORSMiddleware

# Add project root to Python path to allow importing from src, scripts, etc.
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "src"))

from robetta_client import RobettaClient

PROJECTS_ROOT = Path(__file__).resolve().parent / "results"

# --- Configuration ---
CONFIG_FILE = ROOT / "streamlit_app" / "config.json"
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Pydantic Models ---
class AppSettings(BaseModel):
    robetta_user: str = ""
    robetta_pass: str = ""
    qmean_email: str = ""
    qmean_token: str = ""
    voromqa_path: str = ""
    dssp_path: str = ""
    freesasa_path: str = ""
    phenix_path: str = ""

class ModellingRequest(BaseModel):
    job_name: str
    fasta_content: str
    run_modeller: bool
    run_robetta: bool
    modeller_num_models: int = 5
    project_name: str = "my_protein_project"

# --- Helper Functions ---
def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(config_dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config_dict, indent=2))

def clean_sequence(raw: str):
    lines = raw.splitlines()
    seq = ''.join([l.strip() for l in lines if not l.startswith(">")])
    return re.sub(r'[^ACDEFGHIKLMNPQRSTVWY]', '', seq.upper())

JSON_START = "###MODELLER_JSON_START###"
JSON_END = "###MODELLER_JSON_END###"
def extract_embedded_json(text: str):
    m = re.search(re.escape(JSON_START) + r"(.*?)" + re.escape(JSON_END), text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def build_wrapper_env() -> dict:
    """
    Ensure wrapper subprocesses run with the same interpreter context as this API
    and can resolve executables like mkdssp from the env's Scripts/bin folders.
    """
    env = os.environ.copy()
    path_parts = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
    py_dir = str(Path(sys.executable).resolve().parent)
    candidates = [py_dir]

    # Windows venv/conda
    candidates.append(str(Path(py_dir) / "Scripts"))
    # Conda packages often place executables here (e.g., mkdssp.exe)
    candidates.append(str(Path(py_dir) / "Library" / "bin"))
    # Unix-like venv/conda
    candidates.append(str(Path(py_dir) / "bin"))

    for part in candidates:
        if part and part not in path_parts and Path(part).exists():
            path_parts.insert(0, part)
    env["PATH"] = os.pathsep.join(path_parts)
    return env

# --- API Endpoints ---
@app.get("/")
async def read_root():
    return {"message": "ProSutra API is running"}



# -----------------
# Project Management
# -----------------
class Project(BaseModel):
    name: str

PROJECTS_ROOT = Path(__file__).resolve().parent / "results"

@app.get("/api/projects")
async def get_projects():
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_ROOT.exists():
        return []
    return [d.name for d in PROJECTS_ROOT.iterdir() if d.is_dir()]

@app.post("/api/projects")
async def create_project(project: Project):
    project_dir = PROJECTS_ROOT / project.name
    if project_dir.exists():
        raise HTTPException(status_code=400, detail=f"Project '{project.name}' already exists.")
    
    try:
        # Create the structured directory
        (project_dir / "models" / "modeller").mkdir(parents=True, exist_ok=True)
        (project_dir / "models" / "robetta").mkdir(parents=True, exist_ok=True)
        (project_dir / "validation_reports").mkdir(parents=True, exist_ok=True)
        (project_dir / "pdf report").mkdir(parents=True, exist_ok=True)

        # Verify that the directory was created
        if not project_dir.is_dir():
            raise IOError("Failed to create project directory on the filesystem.")

    except Exception as e:
        # Catch any exception during directory creation and raise an HTTP error
        raise HTTPException(status_code=500, detail=f"Server error creating project directory: {e}")
    
    return {"message": f"Project '{project.name}' created successfully.", "project_dir": str(project_dir)}

@app.delete("/api/projects/{project_name}")
async def delete_project(project_name: str):
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found.")
    try:
        shutil.rmtree(project_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project '{project_name}': {e}")
    return {"message": f"Project '{project_name}' deleted successfully."}

@app.get("/api/projects/{project_name}/models")
async def get_project_models(project_name: str):
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found.")
    
    modeller_models_dir = project_dir / "models" / "modeller"
    robetta_models_dir = project_dir / "models" / "robetta"
    
    models = []
    if modeller_models_dir.exists():
        models.extend([f.name for f in modeller_models_dir.rglob("*.pdb")])
    if robetta_models_dir.exists():
        models.extend([f.name for f in robetta_models_dir.rglob("*.pdb")])
        
    return models


@app.get("/api/projects/{project_name}")
async def get_project_details(project_name: str):
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found.")

    def get_files(subdir, pattern="*"):
        path = project_dir / subdir
        if not path.is_dir():
            return []
        return [{"name": f.name, "path": str(f)} for f in path.rglob(pattern)]

    details = {
        "name": project_name,
        "modeller_models": get_files("models/modeller", "*.pdb"),
        "robetta_models": get_files("models/robetta", "*.pdb"),
        "validation_reports": get_files("validation_reports"),
        "pdf_reports": get_files("pdf report", "*.pdf"),
    }
    return details

# -----------------
# Settings
# -----------------
@app.get("/api/settings", response_model=AppSettings)
async def get_settings():
    config = load_config()
    defaults = AppSettings()
    return defaults.copy(update=config)

@app.post("/api/settings")
async def post_settings(settings: AppSettings):
    save_config(settings.dict())
    return {"message": "Settings saved successfully."}

# -----------------
# Modeling
# -----------------
async def run_modelling_stream(request: ModellingRequest):
    if not request.fasta_content:
        yield "data: " + json.dumps({"error": "FASTA content is required."}) + "\n\n"
        return

    # Use a temporary file for the FASTA sequence
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".fasta", dir=ROOT / "streamlit_workspace") as tmp_fasta:
        tmp_fasta.write(request.fasta_content)
        tmp_fasta_path = tmp_fasta.name

    try:
        if request.run_robetta:
            try:
                config = load_config()
                client = RobettaClient(username=config.get("robetta_user"), password=config.get("robetta_pass"))
                if not client.login():
                    raise HTTPException(status_code=401, detail="Robetta login failed. Check credentials.")

                seq = clean_sequence(request.fasta_content)
                # First try RoseTTAFold submission.
                job_id = client.submit_job(
                    sequence=seq,
                    job_name=request.job_name,
                    rosettafold=True,
                    cm=False,
                    ab=False
                )
                
                if job_id:
                    yield "data: " + json.dumps({
                        "event": "finish",
                        "tool": "robetta",
                        "status": "success",
                        "job_id": job_id,
                        "method": "rosettafold"
                    }) + "\n\n"
                else:
                    primary_error = client.last_error or "Failed to submit Robetta job with RoseTTAFold."
                    low_err = primary_error.lower()
                    should_try_ab = any(token in low_err for token in [
                        "maintenance",
                        "unavailable",
                        "can't submit",
                        "cannot submit"
                    ])

                    if should_try_ab:
                        job_id_ab = client.submit_job(
                            sequence=seq,
                            job_name=request.job_name,
                            rosettafold=False,
                            cm=False,
                            ab=True
                        )
                        if job_id_ab:
                            yield "data: " + json.dumps({
                                "event": "finish",
                                "tool": "robetta",
                                "status": "success",
                                "job_id": job_id_ab,
                                "method": "ab",
                                "note": f"RoseTTAFold submit failed, fallback to AB succeeded: {primary_error}"
                            }) + "\n\n"
                        else:
                            ab_error = client.last_error or "Failed to submit Robetta job with AB fallback."
                            detail = f"RoseTTAFold failed: {primary_error} | AB fallback failed: {ab_error}"
                            yield "data: " + json.dumps({"event": "error", "tool": "robetta", "detail": detail}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({"event": "error", "tool": "robetta", "detail": primary_error}) + "\n\n"
            except Exception as e:
                 yield "data: " + json.dumps({"event": "error", "tool": "robetta", "detail": str(e)}) + "\n\n"

        if request.run_modeller:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            modeller_out_dir = PROJECTS_ROOT / request.project_name / "models" / "modeller" / f"{request.job_name}_{timestamp}"
            modeller_out_dir.mkdir(parents=True, exist_ok=True)
            seq = clean_sequence(request.fasta_content)
            cmd = [
                sys.executable,  # Use the same python interpreter that runs the server
                str(ROOT / "scripts" / "run_modeller_job.py"),
                "--sequence", seq,
                "--job_name", request.job_name,
                "--results_dir", str(modeller_out_dir),
                "--num_models", str(request.modeller_num_models)
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            full_stdout = ""
            # Read stdout line by line
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                full_stdout += line_str + "\n"
                if "###MODELLER_PROGRESS###" in line_str:
                    progress_match = re.search(r"(\d+)%", line_str)
                    if progress_match:
                        progress = int(progress_match.group(1))
                        yield "data: " + json.dumps({"event": "progress", "tool": "modeller", "progress": progress, "log": line_str}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({"event": "progress", "tool": "modeller", "log": line_str}) + "\n\n"
            
            stderr = await proc.stderr.read()
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            if proc.returncode != 0:
                yield "data: " + json.dumps({"event": "error", "tool": "modeller", "log": full_stdout + stderr_str}) + "\n\n"
            else:
                summary = extract_embedded_json(full_stdout)
                yield "data: " + json.dumps({
                    "event": "finish", 
                    "tool": "modeller", 
                    "status": "success", 
                    "summary": summary, 
                    "output_dir": str(modeller_out_dir), 
                    "log": full_stdout
                }) + "\n\n"

    finally:
        os.unlink(tmp_fasta_path)

@app.post("/api/run-modelling")
async def run_modelling(request: ModellingRequest):
    return StreamingResponse(run_modelling_stream(request), media_type="text/event-stream")

# -----------------
# Robetta
# -----------------
@app.get("/api/robetta/queue")
async def get_robetta_queue():
    config = load_config()
    client = RobettaClient(username=config.get("robetta_user"), password=config.get("robetta_pass"))
    if not client.login():
        raise HTTPException(status_code=401, detail="Robetta login failed. Check credentials.")
    
    queue = client.get_job_queue()
    return queue

class RobettaDownloadRequest(BaseModel):
    job_id: str
    project_name: str

@app.post("/api/robetta/download")
async def download_robetta_job(request: RobettaDownloadRequest):
    config = load_config()
    client = RobettaClient(username=config.get("robetta_user"), password=config.get("robetta_pass"))
    if not client.login():
        raise HTTPException(status_code=401, detail="Robetta login failed. Check credentials.")

    # 1. Find the job in the queue to get the results page URL
    queue = client.get_job_queue()
    job_info = next((job for job in queue if job['job_id'] == request.job_id), None)

    if not job_info or 'results_link' not in job_info:
        raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found in Robetta queue or has no results link.")

    # 2. Get the specific download links from the results page
    results_data = client.get_job_results(job_info['results_link'])
    pdb_links = results_data.get("pdb_links")

    if not pdb_links:
        raise HTTPException(status_code=404, detail=f"No PDB download links found for job {request.job_id}.")

    # 3. Download the files
    project_dir = PROJECTS_ROOT / request.project_name
    download_dir = project_dir / "models" / "robetta"
    download_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    for link in pdb_links:
        # derive a filename from the URL
        filename = link.split("/")[-1].split("?")[0]
        if not filename.endswith(('.pdb', '.zip', '.tgz')):
            # handle cases like model_download.php?id=...
            # create a more descriptive name
            job_id_match = re.search(r'id=(\d+)', link)
            model_match = re.search(r'model=(\d+)', link)
            job_id_str = job_id_match.group(1) if job_id_match else request.job_id
            model_str = f"_model_{model_match.group(1)}" if model_match else ""
            filename = f"robetta_{job_id_str}{model_str}.pdb"

        save_path = download_dir / filename
        if client.download_file(link, str(save_path)):
            downloaded_files.append(str(save_path))

    if downloaded_files:
        return {"status": "success", "message": f"Successfully downloaded {len(downloaded_files)} file(s) for job {request.job_id}.", "files": downloaded_files}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to download any files for job {request.job_id}.")





from fastapi.responses import StreamingResponse
import asyncio

class ValidationRequest(BaseModel):
    pdb_model_names: List[str]
    project_name: str
    validators: dict[str, bool]
    is_external_file: bool = False

def get_tool_images_base64(tool_dir: Path) -> Dict[str, str]:
    images = {}
    # Prioritize SVG
    svg_files = {p.stem: p for p in tool_dir.glob("*.svg")}
    png_files = {p.stem: p for p in tool_dir.glob("*.png")}

    for name, path in svg_files.items():
        try:
            content = path.read_bytes()
            encoded = base64.b64encode(content).decode("utf-8")
            images[path.name] = f"data:image/svg+xml;base64,{encoded}"
        except Exception as e:
            print(f"Error encoding image {path}: {e}")

    for name, path in png_files.items():
        if name not in svg_files: # Only add PNG if no SVG with the same name exists
            try:
                content = path.read_bytes()
                encoded = base64.b64encode(content).decode("utf-8")
                images[path.name] = f"data:image/png;base64,{encoded}"
            except Exception as e:
                print(f"Error encoding image {path}: {e}")
    return images

async def run_validation_stream(request: ValidationRequest):
    wrapper_env = build_wrapper_env()

    for model_name_or_path in request.pdb_model_names:
        pdb_file_initial = None
        if request.is_external_file:
            pdb_file_initial = Path(model_name_or_path)
        else:
            project_dir = PROJECTS_ROOT / request.project_name
            model_dirs_to_check = [project_dir / "models" / "modeller", project_dir / "models" / "robetta"]
            for models_dir in model_dirs_to_check:
                found_files = list(models_dir.rglob(model_name_or_path))
                if found_files:
                    pdb_file_initial = found_files[0]
                    break
        
        if not pdb_file_initial or not pdb_file_initial.exists():
            yield "data: " + json.dumps({"error": f"PDB file '{model_name_or_path}' not found."}) + "\n\n"
            continue

        model_name = pdb_file_initial.stem
        
        results_dir = PROJECTS_ROOT / request.project_name / "validation_reports" / model_name
        # Avoid stale tool outputs from previous runs for the same model.
        if results_dir.exists():
            shutil.rmtree(results_dir)
        validation_dir = results_dir / "validation"
        validation_dir.mkdir(parents=True, exist_ok=True)
        
        shutil.copy(pdb_file_initial, results_dir / "original.pdb")
        current_pdb_path = str(results_dir / "original.pdb")

        yield "data: " + json.dumps({"event": "start_model", "model_name": model_name_or_path, "results_dir": str(results_dir)}) + "\n\n"

        wrapper_order = [
            ("pdbfixer", "validation_wrappers/pdbfixer_wrapper.py"),
            ("dssp", "validation_wrappers/dssp_wrapper.py"),
            ("freesasa", "validation_wrappers/freesasa_wrapper.py"),
            ("molprobity", "validation_wrappers/molprobity_wrapper.py"),
            ("prosa", "validation_wrappers/prosa_wrapper.py"),
            ("voromqa", "validation_wrappers/voromqa_wrapper.py"),
            ("qmean", "validation_wrappers/qmean_wrapper.py"),
            ("modeller", "validation_wrappers/modeller_wrapper.py"),
        ]
        config = load_config()
        pdbfixer_fallback_to_original = False
        pdbfixer_fallback_note = ""

        for key, script in wrapper_order:
            if not request.validators.get(key):
                continue

            yield "data: " + json.dumps({"event": "start_tool", "tool": key, "model_name": model_name_or_path}) + "\n\n"
            
            outdir = validation_dir / key
            outdir.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(ROOT / script), "--pdb_file", current_pdb_path, "--output_dir", str(outdir)]
            
            extra_args = []
            if key == "qmean":
                qmean_email = config.get("qmean_email")
                qmean_token = config.get("qmean_token")
                if not qmean_email or not qmean_token:
                    yield "data: " + json.dumps({
                        "event": "finish_tool",
                        "tool": key,
                        "model_name": model_name_or_path,
                        "status": "error",
                        "summary": {},
                        "images": {},
                        "log": "QMEAN email or token not configured."
                    }) + "\n\n"
                    continue
                extra_args.extend(["--email", qmean_email, "--token", qmean_token])
            
            if key == "voromqa":
                voromqa_path = config.get("voromqa_path")
                if not voromqa_path or not Path(voromqa_path).exists():
                    yield "data: " + json.dumps({
                        "event": "finish_tool",
                        "tool": key,
                        "model_name": model_name_or_path,
                        "status": "error",
                        "summary": {},
                        "images": {},
                        "log": f"VoroMQA path not configured or invalid: {voromqa_path}"
                    }) + "\n\n"
                    continue
                extra_args.extend(["--voromqa_path", voromqa_path])

            if key == "dssp":
                dssp_path = config.get("dssp_path")
                if dssp_path and dssp_path != "PATH_TO_YOUR_MKDSSP_EXECUTABLE":
                    extra_args.extend(["--dssp_path", dssp_path])
            
            if key == "freesasa":
                freesasa_path = config.get("freesasa_path")
                if freesasa_path and freesasa_path != "PATH_TO_YOUR_FREESASA_EXECUTABLE":
                    extra_args.extend(["--freesasa_path", freesasa_path])

            if key == "molprobity":
                phenix_path = config.get("phenix_path")
                if phenix_path:
                    extra_args.extend(["--phenix_path", phenix_path])
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                *extra_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=wrapper_env
            )
            stdout, stderr = await proc.communicate()
            
            status = "success" if proc.returncode == 0 else "error"
            summary = {}
            summary_path = outdir / f"{key}_summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text())
                except: pass

            log_output = stdout.decode() + stderr.decode()

            if key != "pdbfixer" and pdbfixer_fallback_to_original and pdbfixer_fallback_note:
                log_output = f"[PDBFixer] Warning: {pdbfixer_fallback_note}\n{log_output}"

            if key == "pdbfixer":
                if status == "success":
                    fixed_candidates = []

                    summary_fixed = summary.get("fixed_pdb")
                    if summary_fixed:
                        fixed_candidates.append(Path(summary_fixed))

                    expected_fixed = outdir / f"{Path(current_pdb_path).stem}_fixed.pdb"
                    fixed_candidates.append(expected_fixed)
                    fixed_candidates.extend(sorted(outdir.glob("*_fixed.pdb")))

                    resolved_fixed = next((p for p in fixed_candidates if p and p.exists()), None)
                    if resolved_fixed:
                        current_pdb_path = str(resolved_fixed.resolve())
                        log_output += f"\n[PDBFixer] Using fixed PDB for downstream validators: {current_pdb_path}\n"
                    else:
                        status = "error"
                        log_output += (
                            f"\n[PDBFixer] Error: Expected fixed PDB was not created in {outdir}. "
                            "Remaining validators will run on the original PDB.\n"
                        )
                else:
                    log_output += "\n[PDBFixer] Error: PDBFixer failed. Remaining validators will run on the original PDB.\n"
            
            result = {
                "event": "finish_tool",
                "tool": key,
                "model_name": model_name_or_path,
                "status": status,
                "summary": summary,
                "images": get_tool_images_base64(outdir),
                "log": log_output
            }
            yield "data: " + json.dumps(result) + "\n\n"

            if key == "pdbfixer" and status != "success":
                pdbfixer_fallback_to_original = True
                pdbfixer_fallback_note = (
                    "PDBFixer did not produce a usable fixed PDB. "
                    "Validating with the original PDB file."
                )
                yield "data: " + json.dumps({
                    "event": "error",
                    "tool": "pdbfixer",
                    "model_name": model_name_or_path,
                    "detail": pdbfixer_fallback_note
                }) + "\n\n"

        yield "data: " + json.dumps({"event": "finish_model", "model_name": model_name_or_path}) + "\n\n"

@app.post("/api/run-validation")
async def run_validation(request: ValidationRequest):
    return StreamingResponse(run_validation_stream(request), media_type="application/x-ndjson")


import base64

class ConsolidatedReportRequest(BaseModel):
    results_dirs: List[str]
    project_name: str | None = None

# ... (existing code)

# -----------------
# Reporting
# -----------------
@app.post("/api/generate-report")
async def generate_report(request: ConsolidatedReportRequest):
    if not request.results_dirs:
        raise HTTPException(status_code=400, detail="No result directories provided.")

    script_path = ROOT / "tools" / "generate_consolidated_report.py"

    save_in_project = bool(request.project_name)
    if save_in_project:
        pdf_dir = PROJECTS_ROOT / request.project_name / "pdf report"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        pdf_out_path = str(pdf_dir / f"validation_report_{timestamp}.pdf")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            pdf_out_path = tmp_pdf.name

    try:
        wrapper_env = build_wrapper_env()
        cmd = [
            sys.executable,
            str(script_path), 
            "--results_dirs", ",".join(request.results_dirs), 
            "--out_pdf", pdf_out_path
        ]
        
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=wrapper_env)

        if proc.returncode == 0 and Path(pdf_out_path).exists():
            if save_in_project:
                return {"status": "success", "pdf_path": pdf_out_path}
            pdf_content = Path(pdf_out_path).read_bytes()
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            return {"status": "success", "pdf_data": pdf_base64}
        else:
            error_detail = f"PDF generation failed. Return code: {proc.returncode}\nStdout: {proc.stdout}\nStderr: {proc.stderr}"
            raise HTTPException(status_code=500, detail=error_detail)
    finally:
        # Clean up only temporary PDF outputs (project-saved reports are persistent).
        if (not save_in_project) and Path(pdf_out_path).exists():
            os.remove(pdf_out_path)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091)
