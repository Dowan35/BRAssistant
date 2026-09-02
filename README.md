# Buildroot Review Assistant

An AI-powered automated code review assistant designed specifically for the **Buildroot** project. The system leverages Retrieval-Augmented Generation (RAG) by combining an **Elasticsearch** vector database with an AI agent (here **Gemini 3 Flash (Thinking Mode)**) to analyze patches, enforce manual compliance, cross-reference historical rejections (jurisprudence), and handle complex multi-part patch series.



## 1. Key Features

* **Dual-Engine RAG**: Performs semantic kNN vector searches over both the official Buildroot User Manual and a curated history of past patch rejections.
* **Code-Signature Alignment**: Employs a unified embedding strategy to match raw patch diff patterns directly with natural language developer logs.
* **Patchwork Series Awareness**: Automatically detects patch structures (e.g., `[v5, 2/5]`), securely querying the Patchwork API to pull and reconstruct the context of the series' Cover Letter ($0/n$) and previous patches before reviewing the target file.
* **Strict Hierarchy of Truth**: Validates submissions through an ordered priority loop: Manual Rules $\\rightarrow$ Past Case-Law $\\rightarrow$ Expert Intuition.
* **Production-Ready Output**: Generates editable standard `.eml` mail draft reviews containing precise, inline file feedback.



## 2. Prerequisites

Ensure your host machine has the following prerequisites installed:
* **Python 3.10** or higher
* **Docker** & Docker Engine
* `curl` (for database verification)
* `libmagic` (sudo apt install libmagic1) for the Buildroot's check-package command


## 3. Technical Stack & Dependencies

The project relies on the core dependencies specified in `requirements.txt`:

| Package | Purpose |
| :--- | :--- |
| `elasticsearch` (< 9.0.0) | Official client library for database interactions and vector storage. |
| `sentence-transformers` | Generates text embeddings locally for semantic search. |
| `huggingface_hub` | Manages download and caching of NLP models. |
| `python-magic` | Required for Buildroot's check-package script execution. |
| `flake8` | Python linter utilized by check-package. |
| `bs4` (BeautifulSoup) | Handles HTML/XML log parsing and text extraction. |
| `python-dotenv` | Loads configuration options seamlessly from `.env` files. |
| `openai` | Standardized interface tool for LLM inference APIs (supports OpenRouter, Google, Cohere, etc.). |
| `asyncio` / `aiohttp` | Core asynchronous engines for concurrent network and file operations. |
| `tenacity` | Advanced retry handling for robust API calls and database synchronization. |



## 4. Infrastructure Setup

The processing pipeline requires an active Elasticsearch 8.x instance to store embeddings.

### Option A: Docker Deployment (Recommended)

Run the following command to spin up a single-node Elasticsearch container with security features disabled for development purposes:

```bash
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.12.0

docker run -d --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" \
  docker.elastic.co/elasticsearch/elasticsearch:8.12.0

docker start elasticsearch
```

### Option B: Host Systemd Service

If Elasticsearch is installed directly on the host system, manage the service using systemd outside of any Python virtual environment (outside venv):

```bash
# Check service status
sudo systemctl status elasticsearch

# Start service if stopped
sudo systemctl start elasticsearch
```

### Verifying Elasticsearch Status

Verify that the cluster is up and inspect available indices (including document counts and store sizes) using the following `curl` command:

```bash
curl -s "http://localhost:9200/"
```
Please also verify that your disk usage is below 85% or you might have indexation problems (see https://www.elastic.co/docs/troubleshoot/elasticsearch/fix-watermark-errors) :

```bash
curl -s "http://localhost:9200/_cat/allocation?v"
```


## 5. Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dogulSmile/BRAssistant
   cd BRAssistant
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Environment Variables (.env file) :**

   Fristly provide the mail adress you will use for reviews:
      ```env
      MAIL_ADRESS="vacation@gmail.com"
      ```

   Then get your keys here (no specific permissions required) :

      https://huggingface.co/settings/tokens (`HF_API_KEY` required if you want to vectorize new data)

      https://openrouter.ai/workspaces/default/keys (if using openrouter for patch reviews)
      
   You will then create/modify a `.env` file in the root directory to store your API keys and configurations, here is an example configuration with multiple AI models that I used for reviews (subject to change) :

   ```env
      MAIL_ADRESS="vacation@gmail.com"

      HF_API_KEY="your_hf_key"
      HF_MODEL_ID="sentence-transformers/all-MiniLM-L6-v2"

      # Available providers: gemini, cohere, openrouter, claude, b.ai

      # --- STAGE 1: Router
      ROUTING_PROVIDER="openrouter"
      ROUTING_MODEL="nvidia/nemotron-3.5-lightning:free"

      # --- STAGE 2: Agents
      AGENT_PROVIDER="openrouter"
      AGENT_MODEL="minimax/minimax-m3:free"

      # --- STAGE 3: Judge
      JUDGE_PROVIDER="openrouter"
      JUDGE_MODEL="nvidia/nemotron-3-ultra-550b-a55b:free"

      GEMINI_API_KEY="your_gemini_key"
      OPENROUTER_API_KEY="your_openrouter_key"
   ```

   As you can see, you can setup different keys/model in the `.env` file, but you will have to choose which one to use for 

   - **vectorizing** : the only provider supported at the moment is Hugging Face. just put your key in `HF_API_KEY` if you want to add new data to the RAG database.
   - **routing (Stage 1)** : The router requires a fast model capable of strict JSON formatting to determine which agents to wake up. Set your choices in `ROUTING_PROVIDER` and `ROUTING_MODEL`.
   - **patch review (Stage 2)** : This stage executes multiple specialized agents concurrently. It requires a model with strong reasoning and code analysis capabilities. Set your choices in `AGENT_PROVIDER` and `AGENT_MODEL`.
   - **final judge (Stage 3)** : The judge acts as the final editor, resolving logical contradictions and formatting the email. It requires a model with excellent synthesis and formatting skills. Set your choices in `JUDGE_PROVIDER` and `JUDGE_MODEL`.

4. **Environment Variables:**

   Launch those 2 commands at the root of the project to initialize the database (Elasticsearch must be started):
   ```bash
   python3 elastic_functions/vectorializer.py -d ressources/The_Buildroot_user_manual.html reset
   python3 elastic_functions/vectorializer.py -p ressources/buildroot_lessons.jsonl reset

   (You can enhance the database by adding other files (without the 'reset'), but the format has to be respected.)
   ```


## 6. Usage

To launch the agent, please verify that your venv is activated, then in the root of the project simply launch this command :

```bash
python3 ./BRAssistant.py 
```
You will be asked to put the patch to review, you have 2 possible choices:
  - file : simply put the path of the .patch to analyze (ex: /home/user/Downloads/package-test.patch)
  - link : paste the patchwork url of the patch (ex: https://patchwork.buildroot.org/project/buildroot/patch/20260520092415.665898-1-giulio.benetti@benettiengineering.com/)

You can also directly indicate the patch to analyze this way:

```bash
python3 ./BRAssistant.py <patchwork_url_of_the_contribution>
```

After the analyze, you will find your review ready in .eml format in the reviews_eml/ directory, you can open it with your favorite mail software and edit it (using Thunderbird, you will do right-clic, then 'Edit as new message')
Depending of your mail app, some of them are not compatible with "In-Reply-To" header, in this case you might directly reply to the original mail to keep the thread.

### Feedback

To help improve the assistant's accuracy, you can submit your feedback after each review.
Simply open the generated .eml file, read it, and if you notice a problem, type “2” or “3” to enter your comments and automatically submit a suggestion that you can discuss on https://github.com/dogulSmile/BRAssistant/issues .

```bash
How was this review ? (empty to skip) 
    [1] Perfect
    [2] Good, but missed something
    [3] Hallucination / Bad rule applied : 2
```
If you find the answer correct, just press 'enter' to continue.

To analyze another patch, you can simply enter again another url/path of a patch, and another .eml file will be created.

## 7. Data update

To update the database of the RAG, there is multiple functions to retrieve and format the patches and the documentation.

### Documentation retrieval

`data_construction/documentation_scrapper.py`
This script retrieve Buildroot's documentation and synthesizes it.
It rewrites the content of 'ressources/The_Buildroot_user_manual.html'
```bash
python3 ./data_construction/documentation_scrapper.py
```
### Patches retrieval
`data_construction/patch_scrapper.py`
This script retrieve precedent patches from Patchwork with a specified status.
You can't directly send this list to the DB, please format it with patch_formatter.py before.
```bash
python3 ./data_construction/patch_scrapper.py <output_file_path>
#example : python3 ./data_construction/patch_scrapper.py output/patches.json
```
### Patches formatter
`data_construction/patch_formatter.py`
This script uses AI to format previous patches by summarizing the issue and the solution found by the maintainer, in order to reduce patch size for future vector searches.
```bash
python3 ./data_construction/patch_formatter.py <input_file_path> <output_file_path>
#example : python3 ./data_construction/patch_formatter.py output/patches.json
#default output path is ressources/buildroot_lessons.jsonl
```

Reminder: to push new patches to the database, use `python3 elastic_functions/vectorializer.py -p ressources/buildroot_lessons.jsonl`

## 8. How to choose the AI Model

Because BRAssistant utilizes a three-stage multi-agent architecture, you can mix and match models based on the specific requirements of each stage. Set the models via the `.env` file configuration blocks.

Currently, there are a few different models supported, and your choice will produce varied results.

* **Stage 2 (Reasoning Agents)** requires models capable of deep code analysis and strict heuristic adherence.
* **Stage 1 (Routing) & Stage 3 (Judge)** require high-speed JSON strictness and strong natural language synthesis, respectively.

Here are the pros and cons for the supported models to help you choose:

### Stage 2: Reasoning Agents (Code Review)

*Requires strong code analysis, logical deduction, and the ability to follow strict Buildroot heuristics.*

**`minimax/minimax-m3:free` (OpenRouter)** <-- Recommended Free Tier

* **Pros:** Completely free API aggregator option. Handles large contexts well and provides strong reasoning capabilities necessary for deep code review.
* **Cons:** Reliability and answer times highly depend on OpenRouter's free tier load and the model might not be free in few months.

**`gemini-3.(5,6,7,..)-flash` (Google)**

* **Pros:** Gives highly precise answers and is less prone to hallucinations.
* **Cons:** Slower answers on the free plan and "Best-effort" service; retries might be needed during high demand periods. Limited to 20 requests per day on the free plan.

**`command-a-plus-05-2026` (Cohere)**

* **Pros:** Good answer times, open source and high availability.
* **Cons:** Answers are very concise, limited, and not detailed enough. Lacks the capacity for complex reasoning and "expert intuition" required for deep patch analysis.

### Stage 1: Routing & Stage 3: Judge

*Requires fast execution and strict JSON adherence (Router), and strong natural language synthesis/deduplication (Judge).*

**`nvidia/nemotron-3.5-lightning:free` (OpenRouter)** <-- Recommended for Stage 1 (Routing)

* **Pros:** Fast and excellent at adhering strictly to JSON schemas, making it perfect for determining which agents to wake up based on patch content.
* **Cons:** Availability can vary based on the free tier network load.

**`nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter)** <-- Recommended for Stage 3 (Judge)

* **Pros:** Outstanding at synthesizing multiple agent reports, resolving logical contradictions, and enforcing strict formatting rules for the final `.eml` draft.
* **Cons:** Can be slower than smaller models; dependent on OpenRouter's free tier load.

**`llama-3.3-70b-versatile` (Groq)**

* **Pros:** Very high speed (LPU hardware). Solid choice for fast JSON routing.
* **Cons:** Not the absolute best for complex logic, and possesses extremely strict Tokens-Per-Minute (TPM) limits on the free tier (do not use for the Reasoning Agents).

**`gemini-3.5-flash-lite` (Google AI Studio)**

* **Pros:** Fast answer time when available.
* **Cons:** Subject to downtime during high demand on free plans, 500 requests per day.

### Miscellaneous (Non-free alternatives)

There are, of course, additional models available that are highly recommended for this project if you have a financial budget. Even a very low budget avoids strict rate limits, eliminates timeouts, and unlocks the true potential of BRAssistant.

*Cost estimation baseline on 25/06/2026: A complex patch review with RAG injection averages **20,000 tokens** (19k input context + 1k output generation). API costs are subject to change.*

**`deepseek-v4-pro (thinking mode)` (Official DeepSeek API)**

* **Pros:** Top-tier coding and reasoning capabilities, matching or beating industry standards. Massive 128k context window. Extremely aggressive pricing.
* **Cons:** The free `b.ai` provider has significant limitations and severe delays. Using the official API requires topping up a prepaid balance on their platform.
* **Estimated Price:** **~$0.009 per review** (Less than a cent!).

**`anthropic.claude-3-5-sonnet` (Anthropic API)**

* **Pros:** Widely considered the absolute undisputed king of code review and complex instruction following. Exceptional at synthesizing data for the Judge stage and zero-shot coding tasks for the Agents. Almost zero hallucinations.
* **Cons:** Pricier than DeepSeek, though still highly cost-effective for a single review.
* **Estimated Price:** **~$0.06 per review** (6 cents).

**`gpt-4o` (Official OpenAI API)**

* **Pros:** The industry standard. Extremely fast and reliable 128k context window without restrictive rate limits.
* **Cons:** Currently one of the most expensive options.
* **Estimated Price:** **~$0.0625 per review** (6.25 cents).

**`grok-4.3 (medium reasoning_effort)` (Groq)**
* **Pros:** 150$/month free tokens, with a mean request around 20k tokens, it would be 5k free requests/month (respect if you ever do 5k reviews). (see https://grok-api.apidog.io/free-credits-934025m0)
* **Cons:** Need a 5$ initial investment, eligibility conditions, and is owned by Elon Musk.
* **Estimated Price:** **~$0.025 per review** (2.5 cents). https://docs.x.ai/developers/models

## 9. Troubleshooting

Here are the common problems you can encounter :

```bash
elastic_transport.ConnectionError: Connection error caused by: ConnectionError(Connection error caused by: NewConnectionError(HTTPConnection(host='localhost', port=9200): Failed to establish a new connection: [Errno 111] Connection refused))
```
* **Solution:** Start the elasticsearch container with the command  `docker start elasticsearch`
  <br><br>
```bash
Error : please provide a valid mail adress in .env file.`
```
* **Solution:** You need to add your mail adress in   `.env` file.
  <br><br>
```bash
No patch found for Message-ID : ...
Patchwork URL detected, retrieving patch data from API.
Error: Failed to retrieve patch data.
```
* **Solution:** Provide a valid patch link from https://patchwork.buildroot.org/project/buildroot, or a .patch file.
  <br><br>

## 9. Troubleshooting

Here are the common problems you can encounter :

```bash
elastic_transport.ConnectionError: Connection error caused by: ConnectionError(Connection error caused by: NewConnectionError(HTTPConnection(host='localhost', port=9200): Failed to establish a new connection: [Errno 111] Connection refused))
```
* **Solution:** Start the elasticsearch container with the command  `docker start elasticsearch`
  <br><br>
```bash
Error : please provide a valid mail adress in .env file.`
```
* **Solution:** You need to add your mail adress in   `.env` file.
  <br><br>
```bash
No patch found for Message-ID : ...
Patchwork URL detected, retrieving patch data from API.
Error: Failed to retrieve patch data.
```
* **Solution:** Provide a valid patch link from https://patchwork.buildroot.org/project/buildroot, or a .patch file.
  <br><br>
