#!/usr/bin/env python3
"""
Buildroot License Inspector

This script utilizes the Buildroot make infrastructure to extract a package,
locate its build directory, scan for license files, and extract SPDX identifiers
directly from the source code headers. It validates findings against the 
official SPDX license database.

Usage:
    ./br_license_inspector.py <package_name>
    ./br_license_inspector.py host-localedef
"""

import os
import sys
import json
import subprocess
import re
import urllib.request
from pathlib import Path
import argparse

SPDX_URL = "https://spdx.org/licenses/licenses.json"

def log(msg):
    """Print logs to stderr so stdout remains clean JSON."""
    print(f"[INFO] {msg}", file=sys.stderr)

def error_exit(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_spdx_database():
    """Download and parse the official SPDX license database."""
    log(f"Fetching SPDX database from {SPDX_URL}...")
    try:
        with urllib.request.urlopen(SPDX_URL, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            valid_ids = {lic["licenseId"] for lic in data.get("licenses", [])}
            log(f"Successfully loaded {len(valid_ids)} SPDX identifiers.")
            return valid_ids
    except Exception as e:
        log(f"Failed to fetch SPDX database: {e}")
        return set()

def extract_package(pkg_name):
    """Trigger Buildroot to download and extract the package."""
    # we generate a defconfig to generate a .config to launch the make ...-extract command
    try:
        subprocess.check_call(
            ["make", "alldefconfig"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        pass

    log(f"Running 'make {pkg_name}-extract' to fetch and unpack sources...")
    try:
        subprocess.check_call(
            ["make", f"{pkg_name}-extract"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        error_exit(f"Buildroot failed to extract '{pkg_name}'. Verify the package name.")

def get_build_dir(pkg_name):
    """Use Buildroot printvars to find the exact extracted directory."""
    pkg_upper = pkg_name.upper().replace('-', '_')
    var_name = f"{pkg_upper}_DIR"
    
    log(f"Resolving build directory via '{var_name}'...")
    try:
        output = subprocess.check_output(
            ["make", "-s", "printvars", f"VARS={var_name}"],
            text=True
        ).strip()
        
        for line in output.splitlines():
            if line.startswith(f"{var_name}="):
                path = line.split('=', 1)[1]
                if os.path.isdir(path):
                    return path
    except subprocess.CalledProcessError:
        pass
    
    error_exit(f"Could not resolve or locate build directory for '{pkg_name}'.")

def scan_license_files(build_dir):
    """Identify root-level files that typically contain licensing text."""
    log("Scanning for license files at the root of the extracted source...")
    found_files = []

    licenses_dir = os.path.join(build_dir, "LICENSES")
    if os.path.isdir(licenses_dir):
        for item in os.listdir(licenses_dir):
            if os.path.isfile(os.path.join(licenses_dir, item)):
                found_files.append(f"LICENSES/{item}")

    # Match files like COPYING, LICENSE, README, including extensions like .txt, .md, .lesserv2
    pattern = re.compile(r"^(COPYING|LICENSE|COPYRIGHT)(.*)?$", re.IGNORECASE)
    for item in os.listdir(build_dir):
        item_path = os.path.join(build_dir, item)
        if os.path.isfile(item_path) and pattern.match(item):
            found_files.append(item)

    # Fallback: ONLY suggest README if absolutely no other license files were found
    if not found_files:
        for item in os.listdir(build_dir):
            if os.path.isfile(os.path.join(build_dir, item)) and item.lower().startswith("readme"):
                found_files.append(item)

    return sorted(found_files)

def extract_spdx_tokens(expression):
    """Split an SPDX expression into base tokens, ignoring operators."""
    # Split by spaces, parentheses, or SPDX operators
    tokens = re.split(r'\s+|\(|\)', expression)
    keywords = {"AND", "OR", "WITH", ""}
    return [t for t in tokens if t not in keywords]

def scan_source_for_spdx(build_dir, valid_spdx_ids):
    """Recursively scan source file headers for SPDX-License-Identifier tags."""
    log("Scanning source files for SPDX-License-Identifier headers...")
    spdx_pattern = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9\.\-\+\s\(\)]+)")
    
    found_expressions = set()
    validated_licenses = set()
    unrecognized_licenses = set()
    
    for root, _, files in os.walk(build_dir):
        for file in files:
            filepath = os.path.join(root, file)
            # Skip likely binary files or huge files to save time
            if os.path.getsize(filepath) > 1024 * 1024:
                continue
                
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f):
                        # SPDX tags are conventionally in the first few lines
                        if i > 50:
                            break
                        match = spdx_pattern.search(line)
                        if match:
                            expr = match.group(1).strip()
                            found_expressions.add(expr)
            except Exception:
                continue

    # Validate tokens against official SPDX database
    if valid_spdx_ids:
        for expr in found_expressions:
            tokens = extract_spdx_tokens(expr)
            for token in tokens:
                # Remove '+' which implies "or later" in SPDX shorthand but might not be in the base DB list
                base_token = token[:-1] if token.endswith('+') else token
                
                if base_token in valid_spdx_ids or token in valid_spdx_ids:
                    validated_licenses.add(token)
                else:
                    unrecognized_licenses.add(token)
    else:
        # Fallback if offline
        validated_licenses = set(extract_spdx_tokens(" ".join(found_expressions)))

    return list(validated_licenses), list(unrecognized_licenses)

def resolve_target_name(pkg_name):
    """Parse the .mk file to instantly detect if it evaluates as a host or target package."""
    # Strip 'host-' if the user already provided it
    base_name = pkg_name[5:] if pkg_name.startswith("host-") else pkg_name
    
    # Locate the .mk file within the package/ directory
    mk_files = list(Path("package").rglob(f"{base_name}.mk"))
    if not mk_files:
        return pkg_name # Fallback to user input if not found
        
    has_target = False
    has_host = False
    
    with open(mk_files[0], 'r', encoding='utf-8') as f:
        content = f.read()
        # Look for the evaluation macros at the bottom of the file
        if re.search(r'^\s*\$\(eval \$\(host-.*package\)\)', content, re.MULTILINE):
            has_host = True
        if re.search(r'^\s*\$\(eval \$\((?!host-).*package\)\)', content, re.MULTILINE):
            has_target = True

    # Resolve the correct Buildroot target name
    if pkg_name.startswith("host-") and has_host:
        return pkg_name
    if has_target:
        return base_name
    if has_host:
        return f"host-{base_name}"
        
    return pkg_name

def main():
    parser = argparse.ArgumentParser(description="Analyze a Buildroot package for licenses.")
    parser.add_argument("-b", "--buildroot-dir", default=".", help="Path to the Buildroot repository (default: current directory)")
    parser.add_argument("package", help="Name of the Buildroot package (e.g., localedef, host-localedef)")
    args = parser.parse_args()

    try:
        os.chdir(args.buildroot_dir)
    except OSError as e:
        error_exit(f"Failed to access Buildroot directory '{args.buildroot_dir}': {e}")

    if not os.path.isfile("Makefile") or not os.path.isdir("package"):
        error_exit("This script must be executed from the root of the Buildroot repository.")

    # Auto-detect if the package requires the 'host-' prefix
    pkg_name = resolve_target_name(args.package)
    if pkg_name != args.package:
        log(f"Auto-detected '{args.package}' as a host package. Resolved target: '{pkg_name}'")
    
    valid_spdx_ids = fetch_spdx_database()
    extract_package(pkg_name)
    build_dir = get_build_dir(pkg_name)
    
    log(f"Source extracted to: {build_dir}")
    
    license_files = scan_license_files(build_dir)
    validated_spdx, unrecognized_spdx = scan_source_for_spdx(build_dir, valid_spdx_ids)
    
    report = {
        "package_name": pkg_name,
        "build_directory": build_dir,
        "suggested_mk_variables": {
            f"{pkg_name.upper().replace('-', '_')}_LICENSE": ", ".join(validated_spdx) if validated_spdx else "UNKNOWN",
            f"{pkg_name.upper().replace('-', '_')}_LICENSE_FILES": " ".join(license_files) if license_files else ""
        },
        "details": {
            "root_license_files_found": license_files,
            "spdx_identifiers_found": validated_spdx,
            "unrecognized_identifiers": unrecognized_spdx
        }
    }

    # Output strictly JSON to stdout for AI/agent consumption
    print(json.dumps(report, indent=4))

if __name__ == "__main__":
    main()
