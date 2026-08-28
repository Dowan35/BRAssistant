import re
from turtle import title

def is_package(modified_files):
    """Check if the patch corresponds to package-related files."""
    dependency_keywords = ["package/"]
    for file in modified_files:
        if any(keyword in file.lower() for keyword in dependency_keywords):
            return True
    return False

def should_run_dependency_agent(modified_files):
    """
    Determine if the dependency agent should be invoked based on the modified files.
    Returns True if any of the modified files are related to dependencies.
    """
    dependency_keywords = ["depends on", "select", "Config.in", ".mk", "_DEPENDENCIES"]
    
    for file in modified_files:
        if any(keyword in file.lower() for keyword in dependency_keywords):
            return True
    return False

def should_run_infra_agent(modified_files):
    """
    Determine if the infra agent should be invoked based on the modified files.
    Returns True if any of the modified files are related to infrastructure.
    """
    infra_keywords = ["Config.in"]
    
    for file in modified_files:
        if any(keyword in file.lower() for keyword in infra_keywords):
            return True
    return False

def should_run_license_agent(diff_text, title):
    """Return True if the patch is likely to require a license review, based on the diff content and whether it's a new package."""
    if "new package" in title.lower():
        return True
    
    license_keywords = ["_LICENSE", "_LICENSE_FILES", ".hash"]
    # search if those keywords are in the diff, if yes return True, else return False
    return any(keyword in diff_text for keyword in license_keywords)

def should_run_toolchain_arch_agent(modified_files,title):
    """Return True if the patch needs a review on toolchain or architecture."""

    # Even if the package doesnt need a toolchain, it's safer to launch the agent on new packages in case a dependency is missing.
    if "new package" in title.lower():
        return True

    toolchain_keywords = ["toolchain", "architecture", "compilation", "cross-compile", "arch", "mmu", "threads", "c++", "wchar"]
    
    for file in modified_files:
        if any(keyword in file.lower() for keyword in toolchain_keywords):
            return True
    return False
    

def should_run_upstream_agent(modified_files):
    """Return True if the patch needs a review on an upstream component, based on the diff content and whether it's a new package."""
    dependency_keywords = [".patch"]
    
    for file in modified_files:
        if any(keyword in file.lower() for keyword in dependency_keywords):
            return True
    return False

def dispatch_rag_patches(rag_patches):
    """Dispatch the RAG patches to the appropriate agents based on their content."""
    rag_for_agents = {
        "code_review": [],
        "infra": [],
        "license": [],
        "deps": [],
        "board": [],
        "support": [],
        "toolchain_arch": [],
        "upstream": []
    }
    
    for patch in rag_patches:
        search_text = (patch.get("original_code_error", "") + " " + 
                       patch.get("issue", "") + " " + 
                       patch.get("action", "")).lower()

        formatted_case = (
            f"[URL: {patch.get('source_url', 'Unknown')}]\n"
            f"- Issue: {patch.get('issue', 'N/A')}\n"
            f"- Action: {patch.get('action', 'N/A')}\n"
        )
        
        if any(w in search_text for w in [
            "format", "order", "indentation", "trailing slash", "patterns", 
            "coding standards", "style", "formatting", "rules", "column", 
            "width", "check-package", "typo", "syntax", "spaces", "tabs", 
            "variable", "naming", "convention", "cleanup", "refactor", "makefile"
        ]):
            rag_for_agents["code_review"].append(formatted_case)

        if any(w in search_text.lower() for w in ["license", "spdx", "hash", "copying"]):
            rag_for_agents["license"].append(formatted_case)
            
        if any(w in search_text.lower() for w in ["depends on", "select", "dependenc", "circular"]):
            rag_for_agents["deps"].append(formatted_case)
            
        if any(w in search_text.lower() for w in ["staging_dir", "target_dir", "autotools", "cflags"]):
            rag_for_agents["infra"].append(formatted_case)

        if any(w in search_text.lower() for w in ["board", "board/"]):
            rag_for_agents["board"].append(formatted_case)
        
        if any(w in search_text.lower() for w in ["support", "support/", "support/testing"]):
            rag_for_agents["support"].append(formatted_case)

        if any(w in search_text.lower() for w in ["toolchain", "architecture", "compilation", "cross-compile", "arch", "mmu", "threads", "c++", "wchar"]):
            rag_for_agents["toolchain_arch"].append(formatted_case)
        
        if any(w in search_text.lower() for w in ["Upstream:", "upstream", "upstream/", "upstream patch", "upstreaming"]):
            rag_for_agents["upstream"].append(formatted_case)

    return rag_for_agents
