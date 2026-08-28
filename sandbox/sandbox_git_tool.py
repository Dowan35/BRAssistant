#!/usr/bin/env python3
# sandbox_git_tool.py
# Usage: python3 sandbox_git_tool.py <sandbox_path> <git_command> <args...>

import sys
import subprocess
import json

MAX_LINES = 150  # Limit to avoid context explosion
MAX_CHARS = 10000

def run_command(sandbox_path, command_args, timeout=10):
    """Launch a command in the specified sandbox directory and return the output."""
    
    try:
        result = subprocess.run(
            command_args,
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=timeout # avoids loops
        )
        
        output = result.stdout if result.returncode == 0 else result.stderr
        status = "success" if result.returncode == 0 else "error"
        
        # --- TRUNCATOR LOGIC---
        lines = output.splitlines()
        truncated = False
        
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES]
            lines.append(f"... [TRUNCATED: Output exceeded {MAX_LINES} lines. Please refine your git grep/show command.]")
            truncated = True
            
        final_output = "\n".join(lines)
        
        if len(final_output) > MAX_CHARS:
            final_output = final_output[:MAX_CHARS] + f"\n... [TRUNCATED: Output exceeded {MAX_CHARS} characters.]"
            truncated = True
            
        return {
            "command": " ".join(command_args),
            "status": status,
            "truncated": truncated,
            "output": final_output
        }

    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(command_args),
            "status": "error",
            "truncated": False,
            "output": "Command timed out."
        }
    except Exception as e:
        return {
            "command": " ".join(command_args),
            "status": "error",
            "truncated": False,
            "output": str(e)
        }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: sandbox_git_tool.py <sandbox_path> <cmd...>"}))
        sys.exit(1)
        
    sandbox_dir = sys.argv[1]
    command_args = sys.argv[2:]
    
    response = run_command(sandbox_dir, command_args)
    print(json.dumps(response, indent=2))
