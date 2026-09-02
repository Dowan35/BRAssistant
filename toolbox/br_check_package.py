#!/usr/bin/env python3
# br_check_package.py
# Usage: python3 br_check_package.py <sandbox_path>

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sandbox.sandbox_git_tool import run_command

def run_check_package(sandbox_path):
    """Run the Buildroot check-package script on the modified files."""
    diff_result = run_command(sandbox_path, ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    
    if diff_result["status"] == "error":
        return {"status": "error", "message": f"Failed to get git diff : {diff_result['output']}"}
    
    files = [f for f in diff_result["output"].splitlines() if os.path.exists(os.path.join(sandbox_path, f))]
    if not files:
        return {"status": "success", "warnings": [], "message": "No files to check."}

    check_result = run_command(sandbox_path, ["./utils/check-package"] + files, 300)  # 300 seconds timeout
    if check_result["status"] == "error":
        return {"status": "error", "message": f"Failed to run check-package : {check_result['output']}"}

    # Process lines to filter out noise
    raw_lines = check_result["output"].splitlines()
    warnings = []
    
    for line in raw_lines:
        line = line.strip()
        if not line: continue
        
        # Noise filter: remove shellcheck info lines
        # to avoid the AI attempting to invoke out-of-context tools.
        if "run 'shellcheck'" in line:
            continue
            
        # Keep only lines that look like alerts (e.g., "file:line: warning")
        if ":" in line and "lines processed" not in line and "warnings generated" not in line:
            warnings.append(line)
    
    status = "success" if check_result["status"] == "success" and not warnings else "warning"
    
    return {
        "status": status,
        "files_checked": len(files),
        "warnings": warnings,
        "message": f"{len(warnings)} warning(s) detected." if warnings else "No issues found."
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 br_check_package.py <sandbox_path>"}))
        sys.exit(1)
        
    sandbox_dir = sys.argv[1]
    try:
        response = run_check_package(sandbox_dir)
        print(json.dumps(response, indent=2))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
