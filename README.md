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
                          ┌───────────────────────────────────────────┐
                          │                User (CLI)                 │
                          └───────────────────────┬───────────────────┘
                                                  │
                                        ┌─────────▼───────┐
                                        │    MeshEngine   │
                                        │   (engine.py)   │
                                        └─────────┬───────┘
                                                  │
      ┌─────────────────┬──────────────┬──────────┼────────────┬────────────────┬──────────────────┐
      │                 │              │          │            │                │                  │
┌─────▼──────┐  ┌───────▼───────┐ ┌────▼───┐ ┌────▼───┐ ┌──────▼──────┐ ┌───────▼───────┐ ┌────────▼────────┐
│ Providers  │  │ Tool Registry │ │ Safety │ │ Skills │ │    MCP      │ │ Sub-Agents    │ │ Memory / Notes  │
│ (OpenAI/   │  │ & Permissions │ │ Guard  │ │        │ │   Client    │ │ (delegate /   │ │ / Checkpoints / │
│ Anthropic) │  │               │ │        │ │        │ │ (mcps.json) │ │ squad / etc.) │ │ Reflexion       │
└────────────┘  └───────────────┘ └────────┘ └────────┘ └─────────────┘ └───────────────┘ └─────────────────┘
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
| `/help` | List all available slash commands. |
| `/status` | Show a status overview of active models, tools, MCPs, skills, and memory. |
| `/clear` | Clear the conversation context window. |
| `/retry` | Retry the last LLM response turn. |
| `/debug [on\|off]` | Toggle Chain-of-Thought and tool-execution trace display. |
| `/checkpoint [save\|fork\|restore\|list] <args>` | Save, fork, restore, or list session checkpoints. |
| `/exit` | Close MCP connections and exit. |

### Models & Settings
| Command | Description |
| --- | --- |
| `/models` | List, discover, or add models: `/models discover [<provider>]`, `/models add [<provider>] [<pattern>]`. |
| `/switch auto\|router [<key>]\|<model_key>` | Switch the active model, or enable auto-routing via a router model. |
| `/config distill\|proxy\|repair\|hooks\|compact\|thinking\|effort\|tokens\|cost\|statistics [args]` | View or set automation and proxy toggles. |
| `/guard [on\|off]`, `/guard mode [supervised\|autonomous]`, `/guard model [<key>]`, `/guard trust <tool>` | View or configure the tool-call safety guard. |
| `/mode [plan\|build\|review\|yolo]` | View or switch the operating mode. |

### Context & Integration
| Command | Description |
| --- | --- |
| `/context` | Display conversation history, active tool schemas, and MCP statuses. |
| `/system [text]` | Show, set, or clear (`/system clear`) the current system prompt. |
| `/tools [on\|off]` | List registered tools with full schemas, or toggle their inclusion. |
| `/skills enable\|disable <name>` | List skills, or enable/disable one. |
| `/dirs add\|remove\|clear <path>` | List allowed directories, or edit the permission allow-list. |
| `/mcps on\|off\|enable\|disable <server>` | List MCP servers, or toggle them globally or per-server. |
| `/compact` | Semantically compact older conversation history using the LLM. |

### Agents & Workflows
| Command | Description |
| --- | --- |
| `/agent explore\|squad\|consensus\|delegate\|advisor <args>` | Sub-agent swarm and reasoning workflows. |
| `/loop <test_or_build_command>` | Iterative auto-test/fix loop with an automatic repair sub-agent. |
| `/jobs`, `/jobs log <id>`, `/jobs stop <id>`, `/jobs clear` | View or manage background jobs. |

### Memory & Knowledge
| Command | Description |
| --- | --- |
| `/goal <text> [\| criterion...]`, `/goal done <#>`, `/goal clear` | View, set, or manage the pinned session goal. |
| `/note append <text>`, `/note clear` | View notes, or edit `notes.md`. |
| `/memory save\|get\|search\|delete\|clear <args>` | View memory, or edit the persistent key-value store. |
| `/dream` | Analyze the conversation and extract candidate notes, memory facts, and skills. |
| `/reflexion [distill\|clear]` | View or distill cross-session error lessons. |

### Workspace & Developer Tools
| Command | Description |
| --- | --- |
| `/cd <path>` | Change working directory and reload workspace context. |
| `/shell <cmd>` or `! <cmd>` | Direct shell execution (bypasses the LLM). |
| `/python <code>` or `# <code>` | Direct Python execution (bypasses the LLM). |
| `/script <file.txt>` | Execute commands and prompts line-by-line from a script file. |
| `/project [map\|reload]` | View or reload workspace project rules and the repository map. |
| `/diff` / `/diff undo` | Display the unified diff of the last edit, or revert it. |
| `/git status\|diff\|commit\|push\|branch` | Run native Git commands. |

---

## ⚙️ Configuration Files

### `models.json`

Defines provider REST endpoints and model configurations, including per-model system prompts and an optional router model for `/switch auto`.

```json
{
  "active_model": "llama3-groq",
  "router_model": "llama3-groq",
  "providers": {
    "groq": {
      "name": "Groq Cloud",
      "base_url": "https://api.groq.com/openai/v1",
      "api_key_env": "GROQ_API_KEY"
    },
    "anthropic": {
      "name": "Anthropic",
      "base_url": "https://api.anthropic.com",
      "api_key_env": "ANTHROPIC_API_KEY"
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
      "system_prompt": "You are Llama 3 70B running on Groq acceleration, a fast AI assistant."
    },
    "claude-sonnet": {
      "name": "Claude Sonnet",
      "provider": "anthropic",
      "model_id": "claude-sonnet-4-6",
      "system_prompt": "You are Claude, a careful and precise coding assistant."
    }
  }
}
```

### `mcps.json`

Configures Model Context Protocol servers, over stdio (`command`/`args`) or a remote `url`.

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

### `skills.json`

Configures declarative skills that inject specialized system instructions (and optionally extra tools) into the session.

```json
{
  "skills": {
    "python_coding": {
      "enabled": true,
      "description": "Python code execution and developer-focused reasoning guidelines.",
      "system_instruction": "You possess the Python Coding Skill. Prefer concise, idiomatic Python."
    },
    "technical_writer": {
      "enabled": true,
      "description": "Formats technical responses into clean Markdown documentation.",
      "system_instruction": "Structure your answers with clean Markdown headings, concise code blocks, and bulleted summaries."
    }
  }
}
```

---

## 🤖 Sub-Agent Workflows

Mesh ships several multi-agent primitives, reachable via `/agent` or the underlying tools (`delegate_task`, `explore_branches`, `consult_consensus`, `consult_advisor`):

- **`delegate`** — Hands a self-contained task off to a fresh sub-agent with its own tool loop and turn budget, returning a distilled final report to the parent conversation.
- **`explore`** — Spins up parallel sub-agents to investigate different branches or approaches to a problem for comparison.
- **`squad`** — Runs an autonomous multi-step task pipeline across several sub-agents and produces a final combined report.
- **`consensus`** — Puts a question and a proposed solution to multiple models/perspectives and synthesizes their agreement or disagreement.
- **`advisor`** — Requests a second opinion / critique on a question or piece of work from a separate model.
- **`/loop`** — A specialized delegation loop: runs a test/build command, and on failure spawns a repair sub-agent to fix the code, then re-runs the command, up to a max number of iterations.

### Sub-Agent Proxy (Context Distillation)

When enabled (`/config proxy on`), heavy tools (`read_file`, `shell`, `web_search`, MCP tools) accept an `_intent` parameter describing why they're being called. The `SubAgentProxy` intercepts the raw output, runs it through a focused distillation pass, and returns only the information relevant to that stated intent — keeping the main model's context window clean. Short outputs and lightweight tools (`calculator`, `memory`) bypass distillation automatically.

---

## 🛡️ Security Model

Mesh layers three independent safety mechanisms:

1. **Directory Permissions** (`tools/permissions.py`) — Every file and shell tool validates target paths against an allow-list (`/dirs`). Requests outside it trigger an interactive **Always Allow / Allow Once / Deny** prompt.
2. **Operating Modes** (`modes.py`) — `plan` and `review` block every mutating tool (writes, shell, delegation, MCP) at the registry level, regardless of what the model asks for.
3. **Safety Guard** (`guard.py`) — An LLM-backed risk assessor evaluates tool calls before execution in `supervised` mode (asks for confirmation) or `autonomous` mode (blocks only high-risk calls). `yolo` mode reduces friction for ambiguous-risk actions but never disables the guard's high-risk blocks.

Example permission prompt:

```
❓ AI Decision Prompt: Tool 'read_file' requested access to a path outside allowed directories:
  Target: 'C:\Windows\System32\drivers\etc\hosts'

Select an option:
  ❯ 🔘 Always Allow (Add directory 'C:\Windows\System32\drivers\etc' to allowed list)
    ⚪ Allow Once
    ⚪ Deny
```

Use **`↑` / `↓` Arrow Keys** and **Enter** to make a selection.

---

## 📁 Project Structure

```
Mesh/
├── main.py                      # CLI entry point (argparse + asyncio.run)
├── engine.py                    # MeshEngine: core orchestration loop
├── config.py                    # ConfigManager and Pydantic config schemas
├── version.py                   # Central version identifier
├── theme.py                     # Rich console theme/styling
├── models.json                  # Provider endpoints and model configurations
├── mcps.json                    # MCP server definitions
├── skills.json                  # Declarative skills configuration
├── requirements.txt             # Python dependencies
│
├── compaction.py                # Semantic context window compaction
├── distill.py                   # Sub-agent proxy output distillation
├── delegation.py                # Sub-agent task delegation primitives
├── squad.py                     # Multi-agent task squad pipeline
├── explore.py                   # Parallel branch-exploration sub-agents
├── consensus.py                 # Multi-perspective consensus workflow
├── advisor.py                   # Second-opinion advisory workflow
├── test_loop.py                 # Autonomous /loop test-and-repair driver
├── guard.py                     # LLM-backed tool-call safety guard
├── modes.py                     # Plan / Build / Review / YOLO mode definitions
├── hooks.py                     # Lifecycle hook manager
├── checkpoint.py                # Session checkpoint save/fork/restore
├── file_history.py              # File-edit history & undo tracking
├── reflexion.py                 # Cross-session error-lesson distillation
├── dream.py                     # Conversation → notes/memory/skills extraction
├── memory_search.py             # Semantic search over persistent memory
├── project_rules.py             # Workspace project-rules loader
├── repo_map.py                  # Tree-sitter-based repository map generator
├── symbol_search.py             # Symbol indexer used by repo_map
├── context_mentions.py          # @-mention context resolution
├── git_workflow.py              # Higher-level Git workflow helpers
├── jobs.py                      # Background job manager
├── router.py                    # Auto-routing model selection
├── pricing.py                   # Token/cost accounting
├── python_executor.py           # Sandboxed Python execution helper
├── repair.py                    # Auto-repair helper utilities
├── tool_synthesis.py            # Dynamic tool synthesis
├── terminal_ui.py               # Interactive arrow-key menus
│
├── providers/
│   ├── openai_provider.py       # Async OpenAI-compatible client wrapper
│   └── anthropic_provider.py    # Async Anthropic client wrapper
│
├── render/
│   └── stream_renderer.py       # Rich Markdown & CoT streaming renderer
│
├── mcp/
│   └── client.py                # Native stdio/URL MCP client
│
├── tools/
│   ├── base.py                  # BaseTool class with dynamic schema injection
│   ├── registry.py              # Central tool execution & proxy dispatcher
│   ├── permissions.py           # PermissionManager & directory authorization
│   ├── native_tools.py          # read_file, write_file, edit_file, hash_edit, glob_files, shell
│   ├── web_tools.py             # Key-less web_search (DDG) & web_fetch
│   ├── memory_tool.py           # Key-value memory tool
│   ├── note_tool.py             # notes.md manager tool
│   ├── todo_tool.py             # Multi-step task tracking tool
│   ├── goal_tool.py             # Session goal tool
│   ├── job_tool.py              # Background job tool
│   ├── git_tool.py              # git_status/diff/commit/push/branch tools
│   ├── ask_tool.py              # Interactive human-in-the-loop tool
│   ├── delegate_tool.py         # Sub-agent delegation tool
│   ├── explore_tool.py          # Branch-exploration tool
│   ├── consensus_tool.py        # Consensus workflow tool
│   ├── advisor_tool.py          # Advisor workflow tool
│   └── symbol_tool.py           # Symbol search tool
│
├── skills/
│   ├── base.py                  # Skill base class definition
│   ├── registry.py              # Skill manager & instruction composer
│   └── code_skill.py            # Python coding skill implementation
│
└── commands/
    ├── registry.py              # Slash command registry & dispatcher
    ├── agent_commands.py        # /agent, /loop, /jobs, /guard, /mode
    ├── model_commands.py        # /models, /switch
    ├── session_commands.py      # /cd, /shell, /python, /goal, /note, /memory,
    │                            #   /dream, /script, /project, /reflexion,
    │                            #   /checkpoint, /diff, /git
    └── system_commands.py       # /help, /status, /config, /context, /system,
                                 #   /tools, /skills, /dirs, /mcps, /compact,
                                 #   /clear, /retry, /debug, /exit
```

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).