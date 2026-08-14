# ⚡ Mesh: A Modern, Modular and Hackable AI Harness

*Developed by* **Farshid Mossaiby**

A modern, modular and hackable AI CLI harness written in Python. Mesh connects to any OpenAI- or Anthropic-compatible model provider and wraps it with a full agentic toolset: file editing, shell access, web search, MCP servers, sub-agent delegation, persistent memory, session save/resume, Markdown logging, a comprehensive test suite, and a safety layer that gates risky tool calls — all driven from a single terminal chat loop.

---

## 🌟 Key Features

- **Multi-Provider Support** — Talk to OpenAI, Anthropic, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint, all configured in `config.json`. Switch models live with `/switch`, or let a router model auto-select per turn with `/switch auto`.
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
- **Context Engineering** — Semantic context compaction (`/compact`) that summarizes older turns without breaking active tool-call pairs, a Sub-Agent Proxy that distills large tool outputs before they hit the main model's context, and repository maps (`/project map`) built from a tree-sitter symbol index.
- **Session Continuity & Rollback** — Save and branch conversation state with checkpoints (`/checkpoint save|fork|restore|list`), file-edit history with undo (`/diff undo`), and reflexion (`/reflexion`) that distills cross-session error lessons.
- **Native Tool Suite** — File ops (`read_file`, `write_file`, `edit_file`, `hash_edit`, `glob_files`), shell execution, key-less web search/fetch, Git tools, a calculator, and an `ask_user` tool for human-in-the-loop decisions.
- **Test-Driven Reliability** — Comprehensive, automated `pytest` test suite verifying tool safety, dependency DAGs, file hash drift protection, permission isolation, and session roundtrip persistence.
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
                                        └─────────────┬───────────┘
                                                      │
      ┌──────────────────┬─────────────┬──────────┬───┴────────┬──────────────────┬────────────────────┐
      │                  │             │          │            │                  │                    │
┌─────┴──────┐  ┌────────┴──────┐ ┌────┴───┐ ┌────┴───┐ ┌──────┴──────┐ ┌─────────┴────────┐ ┌─────────┴───────┐
│ Providers  │  │ Tool Registry │ │ Safety │ │ Skills │ │    MCP      │ │ Sub-Agents       │ │ Memory / Notes  │
│ (OpenAI/   │  │ & Permissions │ │ Guard  │ │        │ │   Client    │ │ (delegate /      │ │ / Checkpoints / │
│ Anthropic) │  │               │ │        │ │        │ │ (mcps.json) │ │ squad / etc.)    │ │ Reflexion       │
└────────────┘  └───────────────┘ └────────┘ └────────┘ └─────────────┘ └──────────────────┘ └─────────────────┘
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

### 5. Run the Test Suite

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_native_tools.py -v
pytest tests/test_session_manager.py -v
```

---

## 🧪 Testing & Validation

Mesh includes a comprehensive test suite in the `tests/` directory to ensure reliability, drift-free file operations, safe dependency resolution, and state persistence:

| Test Module | Coverage & Verification |
|---|---|
| `tests/test_native_tools.py` | `read_file`, `write_file`, exact/fuzzy `edit_file`, line-hash verification in `hash_edit`, directory creation, `glob_files`, `shell`, and line-splice integrity |
| `tests/test_todo_tool.py` | Task creation, 1-based indexing, dependency DAG resolution, blocker prevention in `complete`, `next` unblocked task queries, and argument type coercion |
| `tests/test_goal_tool.py` | Pinned session goals, success criteria completion, system prompt Markdown section generation, and callback notifications |
| `tests/test_memory_and_notes.py` | Persistent key-value memory CRUD (`memory.json`), Markdown notes append/write/clear (`notes.md`), and file serialization |
| `tests/test_permissions.py` | Allowed directory containment, path canonicalization, symlink traversal prevention, and YOLO mode auto-approval |
| `tests/test_calculator_and_registry.py` | Arithmetic evaluation, AST injection safety, tool registration/unregistration, mode blocking, and fuzzy tool name typo correction |
| `tests/test_session_manager.py` | Disk session serialization, `.removesuffix(".json")` filename handling, session list/delete, metric restoration, and state reconstruction |
| `tests/test_checkpoint.py` | State snapshots, branching, deep-copy integrity, and conversation rollback |
| `tests/test_file_history.py` | Edit recording, unified diff generation, undo stack operations, and automatic deletion of newly created files upon undo |
| `tests/test_compaction.py` | Token estimation heuristics and safe split index calculation preserving tool call pairs |
| `tests/test_modes.py` | Mode definitions, mutating tool blocks (`plan`, `review`), and allowlist enforcement (`chat` mode) |

---

## 🛠️ Slash Commands Reference

### Session & System
| Command | Description |
| --- | --- |
| `/help` | Display available slash commands and usage help: `/help [<command>]` |
| `/status` | Display Mesh system status and configuration overview: `/status` |
| `/clear` | Clear conversation context window (preserves system prompt and skills): `/clear` |
| `/retry` | Retry the last assistant turn: `/retry` |
| `/debug [on\|off]` | View or toggle debug mode (CoT & tool execution traces): `/debug [on\|off]` |
| `/session [save\|load\|list\|delete] [<name>]` | Save, load, list, or delete disk session states in `sessions/` |
| `/log [on\|off\|status\|<filepath>]` | View or configure Markdown session logging |
| `/checkpoint [save\|fork\|restore\|list] <args>` | Save, fork, restore, or list session checkpoints |
| `/exit` | Close active sessions and exit Mesh: `/exit` |

### Models & Settings
| Command | Description |
| --- | --- |
| `/models` | List, discover, or add models: `/models [discover\|add] [<provider>] [<pattern>]` |
| `/switch [auto\|router\|<model_key>]` | Switch active model or mode: `/switch [auto\|router\|<model_key>]` |
| `/config [distill\|proxy\|repair\|hooks\|compact\|thinking\|effort\|tokens\|cost\|statistics\|set] <args>` | View or configure system settings and parameters |
| `/guard [on\|off\|mode\|model\|trust] <args>` | View or configure safety guard settings |
| `/mode [plan\|build\|review\|chat\|yolo]` | View or switch operating mode: `/mode [plan\|build\|review\|chat\|yolo]` |

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

System parameters, provider REST endpoints, and model configurations can be tuned directly or set via `/config set <category> <param> <value>`:

```json
{
  "active_model": "anthropic:claude-3-7-sonnet-20250219",
  "system_prompt": "You are Mesh, a helpful AI assistant...",
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

## 📁 Project Structure

```
Mesh/
├── main.py                          # CLI entry point (argparse + asyncio.run)
├── engine.py                        # MeshEngine: core orchestration loop
├── config.py                        # ConfigManager and Pydantic config schemas
├── config.json                      # System parameters, provider endpoints, & models
├── session_logger.py                # Markdown session logger
├── session_manager.py               # Disk-backed session save/resume/list manager
├── version.py                       # Central version identifier
├── theme.py                         # Rich console theme/styling
├── mcps.json                        # MCP server definitions
├── skills.json                      # Declarative skills configuration
├── requirements.txt                 # Python dependencies
│
├── compaction.py                    # Semantic context window compaction
├── distill.py                       # Sub-agent proxy output distillation
├── delegation.py                    # Sub-agent task delegation primitives
├── squad.py                         # Multi-agent task squad pipeline
├── explore.py                       # Parallel branch-exploration sub-agents
├── consensus.py                     # Multi-perspective consensus workflow
├── advisor.py                       # Second-opinion advisory workflow
├── test_loop.py                     # Autonomous /loop test-and-repair driver
├── guard.py                         # LLM-backed tool-call safety guard
├── modes.py                         # Plan / Build / Review / Chat / YOLO mode definitions
├── hooks.py                         # Lifecycle hook manager
├── checkpoint.py                    # Session checkpoint save/fork/restore
├── file_history.py                  # File-edit history & undo tracking
├── reflexion.py                     # Cross-session error-lesson distillation
├── dream.py                         # Conversation → notes/memory/skills extraction
├── memory_search.py                 # Semantic search over persistent memory
├── project_rules.py                 # Workspace project-rules loader
├── repo_map.py                      # Tree-sitter-based repository map generator
├── symbol_search.py                 # Symbol indexer used by repo_map
├── context_mentions.py              # @-mention context resolution
├── git_workflow.py                  # Higher-level Git workflow helpers
├── jobs.py                          # Background job manager
├── router.py                        # Auto-routing model selection
├── pricing.py                       # Token/cost accounting
├── python_executor.py               # Sandboxed Python execution helper
├── repair.py                        # Auto-repair helper utilities
├── tool_synthesis.py                # Dynamic tool synthesis
├── terminal_ui.py                   # Interactive arrow-key menus & completer
│
├── providers/
│   ├── openai_provider.py           # Async OpenAI-compatible client wrapper
│   └── anthropic_provider.py        # Async Anthropic client wrapper
│
├── render/
│   └── stream_renderer.py           # Rich Markdown & CoT streaming renderer
│
├── mcp/
│   └── client.py                    # Native stdio/URL MCP client
│
├── tools/
│   ├── base.py                      # BaseTool class with dynamic schema injection
│   ├── registry.py                  # Central tool execution & proxy dispatcher
│   ├── permissions.py               # PermissionManager & directory authorization
│   ├── native_tools.py              # read_file, write_file, edit_file, hash_edit, glob_files, shell
│   ├── web_tools.py                 # Key-less web_search (DDG) & web_fetch
│   ├── memory_tool.py               # Key-value memory tool
│   ├── note_tool.py                 # notes.md manager tool
│   ├── todo_tool.py                 # Multi-step task tracking tool
│   ├── goal_tool.py                 # Session goal tool
│   ├── job_tool.py                  # Background job tool
│   ├── git_tool.py                  # git_status/diff/commit/push/branch tools
│   ├── ask_tool.py                  # Interactive human-in-the-loop tool
│   ├── delegate_tool.py             # Sub-agent delegation tool
│   ├── explore_tool.py              # Branch-exploration tool
│   ├── consensus_tool.py            # Consensus workflow tool
│   ├── advisor_tool.py              # Advisor workflow tool
│   └── symbol_tool.py               # Symbol search tool
│
├── skills/
│   ├── base.py                      # Skill base class definition
│   ├── registry.py                  # Skill manager & instruction composer
│   └── code_skill.py                # Python coding skill implementation
│
├── commands/
│   ├── registry.py                  # Slash command registry & dispatcher
│   ├── agent_commands.py            # /agent, /loop, /jobs, /guard, /mode
│   ├── model_commands.py            # /models, /switch
│   ├── session_commands.py          # /cd, /shell, /python, /goal, /note, /memory,
│   │                                #   /dream, /script, /project, /reflexion,
│   │                                #   /checkpoint, /diff, /git, /session, /log
│   └── system_commands.py           # /help, /status, /config, /context, /system,
│                                    #   /tools, /skills, /dirs, /mcps, /compact,
│                                    #   /clear, /retry, /debug, /exit
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Pytest fixtures, mock engine, & isolated workspace
    ├── test_native_tools.py         # File read/write/edit/hash_edit, diff, glob & shell tests
    ├── test_todo_tool.py            # Dependency DAG, next tasks, & completion blockers
    ├── test_goal_tool.py            # Session goals, criteria tracking, & prompt injection
    ├── test_memory_and_notes.py     # Persistent key-value memory & notes.md CRUD
    ├── test_permissions.py          # Working directory allowlist & YOLO auto-approval
    ├── test_calculator_and_registry.py # Safe AST calculator & tool registry execution
    ├── test_session_manager.py      # Session disk save/load/delete & state integrity
    ├── test_checkpoint.py           # State snapshots & session branching
    ├── test_file_history.py         # Edit history, unified diffs, & file undo stack
    ├── test_compaction.py           # Context estimation & conversation compaction
    └── test_modes.py                # Build, Plan, Review, Chat, & YOLO mode boundaries
```

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
