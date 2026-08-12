# ⚡ Mesh: A Modern, Modular and Hackable AI Harness

*Developed by* **Farshid Mossaiby**

A modern, modular and hackable AI CLI harness written in Python. Mesh connects to any OpenAI- or Anthropic-compatible model provider and wraps it with a full agentic toolset: file editing, shell access, web search, MCP servers, sub-agent delegation, persistent memory, and a safety layer that gates risky tool calls — all driven from a single terminal chat loop.

---

## 🌟 Key Features

- **Multi-Provider Support** — Talk to OpenAI, Anthropic, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint, all configured in `models.json`. Switch models live with `/switch`, or let a router model auto-select per turn with `/switch auto`.
- **Operating Modes (`/mode`)** — `build` (full access, default), `plan` and `review` (read-only investigation, no writes/shell/delegation/MCP), and `yolo` (full access, fewer confirmation prompts — high-risk actions are still always blocked).
- **Safety Guard (`/guard`)** — An LLM-backed risk assessor that reviews tool calls before execution, can run in `supervised` or `autonomous` mode, supports per-session tool trust, and always blocks genuinely high-risk actions regardless of mode.
- **Directory Permissions (`/dirs`)** — A `PermissionManager` enforces a working-directory allow-list for every file/shell tool. Out-of-bounds access triggers an interactive Allow Once / Always Allow / Deny prompt.
- **Model Context Protocol (`/mcps`)** — A native stdio/URL MCP client (`mcps.json`) that discovers and calls tools from external MCP servers (filesystem, SQLite, GitHub, etc.), with global and per-server toggles.
- **Sub-Agent & Multi-Agent Workflows (`/agent`)** — Spin up focused sub-agents for task delegation (`delegate`), branching exploration (`explore`), parallel task squads (`squad`), multi-model consensus (`consensus`), and second-opinion advisory review (`advisor`).
- **Autonomous Test/Fix Loop (`/loop`)** — Runs a test or build command, and on failure automatically delegates a repair sub-agent to fix the code and retries, up to a configurable number of iterations.
- **Declarative Skills (`/skills`)** — Package specialized system prompts and tools into reusable skills, loaded from `skills.json` or custom Python classes (see `skills/code_skill.py`).
- **Persistent Memory & Notes** — A key-value `memory` store with semantic search (`/memory`), a running Markdown `notes.md` (`/note`), pinned session goals with completion criteria (`/goal`), and multi-step task tracking (`todo`).
- **Context Engineering** — Semantic context compaction (`/compact`) that summarizes older turns without breaking active tool-call pairs, a Sub-Agent Proxy that distills large tool outputs before they hit the main model's context, and repository maps (`/project map`) built from a tree-sitter symbol index.
- **Session Continuity** — Checkpoints (`/checkpoint save|fork|restore|list`) for saving and branching conversation state, file-edit history with undo (`/diff undo`), and reflexion (`/reflexion`) that distills cross-session error lessons.
- **Native Tool Suite** — File ops (`read_file`, `write_file`, `edit_file`, `hash_edit`, `glob_files`), shell execution, key-less web search/fetch, Git tools, a calculator, and an `ask_user` tool for human-in-the-loop decisions.
- **Rich Terminal UI** — Real-time Markdown streaming with syntax highlighting, toggleable Chain-of-Thought display (`/debug`), and an interactive arrow-key model/menu switcher.

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
      ┌──────────────────┬─────────────┬──────────┼────────────┬──────────────────┬──────────────────┐
      │                  │             │          │            │                  │                  │
┌─────▼──────┐  ┌────────▼──────┐ ┌────▼───┐ ┌────▼───┐ ┌──────▼──────┐ ┌─────────▼────────┐ ┌────────▼────────┐
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
```

### 3. Configure API Keys

Set environment variables for whichever providers you use (referenced by `api_key_env` in `models.json`):

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
python main.py
```

Or run a script file non-interactively:

```bash
python main.py path/to/script.txt --non-interactive
# equivalent: python main.py -f path/to/script.txt -n
```

---

## 🛠️ Slash Commands Reference

### Session & System
| Command | Description |
| --- | --- |
| `/help` | Display available slash commands and usage help. |
| `/status` | Display Mesh system status and configuration overview. |
| `/clear` | Clear conversation context window (preserves system prompt and skills). |
| `/retry` | Retry the last assistant turn. |
| `/debug [on\|off]` | View or toggle debug mode (CoT & tool execution traces). |
| `/checkpoint [save\|fork\|restore\|list] <args>` | Save, fork, restore, or list session checkpoints. |
| `/exit` | Close active sessions and exit Mesh. |

### Models & Settings
| Command | Description |
| --- | --- |
| `/models` | List, discover, or add models: `/models [discover\|add] [<provider>] [<pattern>]`. |
| `/switch [auto\|router\|<model_key>]` | Switch active model or mode. |
| `/config [distill\|proxy\|repair\|hooks\|compact\|thinking\|effort\|tokens\|cost\|statistics\|set] <args>` | View or configure system settings and parameters. |
| `/guard [on\|off\|mode\|model\|trust] <args>` | View or configure safety guard settings. |
| `/mode [plan\|build\|review\|yolo]` | View or switch operating mode. |

### Context & Integration
| Command | Description |
| --- | --- |
| `/context` | Display conversation context window, active tools, and MCP server states. |
| `/system [<text>]` | View or update the system prompt (or `/system clear`). |
| `/tools [on\|off]` | List registered tools and schemas, or toggle tool execution. |
| `/skills enable\|disable <name>` | List registered skills, or toggle a skill. |
| `/dirs [add\|remove\|clear] [<path>]` | View or modify allowed working directories. |
| `/mcps [on\|off\|enable\|disable] [<server>]` | View or toggle Model Context Protocol servers. |
| `/compact` | Semantically summarize older conversation history to free context tokens. |

### Agents & Workflows
| Command | Description |
| --- | --- |
| `/agent [explore\|squad\|consensus\|delegate\|advisor] <args>` | Run sub-agent swarm and reasoning workflows. |
| `/loop <test_or_build_command>` | Run iterative auto-test and repair loop. |
| `/jobs [log\|stop\|clear] [<job_id>]` | View or manage background job processes. |

### Memory & Knowledge
| Command | Description |
| --- | --- |
| `/goal [<text>] [\| criteria]`, `/goal done <#>`, `/goal clear` | View, set, or manage pinned session goal. |
| `/note [append <text>\|clear]` | View or edit persistent Markdown notes. |
| `/memory [save\|get\|list\|search\|delete\|clear] <args>` | View or edit persistent memory key-value store. |
| `/dream` | Analyze conversation transcript and extract persistent notes, memory facts, and skills. |
| `/reflexion [distill\|clear]` | View or distill cross-session error lessons. |

### Workspace & Developer Tools
| Command | Description |
| --- | --- |
| `/cd <path>` | Change working directory and reload workspace context. |
| `/shell <cmd>` or `!<cmd>` | Execute shell command directly (bypasses LLM). |
| `/python <code>` or `#<code>` | Execute Python snippet directly (bypasses LLM). |
| `/script <file.txt>` | Execute commands and prompts line-by-line from script file. |
| `/project [map\|reload]` | View or reload project rules and repository map. |
| `/diff` / `/diff undo` | Display unified file diff or revert last edit. |
| `/git [status\|diff\|commit\|push\|branch]` | Run native Git commands. |

---

## ⚙️ Configuration File (`models.json`)

System parameters, provider REST endpoints, and model configurations can be tuned directly or set via `/config set <category> <param> <value>`:

```json
{
  "active_model": "lmstudio:gemma-4-e4b",
  "system_prompt": "You are Mesh, a helpful AI assistant...",
  "auto_compact": true,
  "auto_compact_threshold": 0.75,
  "max_delegation_depth": 2,
  "advisor_model": "lmstudio:gemma-4-e4b",
  "guard_enabled": true,
  "guard_model": "lmstudio:minicpm5-1b-claude-opus-fable5-v2-thinking-heretic",
  "guard_autonomy": "supervised",
  "router_model": "lmstudio:minicpm5-1b-claude-opus-fable5-v2-thinking-heretic",
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
    "repomap": 500,
    "dream": 12000,
    "gitdiff": 4000,
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
  }
}
```

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
