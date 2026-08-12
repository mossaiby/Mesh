# ⚡ Mesh

**v1.0.0**

A modular, text-based AI CLI built in Python for local and cloud-hosted LLMs. Designed for developer productivity with **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **sub-agent swarm workflows**, **hash-anchored & fuzzy file editing**, **post-edit linter hooks**, **Git native tools**, **session checkpointing**, and **semantic context compaction**.

---

## 🚀 Quick Start

### 1. Prerequisites & Installation

#### Required
* **Python 3.10 or higher**

#### Optional Linters & Formatters (for Post-Edit Hooks)
Mesh automatically detects installed linters on your system `PATH` to validate code immediately after file edits. If a linter is not installed, Mesh gracefully skips the check:
* **Python:** `ruff` or `flake8`
* **JavaScript / TypeScript:** `eslint`
* **Rust:** `cargo` (`cargo check`)
* **Go:** `gofmt`

> **Note on MCP Servers:** Runtimes like `npx` (Node.js) or `uvx` (`uv`) are **not** required by Mesh itself. They are only needed if you choose to configure external third-party stdio MCP servers in `mcps.json` that depend on them.

```bash
git clone https://github.com/mossaiby/Mesh.git
cd Mesh
pip install -r requirements.txt
```

### 2. Configure API Keys
Set environment variables for cloud or local providers (or configure endpoints in `models.json`):

```bash
export OPENAI_API_KEY="sk-..."
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-..."
```

### 3. Launch Mesh
```bash
# Interactive REPL
python main.py

# Run a script file on startup (interactive or headless)
python main.py script.txt
python main.py --file script.txt --non-interactive
```

---

## 🛠️ Slash Commands Reference

Slash commands are organized into logical categories. Type **`/help`** to view all categories, or **`/help <command>`** (e.g. `/help git`) for specific usage instructions.

### ━━━ Models & Settings ━━━
| Command | Description |
| :--- | :--- |
| **`/status`** | Display active model, tools, MCPs, symbol count, branch, session token usage, USD cost, and context status. |
| **`/models`** | List configured models (`/models`), discover remote endpoints (`/models discover`), or batch-add models (`/models add openrouter *free*`). |
| **`/switch`** | Switch active model interactively using arrow keys, or directly via model key (`/switch <key>`). |
| **`/config`** | Toggle system automation: `/config proxy`, `/config repair`, `/config hooks`, `/config compact`. |
| **`/mode`** | Switch operating mode (`/mode build`, `/mode plan`, `/mode review`, `/mode yolo`). |
| **`/guard`** | Configure tool-call safety guard risk assessment (`/guard on`, `/guard mode supervised|autonomous`). |

### ━━━ Agents & Workflows ━━━
| Command | Description |
| :--- | :--- |
| **`/agent`** | Sub-agent swarm & reasoning workflows: `/agent explore`, `/agent squad`, `/agent consensus`, `/agent delegate`, `/agent advisor`. |
| **`/loop`** | Iterative auto-test/fix loop (`/loop <test_cmd>`). |
| **`/jobs`** | View or manage async background processes (`/jobs log <id>`, `/jobs stop <id>`, `/jobs clear`). |

### ━━━ Workspace & Developer Tools ━━━
| Command | Description |
| :--- | :--- |
| **`/cd`** | Change working directory & automatically sync allowed directories, project rules (`PROJECT.md`), and AST symbol index. |
| **`/project`** | View or reload workspace project rules (`PROJECT.md`) or repository architecture map (`/project map`). |
| **`/git`** | Vendor-agnostic Git workflow: `/git status`, `/git diff`, `/git commit` (AI auto-commit), `/git push`, `/git branch`. |
| **`/diff`** | View colorized unified diffs of file edits (`/diff`), or revert recent edits (`/diff undo`). |
| **`/shell` \| `!`** | Direct shell execution (`! <cmd>`) — runs directly without modifying conversation history or triggering LLM turns. |
| **`/python` \| `#`** | Direct Python execution (`# <code>`) inside a persistent session namespace without modifying conversation history. |
| **`/script`** | Execute commands and prompts line-by-line from a script file (`/script <file.txt>`). |

### ━━━ Memory & Knowledge ━━━
| Command | Description |
| :--- | :--- |
| **`/goal`** | View, set, or update pinned session goals folded directly into the system prompt. |
| **`/note`** | View or edit persistent Markdown project notes (`notes.md`). |
| **`/memory`** | Manage persistent key-value facts (`memory.json`) and semantic meaning search. |
| **`/dream`** | Interactively extract durable notes, memory facts, and skills from conversation history. |
| **`/reflexion`** | View or distill cross-session error lessons into durable system rules (`/reflexion distill`). |

### ━━━ Context & Integration ━━━
| Command | Description |
| :--- | :--- |
| **`/context`** | Display raw conversation history, active tool names, and MCP status. |
| **`/system`** | Show current system prompt (rendered in Markdown) or set it (`/system <text>`). |
| **`/tools`** | List registered tools with full detailed descriptions and schemas, or toggle tool inclusion (`/tools on|off`). |
| **`/skills`** | Enable, disable, or register custom system skills. |
| **`/dirs`** | Manage authorized directory paths enforced by `PermissionManager`. |
| **`/mcps`** | View connected Model Context Protocol servers or toggle tools (`/mcps on|off`). |
| **`/compact`** | Semantically compact older conversation context using the LLM. |

### ━━━ Session & System ━━━
| Command | Description |
| :--- | :--- |
| **`/help`** | Show command categories or specific command usage (`/help <command>`). |
| **`/checkpoint`** | Session state management: `/checkpoint save <tag>`, `/checkpoint fork <branch>`, `/checkpoint restore <tag>`. |
| **`/clear`** | Clear conversation history while preserving system prompt, goal, and skills. |
| **`/retry`** | Retry the last LLM response turn. |
| **`/debug`** | Toggle debug mode to show Chain of Thought (CoT) and sub-agent execution traces. |
| **`/exit`** | Gracefully terminate background processes and exit Mesh. |

---

## 🌟 Key Capabilities

### 🎯 Hash-Anchored & Fuzzy Block File Editing
* **Hash-Anchored Edits (`hash_edit`):** Passing `show_hashes: true` to `read_file` returns line-numbered content with stable 4-character hashes (e.g. `L12|a3f1| def foo():`). Using `hash_edit` verifies line hashes before applying changes, guaranteeing safe, drift-free replacements.
* **Fuzzy Block Matching (`edit_file`):** If exact string replacement fails in `edit_file` due to minor indentation or whitespace variations, Mesh calculates sequence similarity using `difflib.SequenceMatcher`. If similarity is $\ge 85\%$, the target block is replaced automatically.

### ⚡ Post-Edit Linter Hooks (`/config hooks`)
* **Automated Post-Edit Checks:** Automatically detects installed linters (`ruff`, `flake8`, `eslint`, `cargo check`, `gofmt`) using `shutil.which()` after file edits (`write_file`, `edit_file`, `hash_edit`).
* **Real-time Repair:** Captures non-zero linter outputs and appends `_linter_feedback` directly into the tool output, allowing the LLM to fix syntax errors or broken imports in the exact same turn.
* **Graceful Fallback:** If linters aren't installed on the system, Mesh skips checks without errors or delays.

### 💬 Stream Rendering & Transient Status Indicators
* **Clean Real-Time Streaming:** Markdown responses stream live using Rich.
* **Transient Status Indicators:** Displays clean `Waiting...` and `Thinking...` status indicators. If a turn finishes without text output (such as a pure tool execution turn), status indicators are erased automatically from the terminal rather than leaving stale text behind.

### 🔌 Multi-Provider, Model Discovery & Cost Metering
* **REST Compatibility:** Connect to OpenAI, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible backend.
* **Remote Model Discovery:** Query provider `/v1/models` endpoints dynamically (`/models discover`) and batch-add models using wildcard patterns (`/models add openrouter *free*`).
* **Real-Time $ USD Cost Tracking:** Editable `pricing.json` tracks exact prompt/completion token usage and cumulative session cost in USD in response headers and `/status`.

### ⚡ REPL Power Shortcuts (`!`, `#`, `@filename`, `/cd`)
* **`! <command>` / `/shell <command>`:** Runs shell commands directly from the REPL without LLM overhead or safety guard prompts. Executes cleanly without modifying conversation history or triggering LLM turns.
* **`# <code>` / `/python <code>`:** Executes Python code snippets directly inside a persistent session namespace without altering chat context.
* **`/cd <path>`:** Changes working directory and automatically syncs `PermissionManager` allow-lists, codebase symbol indexer, `PROJECT.md` rules, and Repository Map.
* **Autocomplete & `@filename` Auto-Attach:** Typing `@` in prompts triggers Tab-completion for workspace files (`@src/engine.py`). Mentioning files automatically reads and attaches their formatted code blocks directly into the prompt payload.
* **Graceful `Ctrl+C` Turn & Shell Cancellation:** Pressing `Ctrl+C` during streaming or shell command execution cancels *only* the active child process or turn, cleans up context, and returns safely to the prompt without exiting Mesh.

### 🕸️ Automated Repository Map (Dependency Graph & PageRank)
* **Token-Compact Codebase Map (`repo_map.py` / `/project map`):** Pre-computes a PageRank dependency graph across codebase symbols and injects a 500-token repository architecture map into the system prompt.

### 🐝 Sub-Agent Swarms & Advanced Reasoning (`/agent`)
* **Speculative Swarm Exploration (`/agent explore`):** Spawns $N$ parallel sub-agents with distinct strategies to attempt a task, then uses an LLM Judge pass to synthesize the winning solution.
* **Autonomous Task Squad (`/agent squad`):** Executes a 4-stage pipeline of persona sub-agents: **Architect** (design) ➔ **Coder** (implementation) ➔ **Test Engineer** (testing) ➔ **Security Auditor** (code audit).
* **Adversarial Consensus (`/agent consensus`):** Runs a 2-stage red-team audit where Model A proposes a patch, Model B audits for edge-cases/flaws, and a Referee synthesizes a verified recommendation.
* **Recursive Delegation (`/agent delegate`):** Hands off multi-step tasks to autonomous sub-agent loops with configurable recursion depth limits.

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints, model configurations, auto-compaction rules, and global system prompts.

```json
{
  "active_model": "llama3-groq",
  "system_prompt": "You are Mesh, a helpful, precise, and efficient AI assistant running inside an interactive terminal CLI.",
  "auto_compact": true,
  "auto_compact_threshold": 0.75,
  "max_delegation_depth": 2,
  "advisor_model": null,
  "guard_enabled": true,
  "guard_model": "lmstudio:local-1b-model",
  "guard_autonomy": "supervised",
  "providers": {
    "groq": {
      "name": "Groq Cloud",
      "base_url": "https://api.groq.com/openai/v1",
      "api_key_env": "GROQ_API_KEY"
    },
    "lmstudio": {
      "name": "Local LM Studio",
      "base_url": "http://localhost:1234/v1",
      "api_key_env": "LOCAL_API_KEY"
    }
  },
  "models": {
    "llama3-groq": {
      "name": "Llama 3 70B (Groq)",
      "provider": "groq",
      "model_id": "llama-3.3-70b-versatile",
      "context_window": 128000
    }
  }
}
```

### `mcps.json`
Configures Model Context Protocol (MCP) stdio servers.

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["--with", "mcp<1.0.0", "mcp-server-sqlite", "--db-path", "./data.db"]
    }
  }
}
```

---

## 📁 Project Structure

```text
Mesh/
├── requirements.txt           # Project Python dependencies
├── models.json                # Provider endpoints and model configurations
├── pricing.json               # Per-1M token pricing tables for USD cost tracking
├── mcps.json                  # Model Context Protocol server definitions
├── skills.json                # Declarative skills configuration
├── memory.json                # Persistent key-value memory storage
├── reflexion.json             # Cross-session reflexion error log & lessons
├── notes.md                   # Persistent Markdown notes
├── version.py                 # Single source of truth for the app version
├── theme.py                   # Shared Rich theme & console instance
├── config.py                  # Configuration manager and Pydantic schemas
├── pricing.py                 # Real-time USD cost & token metering manager
├── context_mentions.py        # @filename prompt mention parser & attachment engine
├── python_executor.py         # Persistent session namespace Python executor (# code)
├── engine.py                  # Central MeshEngine orchestration & turn loop
├── subagent.py                # Sub-Agent Proxy distillation engine
├── delegation.py              # Task Delegation engine
├── explore.py                 # Speculative Swarm Branch Exploration engine
├── tool_synthesis.py          # Dynamic Tool Synthesis and AST validation
├── consensus.py               # Adversarial Multi-Model Consensus engine
├── squad.py                   # 4-stage Multi-Role Task Squad pipeline
├── reflexion.py               # Cross-Session Reflexion logging & distillation
├── symbol_search.py           # Universal Tree-sitter AST codebase symbol indexer
├── repo_map.py                # PageRank repository dependency graph map generator
├── checkpoint.py              # Session Checkpointing & Branching manager
├── file_history.py            # Unified Diff Previews & File Rollback tracker
├── hooks.py                   # Automated Post-Edit Linter & Formatter Hooks
├── test_loop.py               # Iterative Auto-Test/Fix Loop harness
├── jobs.py                    # Async Background Subprocess Manager
├── git_workflow.py            # Git Native Engine & AI Conventional Commit Generator
├── memory_search.py           # Sub-agent-based semantic memory search
├── self_heal.py               # Self-healing tool-error recovery
├── advisor.py                 # Advisor engine
├── guard.py                   # Tool-call Safety Guard
├── modes.py                   # Operating modes (Plan/Build/Review/YOLO)
├── compaction.py              # Semantic context window compaction module
├── dream.py                   # /dream conversation analysis & knowledge extraction
├── terminal_ui.py             # Prompt_toolkit session with Tab-completion
├── project_rules.py           # Project instructions & rules loader (PROJECT.md)
├── main.py                    # Clean CLI entry point and REPL loop
├── custom_tools/              # Directory for dynamically synthesized tools
├── providers/
│   ├── __init__.py
│   └── openai_provider.py     # Async OpenAI-compatible client wrapper
├── render/
│   ├── __init__.py
│   └── stream_renderer.py     # Rich Markdown & CoT streaming renderer
├── tools/
│   ├── __init__.py            # Tool exports
│   ├── base.py                # BaseTool class
│   ├── registry.py            # Central tool execution dispatcher
│   ├── permissions.py         # PermissionManager and directory authorization
│   ├── native_tools.py        # File, glob, and shell command tools
│   ├── web_tools.py           # Key-less web search & fetch tools
│   ├── memory_tool.py         # Key-value memory tool
│   ├── note_tool.py           # Markdown note manager tool
│   ├── todo_tool.py           # Multi-step task tracking tool
│   ├── ask_tool.py            # Interactive decision tool
│   ├── delegate_tool.py       # delegate_task tool
│   ├── goal_tool.py           # goal tool
│   ├── advisor_tool.py        # consult_advisor tool
│   ├── explore_tool.py        # explore_branches tool
│   ├── synthesis_tool.py      # synthesize_tool tool
│   ├── consensus_tool.py      # consult_consensus tool
│   ├── symbol_tool.py         # search_symbols AST search tool
│   ├── job_tool.py            # job tool (background processes)
│   └── git_tool.py            # git_status, git_diff, git_commit, git_push, git_branch tools
├── commands/
│   ├── __init__.py
│   ├── registry.py            # Slash command registry with categories
│   ├── agent_commands.py      # /agent, /loop, /jobs, /guard, /mode
│   ├── model_commands.py      # /models, /switch
│   ├── session_commands.py    # /cd, /shell (!), /python (#), /checkpoint, /diff, /git, /goal, /note, /memory, /dream, /script, /project, /reflexion
│   └── system_commands.py     # /help, /status, /config, /context, /system, /tools, /skills, /dirs, /mcps, /clear, /retry, /debug, /exit
├── mcp/
│   ├── __init__.py
│   └── client.py              # Stdio JSON-RPC MCP client
└── skills/
    ├── __init__.py
    ├── base.py                # Skill base class
    ├── registry.py            # Skill manager
    └── code_skill.py          # Python coding skill implementation
```

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).
