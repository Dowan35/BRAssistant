# BRAssistant: Architecture & Getting Started

BRAssistant is a multi-agent AI system designed to automate and enhance static patch reviews for the Buildroot project. It operates as a collaborative pipeline: a router assigns tasks to specialized agents, deterministic Python tools extract ground-truth data from the codebase, and a RAG (Retrieval-Augmented Generation) pipeline provides context from the Buildroot manual and mailing list. A final judge agent synthesizes the findings into a cohesive email review.

## 1. Root Directory (Entry Point & Core)
*   **`BRAssistant.py`**: The main orchestrator. Initializes the pipeline, routes tasks, triggers tools, executes AI agents concurrently, and passes results to the final judge.
*   **`requirements.txt`**: Python dependencies (Huggingface, Elasticsearch, etc.).
*   **`README.md`**: Basic user documentation.
*   **`sandbox/`**: Gather tools to create temporary working directory and extract packages to analyze source code without polluting the main environment.
*   **`output/`** & **`reviews_eml/`**: Respectively, the storage for scrapped patches from patch_scrapper.py, and the final generated email files (.eml) ready for the mailing list.

## 2. AI Agents & Prompts (`ai_agents/` & `prompts/`)
Each specialized Python agent in `ai_agents/` is paired with a strictly defined Markdown prompt in `prompts/`.
*   **`toolchain_arch_agent.py`** / **`toolchain_and_arch_review.md`**: Validates toolchain constraints, inherited dependencies, and matching Kconfig comments.
*   **`dependency_agent.py`** / **`dependency_review.md`**: Verifies `select` vs. `_DEPENDENCIES` consistency, missing dependencies and alphabetical sorting.
*   **`license_agent.py`** / **`license_review.md`**: Analyzes SPDX identifiers, `_LICENSE_FILES` variables, and hash requirements.
*   **`code_quality_agent.py`** / **`code_quality_review.md`**: Inspects Kconfig indentation, Makefile formatting, and general coding style from Buildroot's manual.
*   **`infra_agent.py`** / **`infra_review.md`**: Validates Buildroot infrastructure macros (`cmake-package`, `autotools-package`, etc.).
*   **`upstream_agent.py`** / **`upstream_patch_review.md`**: Ensures package-specific patches contain upstream links and Signed-off-by tags.
*   **`final_judge.py`** / **`final_judge_review.md`**: Synthesizes JSON reports from all sub-agents, deduplicates issues, resolves logical contradictions, and formats the final email.

## 3. The Toolbox (`toolbox/`)
Deterministic Python scripts that extract factual data to prevent LLM hallucinations.
*   **`br_package_analyzer.py`**: Parses Kconfig and Makefiles to extract inter-package dependencies and inherited architecture/toolchain constraints.
*   **`br_license_inspector.py`**: Downloads package sources, scans directories (including `LICENSES/`), and extracts native SPDX-License-Identifier tags.
*   **`routing_functions.py`**: Determines is an agent should be run based on patch diffs and keywords to optimize token usage. Also dispatch RAG's findings to the corresponding agents if applicable.
*   **`br_check_package.py`**: Wrapper for Buildroot's native `check-package` script.
*   **`tool_execution_functions.py`**: Utility functions bridging AI agents and the toolbox, with async functionality.

## 4. RAG Pipeline (`data_construction/` & `elastic_functions/`)
Manages external knowledge retrieval (Buildroot manual and mailing list history).

### A. Data Scraping & Formatting (`data_construction/`)
*   **`documentation_scrapper.py`**: Scrapes the official Buildroot manual.
*   **`patch_scrapper.py`**: Fetches historical patches and maintainer reviews from Patchwork.
*   **`patch_formatter.py`**: Cleans and standardizes raw data into structured JSON format.

### B. Vectorization & Search (`elastic_functions/`)
*   **`vectorializer.py`**: Converts formatted JSON into vector embeddings to capture semantic meaning.
*   **`database_sync.py`**: Pushes vectorized data to the vector database.
*   **`search_database.py`**: The search engine used by agents to retrieve relevant manual excerpts and historical patch reviews.

**RAG Update Procedure:**
To update the system's knowledge base (e.g., after a new Buildroot release or to add recent mailing list reviews), execute the following pipeline:
1.  `python data_construction/documentation_scrapper.py` (Update sources)
2.  `python data_construction/patch_scrapper.py` (Update sources)
2.  `python data_construction/patch_formatter.py` (Format data, needs gemini api key to synthetize patch data)
3.  `python elastic_functions/database_sync.py` (Compute embeddings and push to the database)

## 5. Testing (`support/testing/`)
*   Contains unit tests (e.g., `test_br_package_analyzer.py`, `test_br_license_inspector.py`). These scripts use `tempfile` to create virtual Buildroot sandboxes, ensuring Python tools extract data accurately before passing it to the AI. This test suite must be run after any modifications to the corresponding scripts.
