# Streamlit prototype — ProteinGuide

How to run:
1. Activate your Python environment (ensure dependencies from requirements.txt are installed).
2. From project root:
   ```
   streamlit run streamlit_app/app.py
   ```

Notes:
- The app calls local wrapper scripts in `validation_wrappers/`. Ensure those exist and are runnable.
- If you use WSL for binaries (voronota, phenix), either:
  - Add them to PATH in WSL and run Streamlit inside WSL (recommended), or
  - Use full WSL-style paths when providing `--voromqa_path`, e.g. `/mnt/e/...`
- To generate PDF, run the 'Generate PDF report' button after validators finish.