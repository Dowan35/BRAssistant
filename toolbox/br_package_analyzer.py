#!/usr/bin/env python3
# br_package_analyzer.py
# Usage: python3 br_package_analyzer.py <action> <sandbox_path> <package_name>
# Actions: 'deps' or 'toolchain'

import os
import sys
import re
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sandbox.sandbox_git_tool import run_command

def run_git_grep(sandbox_path, pattern, file_pattern):
    """Launch git grep with regex pattern and file pattern, return the matching lines."""
    cmd = ["git", "grep", "-E", pattern, "--", file_pattern]
    result = run_command(sandbox_path, cmd)

    if result["status"] == "success":
        lines = result["output"].splitlines()
        return [line for line in lines if line.strip() and not line.startswith("... [TRUNCATED")]
    return []

def get_dependencies_info(sandbox_path, pkg_name):
    """Extract forward and reverse dependencies to check for missing/circular deps."""
    pkg_upper = pkg_name.upper().replace('-', '_')
    pkg_kconfig = f"BR2_PACKAGE_{pkg_upper}"
    
    # --- 1. FORWARD DEPENDENCIES (What this package needs) ---
    # Kconfig (Config.in)
    fwd_kconfig_lines = run_git_grep(sandbox_path, r"^\s*(select|depends on)\s+(BR2_PACKAGE_[A-Za-z0-9_!]+)", f"package/{pkg_name}/Config.in")

    fwd_kconfig = []
    selected_packages = []
    
    for line in fwd_kconfig_lines:
        clean_line = line.split(':')[-1].strip()
        fwd_kconfig.append(clean_line)
        
        # Look for the dependencies of the selected/needed packages
        match = re.search(r"select\s+BR2_PACKAGE_([A-Z0-9_]+)", clean_line)
        if match:
            selected_packages.append(match.group(1).lower().replace('_', '-'))

    # Makefile (*.mk)
    fwd_mk_lines = run_git_grep(sandbox_path, f"^{pkg_upper}_DEPENDENCIES\\s*\\+?=", f"package/{pkg_name}/*.mk")
    fwd_mk = [line.split(':')[-1].strip() for line in fwd_mk_lines]

    # --- 2. REVERSE DEPENDENCIES (Who needs this package) ---
    rev_kconfig_lines = run_git_grep(sandbox_path, rf"^\s*(select|depends on)\s+{pkg_kconfig}\\b", "*/Config.in")
    rev_mk_lines = run_git_grep(sandbox_path, f"^[A-Z0-9_]+_DEPENDENCIES\\s*\\+?=[^\n]*\\b{pkg_name}\\b", "*/*.mk")
    
    rdepends = set()
    for line in rev_kconfig_lines + rev_mk_lines:
        parts = line.split('/')
        if len(parts) >= 2 and parts[0] in ["package", "boot", "toolchain"]:
            rdepends.add(parts[1])
            
    if pkg_name in rdepends:
        rdepends.remove(pkg_name)

    return {
        "package": pkg_name,
        "direct_dependencies": {
            "in_config_in": sorted(list(set(fwd_kconfig))),
            "in_makefile": sorted(list(set(fwd_mk)))
        },
        "reverse_dependencies": sorted(list(rdepends))
    }

def get_toolchain_arch_info(sandbox_path, pkg_name):
    """Extract toolchain and architecture constraints (direct and inherited), avoiding comments and duplicates."""
    
    def parse_config_block(filepath, target_config):
        """Reads a Config.in file and extracts 'depends on' ONLY for the specified config block."""
        deps = []
        selected = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                in_target_block = False
                for line in f:
                    line = line.strip()
                    
                    if line == f"config {target_config}":
                        in_target_block = True
                        continue
                        
                    if in_target_block:
                        # Stop reading as soon as we exit the package block (new config, comment, menu, etc.)
                        if line.startswith("config ") or line.startswith("menu ") or line.startswith("comment ") or line.startswith("if ") or line.startswith("source "):
                            break
                            
                        # Extract toolchain/arch constraints
                        if line.startswith("depends on "):
                            match = re.search(r"depends on\s+(!?BR2_(TOOLCHAIN|USE|INSTALL|ARCH|STATIC_LIBS|LINUX_KERNEL)[A-Z0-9_]*|!?BR2_[A-Z0-9_]+_ARCH_SUPPORTS)", line)
                            if match:
                                deps.append(match.group(1))
                                
                        # Extract selected packages
                        if line.startswith("select "):
                            match = re.search(r"select\s+(BR2_PACKAGE_[A-Z0-9_]+)", line)
                            if match:
                                selected.append(match.group(1))
        except Exception as e:
            pass
        return deps, selected

    pkg_upper = pkg_name.upper().replace('-', '_')
    main_config_var = f"BR2_PACKAGE_{pkg_upper}"
    main_config_path = os.path.join(sandbox_path, f"package/{pkg_name}/Config.in")
    
    # 1. Package direct constraints (block-wise reading instead of grep to avoid contradictions)
    direct_deps, selected_configs = parse_config_block(main_config_path, main_config_var)
    constraints = [f"depends on {d}" for d in direct_deps]

    # 2. Inherited constraints with grouping (deduplication)
    inherited_dict = {} # Ex: {"BR2_USE_WCHAR": ["BOOST", "ELFUTILS"]}
    
    for config_var in selected_configs:
        files = run_git_grep(sandbox_path, f"^config {config_var}$", "package/*/Config.in")
        if not files:
            continue
            
        filepath = os.path.join(sandbox_path, files[0].split(':')[0])
        inherited_deps, _ = parse_config_block(filepath, config_var)
        
        # Clean the package name for a more readable display (e.g., BR2_PACKAGE_BOOST -> BOOST)
        clean_pkg_name = config_var.replace("BR2_PACKAGE_", "")
        
        for dep in inherited_deps:
            if dep not in inherited_dict:
                inherited_dict[dep] = []
            inherited_dict[dep].append(clean_pkg_name)

    # Pretty-format the merged result
    inherited_constraints = []
    for dep, sources in inherited_dict.items():
        sources_str = ", ".join(sorted(set(sources)))
        inherited_constraints.append(f"depends on {dep} (inherited from {sources_str})")

    # 3. Always collect the comment text for the AI
    comment_lines = run_git_grep(sandbox_path, r"^\s*comment\s+", f"package/{pkg_name}/Config.in")
    comments = [line.split(':')[-1].strip() for line in comment_lines]

    return {
        "package": pkg_name,
        "toolchain_and_arch_constraints": sorted(list(set(constraints))),
        "inherited_toolchain_constraints": sorted(inherited_constraints),
        "toolchain_comments": comments
    }

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: python3 br_package_analyzer.py <action: deps|toolchain> <sandbox_path> <package_name>"}))
        sys.exit(1)
        
    action = sys.argv[1]
    sandbox_dir = sys.argv[2]
    pkg_name = sys.argv[3]
    
    if action == "deps":
        result = get_dependencies_info(sandbox_dir, pkg_name)
    elif action == "toolchain":
        result = get_toolchain_arch_info(sandbox_dir, pkg_name)
    else:
        result = {"error": f"Unknown action '{action}'"}
        
    print(json.dumps(result, indent=2))
