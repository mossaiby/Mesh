# ⚡ Mesh — Onboarding & User Guide

Mesh is a modular, text-based AI CLI harness written in Python. It connects to cloud or local LLMs (OpenAI-compatible endpoints, plus a native Anthropic driver), gives them a rich toolbox (file editing, shell, git, web, memory), and wraps the whole thing in a terminal REPL with streaming Markdown output, safety guardrails, and session persistence.

This guide takes you from zero to productive: installation, first run, core concepts, the full command reference, common workflows, configuration, and troubleshooting.

---

## Table of Contents

1. [What Mesh Is (and Isn't)](#1-what-mesh-is-and-isnt)
2. [Installation](#2-installation)
3. [First Run & API Keys](#3-first-run--api-keys)
4. [Core Concepts](#4-core-concepts)
5. [Talking to Mesh](#5-talking-to-mesh)
6. [Command Reference](#6-command-reference)
7. [Operating Modes (Safety Model)](#7-operating-modes-safety-model)
8. [Tools Mesh Can Use](#8-tools-mesh-can-use)
9. [Configuration Files](#9-configuration-files)
10. [Common Workflows](#10-common-workflows)
11. [Sub-Agent Workflows](#11-sub-agent-workflows)
12. [Memory, Notes & Learning Over Time](#12-memory-notes--learning-over-time)
13. [Troubleshooting](#13-troubleshooting)
14. [Quick Reference Card](#14-quick-reference-card)

---

## 1. What Mesh Is (and Isn't)

**Mesh is:**
- A terminal-based AI agent loop, similar in spirit to Claude Code or Aider, but provider-agnostic.
- Built around a tool-calling loop: you type a prompt, the model responds and optionally calls tools (read/write files, run shell commands, search the web, etc.), Mesh executes them, and feeds results back until the model produces a final answer.
- Configurable at the model, provider, tool, and safety level via `config.json`, `mcps.json`, `skills.json`, and in-session slash commands.

**Mesh is not:**
- A GUI application — everything happens in your terminal.
- Tied to one AI provider — it works with OpenAI, Anthropic, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint.
- A sandboxed environment — the shell, file, and Python execution tools operate directly on your real filesystem and processes. Read [Section 7](#7-operating-modes-safety-model) before turning off the Safety Guard.

---

## 2. Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | Required. |
| `ruff` / `flake8` | Optional — enables post-edit Python linting. |
| `eslint` | Optional — enables post-edit JS/TS linting. |
| `cargo` | Optional — enables post-edit Rust checks. |
| `gofmt` | Optional — enables post-edit Go formatting checks. |
| `npx` / `uvx` | Optional — only needed if you configure external stdio MCP servers in `mcps.json` that depend on Node.js or `uv`. |

Mesh detects installed linters automatically via `PATH` lookup and skips any that aren't present — no configuration required.

### Install

```bash
git clone https://github.com/mossaiby/Mesh.git
cd Mesh
pip install -r requirements.txt
```

Key dependencies installed: `openai`, `anthropic`, `rich` (terminal rendering), `pydantic` (config schemas), `httpx[socks]` (networking + proxy support), `prompt_toolkit` (interactive input), and `tree-sitter` (code symbol indexing).

---

## 3. First Run & API Keys

### Set provider credentials

Export whichever providers you plan to use:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-..."
```

Local providers (Ollama, LM Studio, vLLM) typically need a dummy key:

```bash
export OLLAMA_API_KEY="dummy"
export LOCAL_API_KEY="dummy"
```

> API keys can also be embedded per-provider in `config.json` via `api_key_env`, which just names the environment variable Mesh should read — no secrets are stored in the config file itself by default.

### Optional: network proxy

If you're behind a corporate proxy, either export standard variables before launch:

```bash
export HTTP_PROXY="http://proxy.corp.com:8080"
export HTTPS_PROXY="http://proxy.corp.com:8080"
export ALL_PROXY="socks5://127.0.0.1:1080"
```

...or configure it live once Mesh is running:

```
/config proxy http://proxy.corp.com:8080
/config proxy clear
```

*(OS-level GUI proxy settings, e.g. Windows Internet Options, are invisible to Python CLI tools — you must export the environment variable or use `/config proxy`.)*

### Launch

```bash
# Interactive REPL
python main.py

# Run a script file on startup, then drop into the REPL
python main.py script.txt

# Run a script file headlessly and exit
python main.py --file script.txt --non-interactive
```

On launch, Mesh prints its version and author banner, initializes any configured MCP servers, and drops you into a `>` prompt ready to chat.

---

## 4. Core Concepts

Understanding these five ideas covers most of what you need to use Mesh effectively.

**Turn loop.** Each message you send starts an inference "turn." The active model can respond with text, call one or more tools, or both. Mesh executes any tool calls, appends the results to the conversation, and loops back to the model — up to 10 tool-calling rounds per turn — until it produces a plain text answer.

**Tool Registry.** Every capability Mesh has (reading a file, running a shell command, searching the web, checking git status) is a registered "tool" with a JSON schema the model can call. `/tools` lists them; `/tools off` disables tool-calling entirely, turning Mesh into a plain chat client.

**Modes.** A mode is a blanket policy over which tools are available and how much confirmation is required. Four modes ship by default: `build` (full access, the default), `plan` and `review` (read-only investigation), and `yolo` (full access, no confirmation prompts). See [Section 7](#7-operating-modes-safety-model).

**Safety Guard.** Independent of mode, any tool marked `requires_guard=True` (file writes, shell commands, MCP tools) can be checked by a second, smaller LLM call that assesses risk before execution. This is configurable via `/guard`.

**Skills.** A skill is a reusable bundle of extra system-prompt instructions (and optionally tools) that Mesh injects when active — e.g. "Python Coding" or "Technical Writer." Skills live in `skills.json` and are toggled with `/skills`.

---

## 5. Talking to Mesh

Anything you type that doesn't start with `/`, `!`, or `#` is sent to the model as a normal chat message.

**Shortcuts:**

| Prefix | Meaning |
|---|---|
| `/command args` | Runs a slash command directly — see [Section 6](#6-command-reference). |
| `!command` | Runs a shell command immediately, without going through the LLM or touching conversation history. Equivalent to `/shell`. |
| `#code` | Executes a line of Python in a persistent session namespace, without touching conversation history. Equivalent to `/python`. |
| `@filename` | Inside a normal prompt, `@` mentions are expanded to inject file content directly into your message before it's sent. |

**Example session:**

```
> @main.py explain the process_inference loop to me
> add error handling to the shell tool for when the process times out
> /diff
> /git commit
```

---

## 6. Command Reference

Type `/help` any time for a live categorized list, or `/help <command>` for detailed usage of one command.

### ⚙️ Models & Settings

| Command | Description |
|---|---|
| `/status` | Active model, router model, proxy, thinking mode, effort level, tool/MCP state, symbol count, git branch, metrics display settings, context usage. |
| `/models` | List configured models (`/models`), discover remote endpoints (`/models discover`), or batch-add models (`/models add openrouter *free*`). |
| `/switch` | Switch model or enable routing: `/switch <key>`, `/switch auto` (sticky dynamic router), `/switch router [<key>]`. |
| `/config` | Toggle subsystems: `distill`, `proxy`, `repair`, `hooks`, `compact`, `thinking`, `effort`, `tokens`, `cost`, `statistics`. |
| `/mode` | Switch operating mode: `/mode build \| plan \| review \| yolo`. |
| `/guard` | Configure the tool-call Safety Guard: `on`, `off`, `mode supervised\|autonomous`, `model [<key>]`, `trust <tool>`. |

### 🤖 Agents & Workflows

| Command | Description |
|---|---|
| `/agent explore [<n>] <task>` | Runs `n` (2–5) parallel speculative solution branches and synthesizes the best approach. |
| `/agent squad <task>` | 4-stage pipeline: Architect → Coder → Tester → Auditor. |
| `/agent consensus <question> \| <proposal>` | One model critiques, then a (possibly different) model produces a verified recommendation. |
| `/agent delegate <task>` | Hands a task to an autonomous sub-agent that runs its own tool loop and reports back. `/agent delegate depth [<n>]` sets recursion depth. |
| `/agent advisor <question>` | Consults a second-opinion model without derailing the main conversation. `/agent advisor model [<key>]` sets which model advises. |
| `/loop <test_cmd>` | Iterative auto-fix loop: runs a test/build command, feeds failures back to the model, retries (max 5 iterations). |
| `/jobs` | View/manage background async processes: `/jobs log <id>`, `/jobs stop <id>`, `/jobs clear`. |

### 🛠️ Workspace & Developer Tools

| Command | Description |
|---|---|
| `/cd <path>` | Change working directory; syncs allowed directories, `PROJECT.md` rules, and the AST symbol index. |
| `/project` | View/reload project rules (`PROJECT.md`) or the repo architecture map (`/project map`). |
| `/git` | `status`, `diff`, `commit` (AI-generated commit message), `push`, `branch`. |
| `/diff` | View colorized diffs of recent file edits (`/diff`), or revert them (`/diff undo`). |
| `/shell` \| `!` | Direct shell execution outside the LLM loop. |
| `/python` \| `#` | Direct Python execution in a persistent namespace, outside the LLM loop. |
| `/script <file>` | Runs commands and prompts line-by-line from a script file. |

### 🧠 Memory & Knowledge

| Command | Description |
|---|---|
| `/goal` | View/set a pinned session goal, folded directly into the system prompt. |
| `/note` | View/edit persistent Markdown notes (`notes.md`). |
| `/memory` | Manage the persistent key-value store (`memory.json`), including semantic meaning search. |
| `/dream` | Interactively extract durable notes, memory facts, and skills from conversation history. |
| `/reflexion` | View or distill cross-session error lessons into durable system rules (`/reflexion distill`). |

### 🔌 Context & Integration

| Command | Description |
|---|---|
| `/context` | Raw conversation history, active tool names, MCP status. |
| `/system [text]` | Show or set the system prompt. |
| `/tools [on\|off]` | List registered tools with schemas, or toggle tool-calling entirely. |
| `/skills` | Enable/disable/register skills. |
| `/dirs` | Manage the `PermissionManager` allow-list of directories. |
| `/mcps [on\|off]` | View connected MCP servers or toggle them. |
| `/compact` | Manually trigger semantic summarization of older conversation history. |

### 💻 Session & System

| Command | Description |
|---|---|
| `/help [command]` | Command categories, or usage for one command. |
| `/checkpoint` | `save <tag>`, `fork <branch>`, `restore <tag>` — session state snapshots. |
| `/clear` | Clear conversation history; keeps system prompt, goal, and skills. |
| `/retry` | Re-run the last LLM turn (strips the last assistant/tool exchange first). |
| `/debug [on\|off]` | Show Chain-of-Thought reasoning and sub-agent execution traces. |
| `/exit` | Gracefully stop background jobs, close MCP connections, and quit. |

---

## 7. Operating Modes (Safety Model)

Mesh has two independent safety layers that stack together: **mode** (what's allowed at all) and **Safety Guard** (whether an allowed action needs a second opinion first).

### Modes

| Mode | Tool access | When to use it |
|---|---|---|
| **build** *(default)* | Full — reads and writes | Normal day-to-day work. |
| **plan** | Read-only: `read_file`, `glob_files`, `web_search`, `web_fetch`, `consult_advisor` | Ask Mesh to investigate and propose an approach without touching anything. |
| **review** | Read-only, same tool set as `plan` | Ask Mesh to critique existing code/config for bugs, risk, and style — not to plan new work. |
| **yolo** | Full access, no confirmation prompts for ambiguous-risk actions | Fast iterative work when you've already decided to trust the agent for this session. Genuinely high-risk actions are still blocked by the Safety Guard regardless of mode. |

Switch modes with `/mode <name>`. Any tool that mutates state (file writes, shell, delegation, MCP tools) is automatically blocked in `plan`/`review` — this is computed live from the tool registry, so any newly connected MCP tool is covered too.

### Safety Guard

Independent of mode, tools flagged `requires_guard=True` can be routed through a lightweight risk-assessment LLM call before they execute:

```
/guard on               # enable
/guard off               # disable — guarded calls run unchecked
/guard mode supervised   # ask before risky actions
/guard mode autonomous   # block only genuinely high-risk actions, no prompts
/guard model <key>       # use a specific model for risk assessment
/guard trust <tool_name> # stop guard-checking a specific tool for this session
```

### Directory permissions

Separately, the `PermissionManager` restricts filesystem tool access to an allow-list (defaults to your current working directory). If a tool requests a path outside it, you get an interactive prompt:

```
❓ Tool 'read_file' requested access to a path outside allowed directories:
  Target: '/etc/passwd'

  ❯ Always Allow (add parent directory to allowed list)
    Allow Once
    Deny
```

Manage the allow-list directly with `/dirs`.

> **Practical rule of thumb:** stay in `build` mode with the Safety Guard **on** and `supervised` autonomy until you've watched Mesh work in your codebase for a while. Reach for `yolo` only once you trust its judgment for the task at hand, and never on a machine/directory you can't afford to have modified unexpectedly.

---

## 8. Tools Mesh Can Use

| Category | Tools |
|---|---|
| **Files** | `read_file` (with optional hash-anchored line output), `write_file`, `edit_file` (exact + fuzzy match), `hash_edit` (hash-verified line-range replace), `glob_files` |
| **Shell** | `shell` (synchronous), background shell jobs via `/jobs` |
| **Web** | `web_search` (key-less DuckDuckGo), `web_fetch` (HTML → clean text) |
| **Git** | status, diff, commit (AI-written message), push, branch |
| **Human-in-the-loop** | `ask_user` — interactive arrow-key choice or free text |
| **Session state** | `memory` (key-value store), `note_manager` (`notes.md`), `todo_manager` |
| **Code intelligence** | symbol search (`tree-sitter`-based), repo map |
| **Sub-agents** | explore, squad, consensus, delegate, advisor (see [Section 11](#11-sub-agent-workflows)) |
| **External** | Any MCP server tool configured in `mcps.json` |

### Hash-anchored & fuzzy file editing

Two complementary editing strategies avoid the two classic failure modes of LLM file edits — silent drift and false "not found" errors:

- **`hash_edit`**: call `read_file` with `show_hashes: true` to get output like `L12|a3f1| def foo():`. Then `hash_edit` verifies the 4-character hash at your target start/end lines before replacing them — if the file changed since you read it, the edit is rejected instead of silently corrupting the wrong lines.
- **`edit_file`**: tries an exact string match first; if that fails (e.g. due to whitespace differences), it falls back to fuzzy block matching via `difflib.SequenceMatcher` and applies the edit automatically at ≥85% similarity.

### Post-edit linter hooks

After `write_file`, `edit_file`, or `hash_edit`, Mesh runs any linter it can find for that file type (`ruff`/`flake8`, `eslint`, `cargo check`, `gofmt`) and feeds the results straight back to the model in the same turn — so syntax errors and broken imports often get self-corrected without you noticing. Toggle with `/config hooks`.

---

## 9. Configuration Files

### `config.json` — providers, models, and global settings

```json
{
  "active_model": "anthropic:claude-3-7-sonnet-20250219",
  "system_prompt": "You are Mesh, a helpful, precise, and efficient AI assistant.",
  "auto_compact": true,
  "auto_compact_threshold": 0.75,
  "max_delegation_depth": 2,
  "advisor_model": null,
  "guard_enabled": true,
  "guard_autonomy": "supervised",
  "router_model": null,
  "network_proxy": null,
  "thinking": true,
  "effort": "medium",
  "show_tokens": true,
  "show_cost": true,
  "show_statistics": true,
  "providers": {
    "anthropic": {
      "name": "Anthropic Official",
      "base_url": "https://api.anthropic.com/v1",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
  },
  "models": {
    "anthropic:claude-3-7-sonnet-20250219": {
      "name": "Claude 3.7 Sonnet",
      "provider": "anthropic",
      "model_id": "claude-3-7-sonnet-20250219",
      "context_window": 200000,
      "tags": ["reasoning", "coding", "agent", "thinking", "large-context"],
      "description": "Anthropic's flagship hybrid reasoning model with extended thinking and prompt caching."
    }
  }
}
```

Most of this file is also editable live via `/config`, `/switch`, and `/models add` — you rarely need to hand-edit it except to register new providers or models in bulk.

### `mcps.json` — external tool servers

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

Empty by default. Add any stdio MCP server here and its tools become available automatically on next launch (or toggle live with `/mcps`).

### `skills.json` — reusable instruction/tool bundles

```json
{
  "skills": {
    "python_coding": {
      "enabled": true,
      "description": "Python code execution and developer-focused reasoning guidelines.",
      "system_instruction": "You possess the Python Coding Skill. Prefer concise, idiomatic Python."
    }
  }
}
```

Toggle with `/skills`. Ships with `python_coding` and `technical_writer` enabled by default.

### Other files created as you use Mesh

| File | Purpose |
|---|---|
| `memory.json` | Persistent key-value facts (`/memory`) |
| `notes.md` | Persistent Markdown notes (`/note`) |
| `PROJECT.md` | Optional per-project rules Mesh folds into its system prompt |

---

## 10. Common Workflows

**Ask Mesh to investigate before touching anything:**
```
/mode plan
> figure out why the auth middleware is rejecting valid tokens
```
When you're happy with the plan, `/mode build` and ask it to implement.

**Make a focused edit and review it before trusting it:**
```
> refactor the retry logic in providers/openai_provider.py to use exponential backoff
/diff
/diff undo        # if you don't like it
```

**Get a second opinion without switching your main model:**
```
/agent advisor is this database schema normalized correctly?
```

**Run tests until they pass:**
```
/loop pytest tests/
```

**Let it work on a big task semi-autonomously, but still supervised:**
```
/mode yolo
/guard mode supervised
> implement pagination across the /users and /orders endpoints, then run the test suite
```

**Save your place before a risky change:**
```
/checkpoint save before-refactor
... work happens ...
/checkpoint restore before-refactor   # if it goes sideways
```

**Keep long sessions from blowing the context window:**
Leave `auto_compact: true` (default) in `config.json`, or trigger manually with `/compact` — Mesh preserves the system prompt and summarizes older turns without breaking tool-call/result pairing.

---

## 11. Sub-Agent Workflows

Mesh includes five higher-level agent workflows layered on top of the base turn loop, all under `/agent`:

| Workflow | What it does | Good for |
|---|---|---|
| `explore [<n>] <task>` | Runs `n` (2–5) independent speculative branches in parallel, then synthesizes the strongest result | Open-ended problems with more than one reasonable approach |
| `squad <task>` | Sequential 4-stage pipeline: Architect → Coder → Tester → Auditor | Larger, well-defined feature work that benefits from role separation |
| `consensus <q> \| <proposal>` | One model critiques a proposal, a second (optionally different) model produces a vetted recommendation | High-stakes decisions where you want adversarial review |
| `delegate <task>` | Hands the task to a fully autonomous sub-agent with its own tool loop; reports back a summary | Well-scoped side tasks you don't want cluttering the main conversation |
| `advisor <question>` | One-shot second opinion from a separate model | Quick sanity checks without switching your active model |

`delegate` recursion depth (how many levels a sub-agent can itself delegate) is capped by `max_delegation_depth` in `config.json`, adjustable with `/agent delegate depth <n>`.

---

## 12. Memory, Notes & Learning Over Time

Mesh has three distinct persistence mechanisms — pick the right one for the job:

| Mechanism | Command | Best for |
|---|---|---|
| **Memory** | `/memory` | Structured key-value facts (e.g. `db_host: prod-db-1`), with semantic search so approximate queries still find the right entry |
| **Notes** | `/note` | Free-form running Markdown notes about the project |
| **Goal** | `/goal` | A single pinned objective folded directly into the system prompt for the rest of the session |
| **Reflexion** | `/reflexion` | Cross-session lessons learned from past tool failures, distilled into durable rules |
| **Dream** | `/dream` | Interactive extraction pass over conversation history to pull out notes/memory/skills you forgot to save explicitly |

Run `/dream` at the end of a long, productive session to capture anything worth keeping before you `/clear` or close Mesh.

---

## 13. Troubleshooting

**"Configuration Error" / can't reach the model**
- Check the relevant API key is exported (`echo $ANTHROPIC_API_KEY`, etc.) and matches `api_key_env` in `config.json`.
- For local providers (LM Studio, Ollama), confirm the server is actually running and `base_url` points at the right port.
- Check `/status` for the currently resolved provider and proxy settings.

**Corporate network / proxy issues**
- Use `/config proxy <url>` inside Mesh, or export `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` *before* launching — OS-level GUI proxy settings alone won't be picked up.

**A tool call keeps getting blocked**
- Check your current mode with `/mode` — `plan` and `review` block all mutating tools by design.
- Check `/guard` — if Safety Guard is on and in `supervised` mode, it may be waiting on a prompt you missed, or it assessed the action as high-risk.
- Check `/dirs` — file tools are restricted to the allow-listed directories.

**An edit failed with "target string not found"**
- Read the file with `show_hashes: true` and use `hash_edit` instead of `edit_file` for precise, drift-safe line-range replacement.

**Context window filling up too fast**
- Confirm `auto_compact` is enabled in `config.json`, or trigger `/compact` manually. Lower `auto_compact_threshold` (e.g. from `0.75` to `0.6`) to compact earlier.

**A background job seems stuck**
- `/jobs` to list, `/jobs log <id>` to inspect output, `/jobs stop <id>` to kill it.

**Undo an unwanted file change**
- `/diff` to review recent edits, `/diff undo` to revert.

---

## 14. Quick Reference Card

```
LAUNCH
  python main.py
  python main.py script.txt
  python main.py --file script.txt --non-interactive

TALK TO THE MODEL
  <message>            normal chat turn
  @file.py <message>   inject file content into the prompt
  !command              run shell directly, skip LLM
  #code                 run Python directly, skip LLM

SAFETY
  /mode [build|plan|review|yolo]
  /guard [on|off|mode supervised|autonomous|trust <tool>]
  /dirs

MODELS
  /status
  /models
  /switch <key> | /switch auto

DEV TOOLS
  /git status|diff|commit|push|branch
  /diff [undo]
  /loop <test_cmd>

MEMORY
  /goal | /note | /memory | /dream | /reflexion

SESSION
  /checkpoint save|fork|restore <tag>
  /compact
  /clear
  /retry
  /exit
```

---

*This guide reflects Mesh v1.0.0. For the authoritative feature list at any point in time, run `/help` inside Mesh or check the project's `README.md`.*
