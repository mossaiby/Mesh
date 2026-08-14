Here is a detailed, phased implementation plan for adding missing features to Mesh. The features are ordered strictly by **Ease vs. Value** (from quick, high-impact wins to advanced infrastructure).

---

## 📊 Ordering & Prioritization Matrix

```
                          HIGH VALUE
                             │
     Phase 1: Quick Wins     │     Phase 2: Core Engineering
  ┌──────────────────────────┼──────────────────────────┐
  │ 1. Prompt Cache Metrics  │ 4. Tool Output Pruning   │
  │ 2. Session Spend Caps    │ 5. Architect/Editor Mode │
  │ 3. Git Auto-Commit Mode  │ 6. Playwright Browser    │
  │                          │ 7. Voice Input (Whisper) │
  └──────────────────────────┴──────────────────────────┘
EASY ─────────────────────────────────────────────────── COMPLEX
  ┌──────────────────────────┬──────────────────────────┐
  │                          │ 8. External File Watcher │
  │                          │ 9. Vector Code Search    │
  │                          │ 10. LSP Diagnostics      │
  │                          │ 11. Headless Daemon API  │
  │                          │ 12. Event Webhooks       │
  └──────────────────────────┴──────────────────────────┘
   Phase 3: Deep Intelligence│  Phase 4: Ecosystem Infra
                             │
                          LOW VALUE
```

---

# Phase 1: Quick Wins (Low Effort, High Value)

### 1. Prompt Cache Metrics Tracking & Display
* **Value**: Immediate visibility into Anthropic & OpenAI prompt caching cost savings.
* **Target Files**: `providers/anthropic_provider.py`, `providers/openai_provider.py`, `engine.py`, `config.py`

#### Implementation Steps:
1. **Extend Provider Usage Payloads**:
   * **Anthropic**: Parse `cache_creation_input_tokens` and `cache_read_input_tokens` from `message_start` / `message_delta` events.
   * **OpenAI**: Parse `prompt_tokens_details.cached_tokens` from stream completion usage chunks.
2. **Track in Engine**:
   Add `session_cached_tokens` to `MeshEngine`.
3. **Display in Metrics Footer**:
   Update the turn metrics footer in `engine.py`:
   `[1,200 in (850 cached), 450 out | $0.0012 turn, $0.0420 session | TTFT: 120ms, 45.2 tok/s]`

---

### 2. Session Spend Hard Caps & Cost Guard
* **Value**: Prevents runaway loops or sub-agent swarms from overspending API budget.
* **Target Files**: `config.py`, `commands/system_commands.py`, `engine.py`

#### Implementation Steps:
1. **Add Configuration Field**:
   In `config.py`: Add `budgets.spend` (`/config set budget spend <usd>`). Default `0.0` (unlimited).
2. **Pre-Turn Verification**:
   In `engine.py` (`process_inference`): Before making LLM API calls, check:
   ```python
   max_spend = self.config_mgr.config.budgets.spend
   if max_spend > 0.0 and self.session_cost_usd >= max_spend:
       console.print(f"[error]⛔ Session spend limit (${max_spend:.2f}) reached! Turn blocked.[/error]")
       return
   ```

---

### 3. Automatic Git Commits per Turn
* **Value**: Atomic, rollback-safe development. Every file change by the AI is automatically committed to Git.
* **Target Files**: `config.py`, `git_workflow.py`, `engine.py`, `commands/session_commands.py`

#### Implementation Steps:
1. **Config Toggle & Command**:
   Add `/git autocommit [on|off]` command and `git_autocommit: bool` setting in `config.json`.
2. **Post-Turn Auto-Commit Hook**:
   In `engine.py` (`process_inference`): At the end of a turn, if files were edited and `git_autocommit` is enabled:
   * Generate commit message via `git_workflow.generate_commit_message()`.
   * Run `git_workflow.run_git_commit(message, add_all=True)`.
3. **Git Undo Helper**:
   Add `/git undo` command to execute `git reset --soft HEAD~1` and restore previous state.

---

# Phase 2: Core Engineering (Medium Effort, High Value)

### 4. Granular Tool Output Pruning in Conversation History
* **Value**: Prevents massive tool outputs (e.g. 10,000-line test logs) from clogging context history across subsequent turns.
* **Target Files**: `config.py`, `compaction.py`, `engine.py`

#### Implementation Steps:
1. **Add Budget Setting**:
   Add `budgets.tool_output_max` (default `4000` chars) to `/config set budget tool-output-max <chars>`.
2. **Historical Message Slicing**:
   In `compaction.py` / `engine.py`: Create a pass `prune_historical_tool_outputs(messages)`:
   * Keep tool outputs in the *current active turn* at full length.
   * For tool messages in *older turns* exceeding `tool_output_max`, replace the middle lines with:
     `[... Truncated 12,400 chars of historical tool output for context optimization ...]`

---

### 5. Architect / Editor Dual-Model Workflow
* **Value**: Uses a high-reasoning frontier model (e.g. Claude 3.7 Sonnet) for planning and a fast, cheap model (e.g. Claude 3.5 Haiku) for writing code changes.
* **Target Files**: `config.py`, `modes.py`, `engine.py`, `commands/model_commands.py`

#### Implementation Steps:
1. **Add Editor Model Setting**:
   Add `editor_model` to `config.json` (`/switch editor <model_key>`).
2. **Dual-Turn Dispatching**:
   When active mode is `build` and `editor_model` is configured:
   * **Turn 1 (Architect)**: Main model generates solution plan and structured file change specs (using intent schemas or JSON blocks).
   * **Turn 2 (Editor)**: Engine automatically invokes `editor_model` with the change specs to execute `write_file`/`edit_file`/`hash_edit` tool calls directly.

---

### 6. Playwright Headless Browser Tool (`web_browse`)
* **Value**: Allows AI to inspect, test, and debug local web applications (`localhost:3000`) and capture screenshots.
* **Target Files**: `tools/browser_tool.py`, `engine.py`, `requirements.txt`

#### Implementation Steps:
1. **Add Dependencies**:
   Add `playwright` to `requirements.txt`.
2. **Build `WebBrowseTool` (`tools/browser_tool.py`)**:
   Support actions: `navigate`, `click`, `type`, `screenshot`, `get_text`.
   ```python
   class WebBrowseTool(BaseTool):
       name = "web_browse"
       description = "Navigates web pages using a headless browser, interacts with elements, and captures page text/screenshots."
   ```
3. **Register in Engine**:
   Register `WebBrowseTool` in `engine.py` and assign `requires_guard = True`.

---

### 7. Hands-Free Voice Input / Whisper Audio Transcription
* **Value**: Allows users to speak prompts directly in terminal sessions.
* **Target Files**: `tools/voice.py`, `terminal_ui.py`, `requirements.txt`

#### Implementation Steps:
1. **Add Dependency**:
   Add `sounddevice` and `scipy` / `openai` to `requirements.txt`.
2. **Create Voice Recorder (`/voice` or `v` shortcut)**:
   Record audio from default microphone on keypress, transcribe via local Whisper (`faster-whisper`) or OpenAI Audio API, and automatically paste text into `MeshPromptSession`.

---

# Phase 3: Deep Intelligence (Medium/High Effort, High Value)

### 8. External File Watcher & Workspace Hot Invalidation
* **Value**: Keeps Mesh synchronized when files are edited externally in VS Code or Cursor.
* **Target Files**: `file_watcher.py`, `engine.py`, `requirements.txt`

#### Implementation Steps:
1. **Add Dependency**: `watchdog`.
2. **Build Workspace File Watcher**:
   Monitor working directory for `on_modified`, `on_created`, `on_deleted` events.
3. **Invalidate Caches**:
   On file change, automatically trigger `symbol_indexer.index_file(filepath)` and append a light notification (`file_watcher_event`) to `engine.messages`.

---

### 9. Local Code Vector Embeddings & Dense Semantic Search
* **Value**: Search codebase by meaning/intent (*"where is JWT token verification implemented?"*) alongside AST symbol search.
* **Target Files**: `vector_search.py`, `tools/semantic_tool.py`, `requirements.txt`

#### Implementation Steps:
1. **Add Dependency**: `lancedb` or `chromadb` + `fastembed`.
2. **Codebase Chunking & Indexing**:
   Chunk files by AST function/class boundaries and compute vector embeddings in `.mesh/vectors/`.
3. **Expose `search_code_semantic` Tool**:
   Allow assistant to execute natural-language queries over code chunks with similarity scores.

---

### 10. Language Server Protocol (LSP) Diagnostics Tool
* **Value**: Gives the AI real-time compiler, type checker, and lint errors before running tests.
* **Target Files**: `lsp_client.py`, `tools/lsp_tool.py`

#### Implementation Steps:
1. **LSP Stdio Client**:
   Connect via stdio to installed language servers (`pyright-langserver`, `tsserver`, `gopls`, `rust-analyzer`).
2. **Expose `get_code_diagnostics` Tool**:
   Returns real-time type/syntax errors for modified files directly to the model.

---

# Phase 4: Ecosystem Infrastructure (Higher Effort)

### 11. Headless Daemon Mode (HTTP & WebSocket REST API)
* **Value**: Allows VS Code, JetBrains plugins, or web dashboards to use Mesh as an agent backend.
* **Target Files**: `server.py`, `main.py`, `requirements.txt`

#### Implementation Steps:
1. **Add Dependency**: `fastapi`, `uvicorn`.
2. **Add CLI Flag**: `python main.py --server 8080`.
3. **Expose Endpoints**:
   * `POST /api/v1/prompt`
   * `GET /api/v1/status`
   * `WS /api/v1/stream` (Streams Rich tokens & tool execution events in real time).

---

### 12. Event-Driven Webhooks & Git Hook Triggers
* **Value**: Runs Mesh workflows automatically when CI fails or a git pre-commit hook fires.
* **Target Files**: `event_trigger.py`, `.mesh/hooks/`

#### Implementation Steps:
1. **Local Git Hook Integration**:
   Install `.git/hooks/pre-commit` script invoking `python main.py --script .mesh/hooks/pre-commit.txt -n`.
2. **Webhook Endpoint**:
   Expose `/api/v1/webhook` to trigger `/loop` or `/agent squad` on incoming GitHub PR/issue events.

---

## 🚀 Suggested Implementation Sequence

```bash
# Milestone 1: Instant Metrics & Safety (Phase 1)
├── 1. Prompt Cache Metrics (Anthropic & OpenAI)
├── 2. Session Spend Hard Caps
└── 3. Git Auto-Commit per Turn

# Milestone 2: Agent Power & Automation (Phase 2)
├── 4. Tool Output Pruning
├── 5. Architect/Editor Dual-Model
├── 6. Playwright Browser Tool
└── 7. Voice Input (Whisper)

# Milestone 3: Deep Workspace Intelligence (Phase 3 & 4)
├── 8. File Watcher
├── 9. Vector Code Search
├── 10. LSP Diagnostics Tool
└── 11. Headless Daemon API
```