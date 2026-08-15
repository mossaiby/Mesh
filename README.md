# ⚡ Mesh: A Modern, Modular and Hackable AI Harness

*Developed by* **Farshid Mossaiby**

A modern, modular and hackable AI CLI harness written in Python. Mesh connects to any OpenAI- or Anthropic-compatible model provider and wraps it with a full agentic toolset: file editing, shell access, web search, MCP servers, sub-agent delegation, persistent memory, session save/resume, Markdown logging, automated test-and-repair loops, a comprehensive test suite, and a safety layer that gates risky tool calls — all driven from a single terminal chat loop.

---

## 🌟 Key Features

- **Provider Management via CLI (`/providers`)** — Add, list, test, configure custom headers, or remove model providers directly from the terminal without manual editing of `config.json`.
- **Persistent Command History (`/history`)** — Cross-session terminal history persisted on disk in `.mesh/history.txt` with `↑` / `↓` arrow-key recall and inspection/clearing commands.
- **Multi-Provider Support with Exponential Backoff & Retry** — Talk to OpenAI, Anthropic, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint, all configured in `config.json`. Includes customizable exponential backoff with randomized jitter (`/config set retry`) for resilient API communication.
- **Concurrent Read-Only Tool Execution** — When a model requests multiple tool calls in a turn, contiguous read-only operations (`read_file`, `glob_files`, `web_search`, `web_fetch`, `search_symbols`, `calculator`, `git_status`, `git_diff`, memory queries) run in parallel via `asyncio.gather()`, while mutating actions execute sequentially with strict state safety.
- **Background Symbol Indexing with Persistent Disk Cache (`.mesh/symbols.cache.json`)** — Polyglot Tree-sitter AST symbol indexing across 11 languages (Python, JS/TS, Rust, Go, C/C++, Java, C#, PHP, Ruby). Caches parsed symbols, line numbers, and docstrings to disk in `.mesh/symbols.cache.json` with `mtime`/size validation and runs incremental directory scans asynchronously in a background thread pool without blocking REPL interactions.
- **Accurate Token Accounting with `tiktoken`** — BPE tokenization for OpenAI/Anthropic/OpenRouter models with LRU encoding caching and graceful character-count fallback (`CHARS_PER_TOKEN = 4`) for precise context threshold triggers and compaction.
- **IDE Config Auto-Completion & JSON Schema (`$schema`)** — Native Draft 2020-12 JSON Schema generation (`config.schema.json` and `/config schema`) provides instant autocomplete, parameter descriptions, and type validation in VS Code, Cursor, JetBrains, and Neovim.
- **Modular Core Architecture** — Clean separation of concerns between `InferenceCoordinator` (turn loops, streaming, auto-routing, metrics) and `ToolOrchestrator` (batching, concurrent execution, logging, reflexion).
- **Disk-Backed Session Save & Resume (`/session`)** — Save full conversation state, goals, todo graph, notes, memory, active mode, metrics, and checkpoints to disk under `sessions/<name>.json`. Resume anytime with `/session load <name>`, `python main.py --session <name>`, or `python main.py --resume`.
- **Markdown Session Logging (`/log`)** — Stream clean, structured Markdown transcripts of user prompts, assistant responses, and tool executions to a log file (`session.md` or custom path) via CLI `--log` or `/log on <path>`.
- **Operating Modes (`/mode`)** — `build` (full access, default), `plan` and `review` (read-only workspace inspection, no writes/shell/delegation/MCP), `chat` (conversational Q&A, brainstorming, and research with web search, fetch, calculator, advisor, and memory), and `yolo` (full access, no confirmation prompts for ambiguous-risk actions — high-risk actions are still always blocked).
- **Safety Guard (`/guard`)** — An LLM-backed risk assessor that reviews tool calls before execution, can run in `supervised` or `autonomous` mode, supports per-session tool trust, and always blocks genuinely high-risk actions regardless of mode.
- **Directory Permissions (`/dirs`)** — A `PermissionManager` enforces a working-directory allow-list for every file/shell tool. Out-of-bounds access triggers an interactive Allow Once / Always Allow / Deny prompt.
- **Model Context Protocol (`/mcps`)** — A native stdio/URL MCP client (`mcps.json`) that discovers and calls tools from external MCP servers (filesystem, SQLite, GitHub, etc.), with global and per-server toggles.
- **Sub-Agent & Multi-Agent Workflows (`/agent`)** — Spin up focused sub-agents for task delegation (`delegate`), branching exploration (`explore`), parallel task squads (`squad`), multi-model consensus (`consensus`), and second-opinion advisory review (`advisor`).
- **Autonomous Test/Fix Loop (`/loop`)** — Runs a test or build command, and on failure automatically delegates a repair sub-agent to fix the code and retries, up to a configurable number of iterations.
- **Declarative Skills (`/skills`)** — Package specialized system prompts and tools into reusable skills, loaded from `skills.json` or custom Python classes (see `skills/code_skill.py`).
- **Persistent Memory & Notes** — A key-value `memory` store with semantic search (`/memory`), a running Markdown `notes.md` (`/note`), pinned session goals with completion criteria (`/goal`), and multi-step task tracking (`todo`).
- **Context Engineering** — Semantic context compaction (`/compact`) that summarizes older turns without breaking active tool-call pairs, a Sub-Agent Distiller that summarizes large tool outputs before they hit context, and repository maps (`/project map`) built from PageRank symbol centrality.
- **Session Continuity & Rollback** — Save and branch conversation state with checkpoints (`/checkpoint save|fork|restore|list`), file-edit history with undo (`/diff undo`), and reflexion (`/reflexion`) that distills cross-session error lessons.
- **Native Tool Suite** — File ops (`read_file`, `write_file`, `edit_file`, `hash_edit`, `glob_files`), shell execution, key-less web search/fetch, Git tools, a calculator, and an `ask_user` tool for human-in-the-loop decisions.
- **Test-Driven Reliability** — Automated `pytest` test suite verifying concurrency partitioning, tool safety, dependency DAGs, file hash drift protection, permission isolation, and session roundtrip persistence.
- **Rich Terminal UI** — Real-time Markdown streaming with syntax highlighting, toggleable Chain-of-Thought display (`/debug`), and an interactive arrow-key model/menu switcher with context-aware tab completion.

---

## 🏗️ Architecture Overview

```
                                        ┌─────────────────────────┐
                                        │       User (CLI)        │
                                        └─────────────┬───────────┘
                                                      │
                                        ┌─────────────▼───────────┐
                                        │ MeshEngine (engine.py)  │
                                        └───┬─────────────────┬───┘
                                            │                 │
                      ┌─────────────────────▼─┐             ┌─▼─────────────────────┐
                      │ InferenceCoordinator  │             │   ToolOrchestrator    │
                      │(inference_coordinator)│             │  (tool_orchestrator)  │
                      └─────────────┬─────────┘             └─┬───────────────────┬─┘
                                    │                         │                   │
      ┌──────────────────┬──────────┴──┬──────────┬───────────┴────┐        ┌─────▼──────────────┐
      │                  │             │          │                │        │ SymbolIndexer      │
┌─────┴──────┐  ┌────────┴──────┐ ┌────┴───┐ ┌────┴───┐ ┌──────────┴───┐    │ (.mesh disk cache) │
│ Providers  │  │ Tool Registry │ │ Safety │ │ Skills │ │ MCP Client   │    └────────────────────┘
│ (Retry &   │  │ & Permissions │ │ Guard  │ │        │ │ (mcps.json)  │
│ Backoff)   │  │               │ │        │ │        │ │              │
└────────────┘  └───────────────┘ └────────┘ └────────┘ └──────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python **3.10** or higher
- Node.js / `npx` (optional, for Node-based MCP servers)
- `uv` / `uvx` (optional, for Python-based MCP servers)

### 2. Installation

```bash
git clone https://github.com/mossaiby/Mesh.git
cd Mesh
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

### 3. Configure API Keys

Set environment variables for whichever providers you use (referenced by `api_key_env` in `config.json`):

```bash
# Cloud providers
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-..."

# Local providers (optional)
export OLLAMA_API_KEY="dummy"
export LOCAL_API_KEY="dummy"
```

### 4. Run Mesh

```bash
# Start an interactive CLI session
python main.py

# Enable session Markdown logging on launch
python main.py --log session.md

# Resume the most recently saved disk session
python main.py --resume

# Load or create a specific named disk session
python main.py --session my-feature

# Run a script file non-interactively
python main.py path/to/script.txt --non-interactive
```

---

## 🛠️ Slash Commands Reference

### Models & Providers
| Command | Description |
| --- | --- |
| `/providers [list\|add\|remove\|test\|header] <args>` | List, add, remove, test, or configure model providers live from the CLI |
| `/models [discover\|add\|remove] [<args>]` | List, discover, add, or remove configured models |
| `/switch [auto\|router\|<model_key>]` | Switch active model or mode: `/switch [auto\|router\|<model_key>]` |
| `/config [distill\|proxy\|repair\|hooks\|compact\|thinking\|effort\|tokens\|cost\|statistics\|schema\|set] <args>` | View or configure system settings, retry parameters, and JSON schemas |
| `/guard [on\|off\|mode\|model\|trust] <args>` | View or configure safety guard settings |
| `/mode [plan\|build\|review\|chat\|yolo]` | View or switch operating mode: `/mode [plan\|build\|review\|chat\|yolo]` |

### Session & System
| Command | Description |
| --- | --- |
| `/help` | Display available slash commands and usage help: `/help [<command>]` |
| `/status` | Display Mesh system status, background indexing state, active model, and configuration overview: `/status` |
| `/history [<limit>\|clear]` | View or clear interactive command history (.mesh/history.txt) |
| `/clear` | Clear conversation context window (preserves system prompt and skills): `/clear` |
| `/retry` | Retry the last assistant turn: `/retry` |
| `/debug [on\|off]` | View or toggle debug mode (CoT & tool execution traces): `/debug [on\|off]` |
| `/session [save\|load\|list\|delete] [<name>]` | Save, load, list, or delete disk session states in `sessions/` |
| `/log [on\|off\|status\|<filepath>]` | View or configure Markdown session logging |
| `/checkpoint [save\|fork\|restore\|list] <args>` | Save, fork, restore, or list session checkpoints |
| `/exit` | Close active sessions and exit Mesh: `/exit` |

### Context & Integration
| Command | Description |
| --- | --- |
| `/context` | Display conversation context window, active tools, and MCP server states |
| `/system [<text>]` | View or update the system prompt (or `/system clear`) |
| `/tools [on\|off]` | List registered tools and schemas, or toggle tool execution |
| `/skills enable\|disable <name>` | List registered skills, or toggle a skill |
| `/dirs [add\|remove\|clear] [<path>]` | View or modify allowed working directories |
| `/mcps [on\|off\|enable\|disable] [<server>]` | View or toggle Model Context Protocol servers |
| `/compact` | Semantically summarize older conversation history to free context tokens |

### Agents & Workflows
| Command | Description |
| --- | --- |
| `/agent [explore\|squad\|consensus\|delegate\|advisor] <args>` | Run sub-agent swarm and reasoning workflows |
| `/loop <test_or_build_command>` | Run iterative auto-test and repair loop |
| `/jobs [log\|stop\|clear] [<job_id>]` | View or manage background job processes |

### Memory & Knowledge
| Command | Description |
| --- | --- |
| `/goal [<text>] [\| criteria]`, `/goal done <#>`, `/goal clear` | View, set, or manage pinned session goal |
| `/note [append <text>\|clear]` | View or edit persistent Markdown notes |
| `/memory [save\|get\|list\|search\|delete\|clear] <args>` | View or edit persistent memory key-value store |
| `/dream` | Analyze conversation transcript and extract persistent notes, memory facts, and skills |
| `/reflexion [distill\|clear]` | View or distill cross-session error lessons |

### Workspace & Developer Tools
| Command | Description |
| --- | --- |
| `/cd <path>` | Change working directory and reload workspace context |
| `/shell <cmd>` or `!<cmd>` | Execute shell command directly (bypasses LLM) |
| `/python <code>` or `#<code>` | Execute Python snippet directly (bypasses LLM) |
| `/script <file.txt>` | Execute commands and prompts line-by-line from script file |
| `/project [map\|reload]` | View or reload project rules and repository map |
| `/diff` / `/diff undo` | Display unified file diff or revert last edit |
| `/git [status\|diff\|commit\|push\|branch]` | Run native Git commands |

---

## ⚙️ Configuration File (`config.json`)

```json
{
  "$schema": "./config.schema.json",
  "active_model": "anthropic:claude-3-7-sonnet-20250219",
  "system_prompt": "You are Mesh, a helpful, precise, and efficient AI assistant...",
  "auto_compact": true,
  "auto_compact_threshold": 0.75,
  "max_delegation_depth": 2,
  "advisor_model": null,
  "guard_enabled": true,
  "guard_model": null,
  "guard_autonomy": "supervised",
  "router_model": null,
  "network_proxy": null,
  "thinking": true,
  "effort": "medium",
  "show_tokens": true,
  "show_cost": true,
  "show_statistics": true,
  "timeouts": {
    "web": 15.0,
    "shell": 30.0,
    "mcp": 60.0,
    "linter": 10.0,
    "python": 10.0,
    "api": 12.0
  },
  "budgets": {
    "web": 8000,
    "repo-map": 500,
    "dream": 12000,
    "git-diff": 4000,
    "symbol": 30
  },
  "turns": {
    "agent": 6,
    "engine": 10,
    "loop": 5,
    "depth": 2,
    "branches": 3
  },
  "repair_settings": {
    "retries": 2,
    "delay": 0.75
  },
  "retry_settings": {
    "retries": 3,
    "initial-delay": 1.0,
    "max-delay": 30.0,
    "backoff-factor": 2.0,
    "jitter": true
  },
  "compaction_settings": {
    "minkeep": 2
  },
  "logging": {
    "enabled": false,
    "filepath": "session.md"
  }
}
```

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
