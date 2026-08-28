#!/usr/bin/env python3
# br_ingestor.py
# Usage: python3 br_ingestor.py <url_or_filepath>

import pathlib
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import pathlib
import sys
import os
import re
import uuid
import subprocess
import json
import requests

parent_dir = pathlib.Path(__file__).parent.resolve()
SANDBOX_SCRIPT = parent_dir.parent / 'sandbox' / 'setup_sandbox.sh'

def fetch_patchwork_mbox(patch_url_or_id):
    """
    Retrieve all the info from the current patch using the Patchwork API.
    Returns the raw mbox/diff content.
    """
    mbox_url = f"{patch_url_or_id}/mbox"
    
    # Using requests with a standard User-Agent just to be safe
    headers = {
        'User-Agent': 'BRAssistant-Agent/1.0 (Python/requests)'
    }

    session = requests.Session()
    retries = Retry(
        total=3, 
        backoff_factor=1,
        status_forcelist=[ 500, 502, 503, 504 ]
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        response = session.get(mbox_url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Network error while downloading the patch : {e}")
        sys.exit(1)

def ingest_patch(source):
    """Handles ingestion of a URL or local file, start the sandbox and apply the patch.
    Return a json with infos like the sandbox path and the status of git am.
    """
    sandbox_id = str(uuid.uuid4())[:8]
    work_dir = "/tmp/brassistant_sandboxes"
    os.makedirs(work_dir, exist_ok=True)
    
    patch_file_path = os.path.join(work_dir, f"patch_{sandbox_id}.patch")

    # 1. Detect source type (URL vs Local File) and save the patch in a file for the sandbox
    if re.match(r'^https?://', source):
        # This is a Patchwork URL
        patch_data = fetch_patchwork_mbox(source)
        with open(patch_file_path, 'wb') as f:
            f.write(patch_data)
    else:
        # This is a local file
        local_path = os.path.abspath(source)
        if not os.path.isfile(local_path):
            print(json.dumps({"status": "error", "message": f"File not found: {local_path}"}))
            sys.exit(1)
        
        # Copy file to work directory
        with open(local_path, 'rb') as src_f, open(patch_file_path, 'wb') as dest_f:
            dest_f.write(src_f.read())

    print(f"Patch file prepared: {patch_file_path}", file=sys.stderr)

    # 2. Trigger sandbox creation and send the path of the patch to apply it there
    print(f"Creating Git sandbox ({sandbox_id})...", file=sys.stderr)
    try:
        result = subprocess.run(
            [SANDBOX_SCRIPT, patch_file_path, sandbox_id],
            capture_output=True,
            text=True,
            check=True
        )
        
        # The bash script returns JSON on its last line
        sandbox_data = json.loads(result.stdout.strip().splitlines()[-1])
        return sandbox_data

    except subprocess.CalledProcessError as e:
        print(json.dumps({"status": "error", "message": "setup_sandbox.sh failed", "details": e.stderr}))
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 br_ingestor.py <patchwork_url_OR_local_file>")
        sys.exit(1)
        
    source_input = sys.argv[1]
    result_json = ingest_patch(source_input)
    
    print("\n--- Ingestion Result ---", file=sys.stderr)
    print(json.dumps(result_json, indent=2))

