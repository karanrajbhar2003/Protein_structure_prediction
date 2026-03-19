# ProSutra - Protein Modeling and Validation Pipeline

ProSutra provides a protein structure workflow with modeling, validation, and report generation utilities.  
You can run it as a CLI pipeline, Streamlit app, or Electron desktop app.

## Achievements

1. **Aavishkar Research Convention (University of Mumbai, 2025-26)**  
   ProSutra was presented at the 20th Aavishkar Inter-Collegiate/Institute/Department Research Convention (Zonal Round) hosted at D.G. Ruparel College, Mumbai, under the Pure Sciences category (Postgraduate level). The project advanced to the podium round from Zone I (Mumbai I).
2. **SRIJNA National Level Poster Competition**  
   ProSutra was presented at SRIJNA (GNIRD, Guru Nanak Khalsa College, Matunga, Mumbai) and received **Second Place** for research relevance, technical innovation, and presentation clarity.

## Thesis

The thesis copy is available in this repository at:

`Thesis/ProSutra_Thesis.pdf`

## User Installation Guide

### 1. Prerequisites

Install these first:

1. Python 3.10+ (3.11/3.12 recommended)
2. `pip`
3. Git
4. Optional for desktop app: Node.js 18+ and npm
5. External tools you plan to use:
   - Modeller
   - DSSP (`mkdssp`)
   - FreeSASA
   - VoroMQA (`voronota-voromqa`)
   - MolProbity / Phenix (if used in your flow)

### 2. Clone the project

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### 3. Create virtual environment and install Python dependencies

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create local config files

Windows PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item scripts/config.json.template scripts/config.json
Copy-Item streamlit_app/config.example.json streamlit_app/config.json
```

Linux/macOS:

```bash
cp .env.example .env
cp scripts/config.json.template scripts/config.json
cp streamlit_app/config.example.json streamlit_app/config.json
```

### 5. Fill credentials and tool paths

Update these local files:

1. `.env`
2. `scripts/config.json`
3. `streamlit_app/config.json`

Set:

1. Robetta username/password
2. QMEAN email/token
3. Paths to installed binaries (`voromqa_path`, `dssp_path`, `freesasa_path`, `phenix_path` if needed)

## Run ProSutra

### CLI pipeline (`scripts/main.py`)

Modeling:

```bash
python scripts/main.py model --sequence "YOUR_SEQUENCE_HERE" --job-name "my_protein" --modeller --robetta
```

Validation:

```bash
python scripts/main.py validate --pdb-file "/path/to/your/model.pdb" --project-name "validation_project"
```

Reporting:

```bash
python scripts/main.py report --model-dir "/path/to/your/results/validation_project/model_20260105_123456" --out-pdf "report.pdf"
```

### Streamlit app

```bash
streamlit run streamlit_app/app.py
```

### Electron app (optional)

```bash
cd electron-app
npm install
npm start
```

## GitHub-Ready Setup

Before committing:

1. Keep local secrets in ignored files only:
   - `streamlit_app/config.json` (copy from `streamlit_app/config.example.json`)
   - `scripts/config.json` (copy from `scripts/config.json.template`)
   - `.env` (copy from `.env.example`)
2. Do not commit cookie/session files (`cookies.json`, `electron-app/cookies.json`)
3. Keep local heavy tool folders out of git (`Modeller10.7/`, `VoroMQA/`, output folders)

## Upload To GitHub (First Time)

Run from project root:

```bash
git init
git branch -M main
git add .
git status
git commit -m "Initial commit: ProSutra pipeline"
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```
