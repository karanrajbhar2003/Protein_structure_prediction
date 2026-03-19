import os
import json
import re

BASE = "casp_data/CASP14"
native_dir = os.path.join(BASE, "native")
model_dir  = os.path.join(BASE, "models")
output_file = "training_pairs.json"

dataset = []

if not os.path.isdir(native_dir) or not os.path.isdir(model_dir):
    print(f"❌ Error: Base directories not found. Did you run the download script first?")
    print(f"  - Expected native dir: {os.path.abspath(native_dir)}")
    print(f"  - Expected model dir:  {os.path.abspath(model_dir)}")
    exit(1)

print("🔍 Scanning for native PDB files...")
native_pdbs = {}
for r_folder in os.listdir(native_dir):
    r_match = re.search(r"R(\d+)", r_folder)
    if not r_match:
        continue
    
    target_id_num = r_match.group(1) # This is the number, e.g., '1027'
    
    # CASP targets are T + number, e.g., T1027
    target_id_str = f"T{target_id_num}"

    r_folder_path = os.path.join(native_dir, r_folder)
    
    # Find the single PDB file in the R... directory
    found_pdb = False
    for f in os.listdir(r_folder_path):
        if f.endswith(".pdb"):
            native_pdbs[target_id_str] = os.path.join(r_folder_path, f)
            found_pdb = True
            break
    if not found_pdb:
        print(f"  - ⚠️ Warning: No .pdb file found in {r_folder_path}")


print(f"✅ Found {len(native_pdbs)} native PDBs.")
print("🔍 Matching models to natives...")

for target_id, native_pdb_path in native_pdbs.items():
    model_folder_path = os.path.join(model_dir, target_id)
    
    if not os.path.isdir(model_folder_path):
        continue

    models_found = 0
    for model_file in os.listdir(model_folder_path):
        if model_file.endswith(".pdb"):
            dataset.append({
                "target": target_id,
                "native_pdb": native_pdb_path,
                "model_pdb": os.path.join(model_folder_path, model_file)
            })
            models_found += 1
    
    if models_found > 0:
        print(f"  - Matched {models_found} models for target {target_id}")

with open(output_file, "w") as f:
    json.dump(dataset, f, indent=2)

print(f"\n✅ Generated {len(dataset)} model–native pairs in '{output_file}'")
