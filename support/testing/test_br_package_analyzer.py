import unittest
import sys
import os
import json
import tempfile
import shutil
import re
from unittest.mock import patch
import fnmatch

# Add the repository root to sys.path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from toolbox.br_package_analyzer import get_toolchain_arch_info, get_dependencies_info

def fake_git_grep(sandbox_path, regex, path_pattern):
    """Simulate git grep by searching through the temporary sandbox directory."""
    results = []
    pattern = re.compile(regex)
    for root, dirs, files in os.walk(sandbox_path):
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, sandbox_path)
            
            # Filter on full path
            if not fnmatch.fnmatch(rel_path, path_pattern):
                continue
                
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if pattern.search(line):
                        results.append(f"{rel_path}:{line.strip()}")
    return results


class TestPackageAnalyzer(unittest.TestCase):
    
    def setUp(self):
        """Create a mini temporary Buildroot filesystem before each test."""
        self.sandbox = tempfile.mkdtemp()
        
        def create_file(path, content):
            full_path = os.path.join(self.sandbox, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        # 1. Reference package
        create_file("package/libglib2/Config.in", 
            "config BR2_PACKAGE_LIBGLIB2\n"
            "    depends on BR2_USE_WCHAR\n"
            "    depends on BR2_TOOLCHAIN_HAS_THREADS\n"
            "    depends on BR2_USE_MMU\n"
        )
        
        # 2. Package that correctly propagated its dependencies
        create_file("package/good_pkg/Config.in",
            "config BR2_PACKAGE_GOOD_PKG\n"
            "    depends on BR2_USE_WCHAR\n"
            "    depends on BR2_TOOLCHAIN_HAS_THREADS\n"
            "    select BR2_PACKAGE_LIBGLIB2\n"
        )
        
        # 3. Package that forgot its dependencies
        create_file("package/bad_pkg/Config.in",
            "config BR2_PACKAGE_BAD_PKG\n"
            "    select BR2_PACKAGE_LIBGLIB2\n"
        )
        
        # 4. Packages to test the Dependencies module
        create_file("package/my-pkg/Config.in",
            "config BR2_PACKAGE_MY_PKG\n"
            "    depends on BR2_PACKAGE_LIBBAR\n"
            "    select BR2_PACKAGE_LIBFOO\n"
        )
        create_file("package/my-pkg/my-pkg.mk", "MY_PKG_DEPENDENCIES = libbar libfoo\n")
        
        create_file("package/libfoo/Config.in",
            "config BR2_PACKAGE_LIBFOO\n"
            "    depends on BR2_TOOLCHAIN_HAS_THREADS\n"
            "    depends on BR2_USE_WCHAR\n"
        )
        
        # 5. Reverse dependencies
        create_file("package/other-pkg/Config.in",
            "config BR2_PACKAGE_OTHER_PKG\n"
            "    select BR2_PACKAGE_MY_PKG\n"
        )
        create_file("package/other-pkg/other-pkg.mk", "OTHER_PKG_DEPENDENCIES = host-pkgconf my-pkg\n")

    def tearDown(self):
        """Clean the temporary directory after the test."""
        shutil.rmtree(self.sandbox)

    @patch("toolbox.br_package_analyzer.run_git_grep", side_effect=fake_git_grep)
    def test_good_package_extraction(self, mock_grep):
        result = get_toolchain_arch_info(self.sandbox, "good_pkg")
        print("\n--- Output of get_toolchain_arch_info ---")
        import json
        print(json.dumps(result, indent=2))

        direct_deps = result["toolchain_and_arch_constraints"]
        self.assertIn("depends on BR2_USE_WCHAR", direct_deps)
        self.assertIn("depends on BR2_TOOLCHAIN_HAS_THREADS", direct_deps)
        
        # Note: the new script cleans the prefix and uppercases the name (LIBGLIB2)
        inherited_deps = result["inherited_toolchain_constraints"]
        self.assertIn("depends on BR2_USE_WCHAR (inherited from LIBGLIB2)", inherited_deps)
        self.assertIn("depends on BR2_TOOLCHAIN_HAS_THREADS (inherited from LIBGLIB2)", inherited_deps)

    @patch("toolbox.br_package_analyzer.run_git_grep", side_effect=fake_git_grep)
    def test_bad_package_deep_dependencies(self, mock_grep):
        result_glib = get_toolchain_arch_info(self.sandbox, "bad_pkg")
        
        self.assertEqual(len(result_glib["toolchain_and_arch_constraints"]), 0)
        
        inherited_glib = result_glib["inherited_toolchain_constraints"]
        self.assertIn("depends on BR2_USE_WCHAR (inherited from LIBGLIB2)", inherited_glib)
        self.assertIn("depends on BR2_USE_MMU (inherited from LIBGLIB2)", inherited_glib)

        result_foo = get_toolchain_arch_info(self.sandbox, "my-pkg")
        inherited_foo = result_foo["inherited_toolchain_constraints"]
        self.assertIn("depends on BR2_TOOLCHAIN_HAS_THREADS (inherited from LIBFOO)", inherited_foo)

    @patch("toolbox.br_package_analyzer.run_git_grep", side_effect=fake_git_grep)
    def test_get_dependencies_info(self, mock_grep):
        result = get_dependencies_info(self.sandbox, "my-pkg")
        print("\n--- Output of get_dependencies_info ---")
        import json
        print(json.dumps(result, indent=2))

        in_config = result["direct_dependencies"]["in_config_in"]
        self.assertIn("select BR2_PACKAGE_LIBFOO", in_config)
        self.assertIn("depends on BR2_PACKAGE_LIBBAR", in_config)
        
        in_makefile = result["direct_dependencies"]["in_makefile"]
        self.assertIn("MY_PKG_DEPENDENCIES = libbar libfoo", in_makefile)
        
        reverse_deps = result["reverse_dependencies"]
        self.assertIn("other-pkg", reverse_deps)
        self.assertNotIn("my-pkg", reverse_deps)


if __name__ == '__main__':
    unittest.main()
