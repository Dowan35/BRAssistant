import subprocess
import json
import asyncio
import os

def execute_tool(script_name, args):
    """
    Utility function to execute a toolbox script synchronously.
    Expects the script to return valid JSON on stdout.
    """
    # Dynamically find the toolbox directory
    toolbox_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(toolbox_dir, script_name)
    cmd = ["python3", script_path] + args

    # Inject root project directory into PYTHONPATH to prevent import errors inside tools
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(toolbox_dir)

    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True, 
            env=env
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error while running {script_name}: {e.stderr}")
        return {"error": str(e)}
    except json.JSONDecodeError:
        print(f"Error: {script_name} did not return valid JSON. Raw output: {result.stdout}")
        return {"error": "Invalid JSON output"}


async def execute_tool_async(script_name, args):
    """
    Utility function to execute a toolbox script asynchronously.
    Expects the script to return valid JSON on stdout.
    """
    toolbox_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(toolbox_dir, script_name)
    cmd = ["python3", script_path] + args

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(toolbox_dir)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return json.loads(stdout.decode().strip())
        else:
            print(f"Error while running {script_name}: {stderr.decode()}")
            return {"error": stderr.decode()}
    except json.JSONDecodeError:
        print(f"Error: {script_name} did not return valid JSON. Raw output: {stdout.decode().strip()}")
        return {"error": "Invalid JSON output"}
