# ⚡ Mesh

**v1.0.0**

A modular, text-based AI CLI built in Python for local and cloud-hosted LLMs. Designed for developer productivity with **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **sub-agent swarm workflows**, **Git native tools**, **post-edit linter hooks**, **session checkpointing**, and **semantic context compaction**.

---

## 🚀 Quick Start

### 1. Prerequisites & Installation
* Python **3.10** or higher
* Node.js / `npx` (optional, for Node-based MCP servers)
* `uv` / `uvx` (optional, for Python-based MCP servers)

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

| Command | Description |
| :--- | :--- |
| **`/status`** | Display active model, tools, MCPs, symbol count, branch, and context status. |
| **`/models [discover\|add]`** | List configured models, query endpoints (`/models discover`), or batch-add models (`/models add openrouter *free*`). |
| **`/switch [key]`** | Switch active model using cross-platform arrow keys or model key. |
| **`/agent <subcmd>`** | Sub-agent swarms: `/agent explore` (branch search), `/agent squad` (4-stage pipeline), `/agent consensus` (audit), `/agent delegate` (handoff), `/agent advisor` (opinion). |
| **`/git [cmd]`** | Vendor-agnostic Git workflow: `/git status`, `/git diff`, `/git commit` (AI auto-commit), `/git push`, `/git branch`. |
| **`/config <subcmd>`** | Toggle automation: `/config proxy`, `/config repair`, `/config hooks`, `/config compact`. |
| **`/mode [plan\|build\|review\|yolo]`** | Switch operating mode (Build=full, Plan/Review=read-only, YOLO=no prompts). |
| **`/guard [on\|off]`** | Configure tool-call safety guard risk assessment (`low`/`medium`/`high`). |
| **`/checkpoint <subcmd>`** | Session state management: `/checkpoint save <tag>`, `/checkpoint fork <branch>`, `/checkpoint restore <tag>`. |
| **`/diff [undo]`** | View colorized unified diffs of file edits (`/diff`), or revert the last file edit (`/diff undo`). |
| **`/jobs [log\|stop\|clear]`** | View background servers/watchers (`/jobs`), tail logs (`/jobs log <id>`), or stop process (`/jobs stop <id>`). |
| `/loop <test_cmd>` | Run an automated iterative test-fix loop until all tests pass green. |
| `/script <file.txt>` | Execute commands and prompts line-by-line from a script file. |
| `/project [reload]` | View or reload workspace project rules (`PROJECT.md`). |
| `/goal <text>` | View, set, or update pinned session goals folded directly into system prompt. |
| `/reflexion [distill\|clear]` | View or distill cross-session error lessons into durable system rules. |
| `/context` | Display raw conversation history, active tool schemas, and MCP statuses. |
| `/system [text]` | View, update, or clear the live system prompt. |
| `/memory` | Manage persistent key-value facts (`memory.json`) and semantic meaning search. |
| `/note` | Manage persistent Markdown project notes (`notes.md`). |
| `/dream` | Interactively extract durable notes, memory facts, and skills from conversation history. |
| `/mcps` | View connected Model Context Protocol servers or toggle tools. |
| `/skills` | Enable, disable, or register custom system skills. |
| `/tools` | View registered tools or toggle global tool execution. |
| `/dirs` | Manage authorized directory paths enforced by `PermissionManager`. |
| `/compact` | Semantically summarize older conversation context using the LLM. |
| `/debug [on\|off]` | Toggle debug mode to show Chain of Thought (CoT) and sub-agent traces. |
| `/clear` | Clear conversation history while preserving system prompt, goal, and skills. |
| `/exit` | Gracefully terminate background processes and exit Mesh. |

---

## 🌟 Key Capabilities

### 🔌 Multi-Provider & Model Discovery
* **REST Compatibility:** Connect to OpenAI, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible backend.
* **Remote Model Discovery:** Query provider `/v1/models` endpoints dynamically (`/models discover`) and batch-add models using wildcard patterns (`/models add openrouter *free*`).

### 🐝 Sub-Agent Swarms & Advanced Reasoning (`/agent`)
* **Speculative Swarm Exploration (`/agent explore`):** Spawns $N$ parallel sub-agents with distinct strategies to attempt a task, then uses an LLM Judge pass to synthesize the winning solution.
* **Autonomous Task Squad (`/agent squad`):** Executes a 4-stage pipeline of persona sub-agents: **Architect** (design) ➔ **Coder** (implementation) ➔ **Test Engineer** (testing) ➔ **Security Auditor** (code audit).
* **Adversarial Consensus (`/agent consensus`):** Runs a 2-stage red-team audit where Model A proposes a patch, Model B audits for edge-cases/flaws, and a Referee synthesizes a verified recommendation.
* **Recursive Delegation (`/agent delegate`):** Hands off multi-step tasks to autonomous sub-agent loops with configurable recursion depth limits.

### 🛠️ Developer & Codebase Intelligence
* **Git Native Workflow (`/git`):** Pure, vendor-agnostic Git tools (`git_status`, `git_diff`, `git_commit`, `git_push`, `git_branch`). Running `/git commit` automatically generates conventional commit messages from `git diff`.
* **Async Background Jobs (`job` / `/jobs`):** Spawns background servers/watchers (`npm run dev`, `cargo watch`, `pytest --watch`) asynchronously without timing out or blocking Mesh.
* **Post-Edit Linter Hooks (`/config hooks`):** Runs background linters/formatters (`ruff`, `eslint`, `black`, `cargo check`, `gofmt`) after file edits and feeds warnings back to the LLM to fix syntax errors in real-time.
* **Iterative Auto-Test Loop (`/loop <command>`):** Runs a test command (`pytest`, `npm test`). If tests fail, Mesh captures errors, spawns repair sub-agents, modifies code, and re-tests until green.
* **AST Symbol Search (`search_symbols`):** Zero-vector AST parsing indexes classes, functions, and docstrings across workspace Python files for instant navigation.
* **Diff Previews & File Rollback (`/diff`, `/diff undo`):** Displays colorized unified diffs (`-`/`+`) for file mutations and maintains a session undo stack allowing instant rollback of recent file edits.
* **Autonomous Tool Synthesis (`synthesize_tool`):** Writes, AST-validates, saves, and dynamically registers new Python tools in `custom_tools/` at runtime.

### 🛡️ Safety, Modes & Error Recovery
* **Operating Modes (`/mode`):** Switch between **Build** (default full access), **Plan** / **Review** (read-only enforcement at both schema and execution levels), and **YOLO** (autonomous auto-approval for ambiguous risk).
* **Safety Guard (`/guard`):** Risk-assesses shell commands, file writes, and MCP tools before execution (`low`/`medium`/`high` risk classification).
* **Self-Healing Tool Repair (`/config repair`):** Mechanical retries for transient failures + LLM-assisted argument repair for malformed tool calls.
* **Cross-Session Reflexion Journal (`/reflexion`):** Captures tool failures and user corrections across sessions, distilling them into durable lessons injected into the system prompt.

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints and model configurations, plus a single global system prompt shared by all models.

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
├── mcps.json                  # Model Context Protocol server definitions
├── skills.json                # Declarative skills configuration
├── memory.json                # Persistent key-value memory storage
├── reflexion.json             # Cross-session reflexion error log & lessons
├── notes.md                   # Persistent Markdown notes
├── version.py                 # Single source of truth for the app version
├── theme.py                   # Shared Rich theme & console instance
├── config.py                  # Configuration manager and Pydantic schemas
├── engine.py                  # Central MeshEngine orchestration & inference turn loop
├── subagent.py                # Sub-Agent Proxy distillation engine
├── delegation.py              # Task Delegation engine
├── explore.py                 # Speculative Swarm Branch Exploration engine
├── tool_synthesis.py          # Dynamic Tool Synthesis and AST validation
├── consensus.py               # Adversarial Multi-Model Consensus engine
├── squad.py                   # 4-stage Multi-Role Task Squad pipeline
├── reflexion.py               # Cross-Session Reflexion logging & distillation
├── symbol_search.py           # Zero-vector AST codebase symbol indexer
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
│   ├── registry.py            # Slash command registry
│   ├── agent_commands.py      # /agent (explore, squad, consensus, delegate, advisor), /loop, /hooks, /jobs, /guard, /mode
│   ├── model_commands.py      # /models, /switch
│   ├── session_commands.py    # /checkpoint (save, fork, restore, list), /diff (undo), /git, /goal, /note, /memory, /dream, /script, /project, /reflexion
│   └── system_commands.py     # /help, /status, /config (proxy, repair, hooks, compact), /context, /system, /tools, /skills, /dirs, /mcps, /clear, /retry, /debug, /exit
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
