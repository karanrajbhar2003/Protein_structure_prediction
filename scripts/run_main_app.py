from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import subprocess
import os
import asyncio
import json
from typing import List

app = FastAPI()

# --- Models ---

class ModelingJob(BaseModel):
    jobName: str
    sequence: str
    runModeller: bool
    runRobetta: bool
    modellerNumModels: int
    projectName: str

class RobettaDownloadJob(BaseModel):
    jobId: str
    projectName: str

class ValidationJob(BaseModel):
    validators: List[str]
    pdbFile: str
    projectName: str
    
class PdfJob(BaseModel):
    jobName: str
    resultsDir: str

# --- Websocket log streaming ---

async def stream_process_logs(process, websocket: WebSocket):
    while True:
        output = await process.stdout.readline()
        if not output and process.poll() is not None:
            break
        if output:
            await websocket.send_text(output.decode().strip())
    
    while True:
        output = await process.stderr.readline()
        if not output and process.poll() is not None:
            break
        if output:
            await websocket.send_text(f"ERROR: {output.decode().strip()}")

    await process.wait()
    
# --- Websocket Endpoints ---

@app.websocket("/ws/run-modeling")
async def run_modeling_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            job = ModelingJob(**json.loads(data))

            if job.runModeller:
                results_dir = f"/app/results/{job.projectName}/model_generation_folder/modeller/{job.jobName}"
                os.makedirs(results_dir, exist_ok=True)
                
                args = [ "python", "/app/scripts/run_modeller_job.py", "--sequence", job.sequence,
                         "--job_name", job.jobName, "--results_dir", results_dir, "--num_models", str(job.modellerNumModels) ]
                
                process = await asyncio.create_subprocess_exec(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                await stream_process_logs(process, websocket)

            if job.runRobetta:
                await websocket.send_text("Robetta modeling is not fully implemented in the backend yet.")
            
            await websocket.send_text("--- JOB FINISHED ---")

    except WebSocketDisconnect:
        print("Client disconnected from modeling")

@app.websocket("/ws/run-validation")
async def run_validation_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            job = ValidationJob(**json.loads(data))
            
            # This is a simplified version of the complex validation pipeline from main.js
            # For a real implementation, more robust process handling is needed
            
            await websocket.send_text(f"Starting validation for {job.pdbFile}")
            
            for validator in job.validators:
                await websocket.send_text(f"--- Running {validator} ---")
                script = f"/app/validation_wrappers/{validator}_wrapper.py"
                out_dir = f"/app/results/{job.projectName}/validation/{job.pdbFile}/{validator}"
                os.makedirs(out_dir, exist_ok=True)
                
                args = ["python", script, "--pdb_file", f"/app/results/{job.pdbFile}", "--output_dir", out_dir]

                # This needs to be adapted for scripts with special args (qmean, voromqa)
                
                process = await asyncio.create_subprocess_exec(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                await stream_process_logs(process, websocket)

            await websocket.send_text("--- VALIDATION FINISHED ---")

    except WebSocketDisconnect:
        print("Client disconnected from validation")
        
# --- HTTP Endpoints ---

@app.get("/robetta-queue")
async def get_robetta_queue():
    # Needs credentials
    return {"error": "Not implemented"}

@app.post("/download-robetta-job")
async def download_robetta_job(job: RobettaDownloadJob):
    # Needs credentials
    return {"error": "Not implemented"}
    
@app.post("/generate-pdf-report")
async def generate_pdf_report(job: PdfJob):
    pdf_out = f"/app/results/{job.resultsDir}/{job.jobName}_validation_report.pdf"
    args = ["python", "/app/tools/generate_validation_pdf.py", "--model_dir", f"/app/results/{job.resultsDir}", "--out_pdf", pdf_out]
    
    process = await asyncio.create_subprocess_exec(*args)
    retcode = await process.wait()
    
    if retcode == 0:
        return {"status": "success", "pdf_path": pdf_out}
    else:
        return {"status": "error"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
