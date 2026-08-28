#!/bin/bash
# setup_sandbox.sh
# Usage: ./setup_sandbox.sh <path_to_patch> <sandbox_id>

PATCH_FILE=$(realpath "$1")
SANDBOX_ID="$2"
BUILDROOT_URL="https://gitlab.com/buildroot.org/buildroot.git"
WORK_DIR="/tmp/brassistant_sandboxes"
SANDBOX_PATH="$WORK_DIR/$SANDBOX_ID"

# Prepare base JSON structure
JSON_OUTPUT="{\"sandbox_id\": \"$SANDBOX_ID\", \"status\": \"\", \"message\": \"\", \"sandbox_path\": \"$SANDBOX_PATH\"}"

mkdir -p "$WORK_DIR"

# 1. Setup the Cache directory for Buildroot so we dont have to clone it each time
CACHE_DIR="$WORK_DIR/buildroot_cache"
if [ ! -d "$CACHE_DIR" ]; then
    git clone --bare "$BUILDROOT_URL" "$CACHE_DIR" > /dev/null 2>&1
else
    git -C "$CACHE_DIR" fetch origin master:master > /dev/null 2>&1
fi

PATCH_BASENAME=$(basename "$PATCH_FILE")
CACHE_BASENAME=$(basename "$CACHE_DIR")
#Cleaning old sandboxes/patches
find "$WORK_DIR" -mindepth 1 -maxdepth 1 \
    ! -name "$CACHE_BASENAME" \
    ! -name "$PATCH_BASENAME" \
    -exec rm -rf {} +

# 2. Creating the worktree (sandbox)
if [ -d "$SANDBOX_PATH" ]; then
    rm -rf "$SANDBOX_PATH"
fi
#make a temp copy of the buildroot_cache so we can use it for this analysis
git clone "$CACHE_DIR" "$SANDBOX_PATH" > /dev/null 2>&1

cd "$SANDBOX_PATH"
git checkout -b "review_$SANDBOX_ID" > /dev/null 2>&1

# 3 Enable all packages
# 3. Applying patch with git am
if git am "$PATCH_FILE" > /tmp/git_am_out.log 2>&1; then
    COMMIT_HASH=$(git rev-parse HEAD)
    echo "{\"sandbox_id\": \"$SANDBOX_ID\", \"status\": \"success\", \"message\": \"Patch applied cleanly.\", \"sandbox_path\": \"$SANDBOX_PATH\", \"commit_hash\": \"$COMMIT_HASH\"}"
else
    # If the patch application fails, abort the git am operation and capture the error message
    git am --abort > /dev/null 2>&1
    ERROR_MSG=$(cat /tmp/git_am_out.log | tr '\n' ' ' | sed 's/"/\\"/g')
    echo "{\"sandbox_id\": \"$SANDBOX_ID\", \"status\": \"error\", \"message\": \"git am failed: $ERROR_MSG\", \"sandbox_path\": \"$SANDBOX_PATH\"}"
fi
