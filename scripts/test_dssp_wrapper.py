import os
import shutil
import subprocess
import unittest
from pathlib import Path

class TestDSSPWrapper(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_dssp_output")
        self.test_dir.mkdir(exist_ok=True)
        self.pdb_file = Path("data/2LZM.pdb")
        self.wrapper_script = Path("validation_wrappers/dssp_wrapper.py")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_dssp_wrapper(self):
        cmd = [
            "python",
            str(self.wrapper_script),
            "--pdb_file",
            str(self.pdb_file),
            "--output_dir",
            str(self.test_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0, f"DSSP wrapper failed with exit code {result.returncode}\n{result.stderr}")

        output_json = self.test_dir / "dssp_summary.json"
        self.assertTrue(output_json.exists(), "dssp_summary.json not found")
        
        output_png = self.test_dir / "dssp_secondary_structure.png"
        self.assertTrue(output_png.exists(), "dssp_secondary_structure.png not found")

if __name__ == "__main__":
    unittest.main()

