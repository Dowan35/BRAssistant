import unittest
import os
import tempfile
import sys
import shutil
from pathlib import Path

# Add the repository root to sys.path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from toolbox.br_license_inspector import scan_license_files, scan_source_for_spdx

"""
Test suite for br_license_inspector.py.
Run: python3 -m unittest test_br_license_inspector.py
"""

class TestLicenseInspector(unittest.TestCase):
    
    def setUp(self):
        """Create a fake source directory before each test."""
        self.test_dir = tempfile.mkdtemp()
        
        # 1. Create license files at the repository root
        Path(os.path.join(self.test_dir, "COPYING")).touch()
        Path(os.path.join(self.test_dir, "README.md")).touch()
        
        # 2. Create a subfolder with source code containing SPDX tags
        src_dir = os.path.join(self.test_dir, "src")
        os.makedirs(src_dir)
        
        with open(os.path.join(src_dir, "main.c"), "w") as f:
            f.write("// SPDX-License-Identifier: GPL-2.0-or-later\n")
            f.write("int main() { return 0; }\n")
            
        with open(os.path.join(src_dir, "gui.c"), "w") as f:
            f.write("// SPDX-License-Identifier: MIT\n")
            f.write("void draw() {}\n")

    def tearDown(self):
        """Clean up the fake directory after the test."""
        shutil.rmtree(self.test_dir)

    def test_scan_license_files(self):
        """Verify the tool finds COPYING and README files."""
        found_files = scan_license_files(self.test_dir)
        
        self.assertIn("COPYING", found_files)
        self.assertIn("README.md", found_files)
        self.assertEqual(len(found_files), 2)
        print("\n--- Output of scan_license_files ---")
        print(found_files)

    def test_scan_source_for_spdx(self):
        """Verify the tool extracts SPDX tags from subfolders."""
        # Simulate the official SPDX database with the expected licenses
        fake_spdx_db = {"GPL-2.0-or-later", "MIT", "Apache-2.0"}
        
        validated, unrecognized = scan_source_for_spdx(self.test_dir, fake_spdx_db)
        
        # L'outil doit avoir trouvé les deux licences du code source
        self.assertIn("GPL-2.0-or-later", validated)
        self.assertIn("MIT", validated)
        self.assertEqual(len(unrecognized), 0)
        print("\n--- Output of scan_source_for_spdx ---")
        print(validated)
        print(unrecognized)

if __name__ == '__main__':
    from pathlib import Path # Needed for the setup
    unittest.main()
