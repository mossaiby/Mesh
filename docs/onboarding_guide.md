# ⚡ Mesh — Onboarding & User Guide

Mesh is a modular, text-based AI CLI harness written in Python. It connects to cloud or local LLMs (OpenAI-compatible endpoints, plus a native Anthropic driver), gives them a rich toolbox (file editing, shell, git, web, memory), and wraps the whole thing in a terminal REPL with streaming Markdown output, safety guardrails, and session persistence.

This guide takes you from zero to productive: installation, first run, core concepts, the full command reference, common workflows, configuration, and troubleshooting.

---

## Table of Contents

1. [What Mesh Is (and Isn't)](#1-what-mesh-is-and-isnt)
2. [Installation](#2-installation)
3. [First Run & API Keys](#3-first-run--api-keys)
4. [Managing Providers via CLI (`/providers`)](#4-managing-providers-via-cli-providers)
5. [Core Concepts](#5-core-concepts)
6. [Talking to Mesh](#6-talking-to-mesh)
7. [Command Reference](#7-command-reference)
8. [Operating Modes (Safety Model)](#8-operating-modes-safety-model)
9. [Tools & Concurrency Model](#9-tools--concurrency-model)
10. [Configuration Files & IDE Setup](#10-configuration-files--ide-setup)
11. [Common Workflows](#11-common-workflows)
12. [Sub-Agent Workflows](#12-sub-agent-workflows)
13. [Memory, Notes & Learning Over Time](#13-memory-notes--learning-over-time)
14. [Troubleshooting](#14-troubleshooting)
15. [Quick Reference Card](#15-quick-reference-card)

---

## 1. What Mesh Is (and Isn't)

**Mesh is:**
- A terminal-based AI agent loop, similar in spirit to Claude Code or Aider, but provider-agnostic.
- Built around a modular architecture: `InferenceCoordinator` handles streaming, metrics, and retry backoff, `ToolOrchestrator` handles concurrent read execution and sequential state mutation, and `SymbolIndexer` manages persistent AST symbol caching in `.mesh/symbols.cache.json`.
- Configurable at the model, provider, tool, retry, and safety level via `/providers`, `/models`, `/config`, `config.json`, `config.schema.json`, `mcps.json`, and `skills.json`.

**Mesh is not:**
- A GUI application — everything happens in your terminal.
- Tied to one AI provider — it works with OpenAI, Anthropic, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any custom OpenAI-compatible REST endpoint.
- A sandboxed environment — the shell, file, and Python execution tools operate directly on your real filesystem and processes. Read [Section 8](#8-operating-modes-safety-model) before turning off the Safety Guard.

---

## 2. Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | Required. |
| `tiktoken` | Installed automatically via `requirements.txt` for exact BPE token counting. |
| `tree-sitter` | Installed automatically via `requirements.txt` for polyglot codebase symbol indexing. |
| `ruff` / `flake8` | Optional — enables post-edit Python linting. |
| `eslint` | Optional — enables post-edit JS/TS linting. |
| `cargo` | Optional — enables post-edit Rust checks. |
| `gofmt` | Optional — enables post-edit Go formatting checks. |
| `npx` / `uvx` | Optional — only needed if you configure external stdio MCP servers in `mcps.json` that depend on Node.js or `uv`. |

### Install

```bash
git clone https://github.com/mossaiby/Mesh.git
cd Mesh
pip install -r requirements.txt
```

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

---

## 4. Managing Providers via CLI (`/providers`)

You can set up, list, test, and remove model providers live inside Mesh without touching `config.json`:

```bash
# List all configured providers and API key environment status
/providers list

# Add a cloud provider (e.g. DeepSeek)
/providers add deepseek https://api.deepseek.com/v1 "DeepSeek Cloud" DEEPSEEK_API_KEY

# Add a local provider (e.g. vLLM or local endpoint)
/providers add vllm http://localhost:8000/v1

# Test live connectivity to a provider endpoint
/providers test deepseek

# Add custom HTTP headers (e.g. for OpenRouter or custom gateways)
/providers header openrouter add HTTP-Referer https://github.com/mossaiby/Mesh

# Discover and add models from your newly added provider
/models discover deepseek
/models add deepseek *
```

---

## 5. Core Concepts

Understanding these ideas covers most of what you need to use Mesh effectively:

**Turn Loop & Inference Coordinator.** When you send a prompt, `InferenceCoordinator` streams completions from the active model, accurately accounting for prompt, completion, and cached tokens via `tiktoken`. It auto-compacts context when nearing window limits and supports sticky auto-routing (`/switch auto`).

**Concurrent Tool Orchestrator.** When the model returns tool calls, `ToolOrchestrator` dynamically inspects whether each call is read-only. Contiguous read-only calls (like reading multiple files, running symbol searches, and checking git status) run concurrently via `asyncio.gather()`, while writes and shell commands run sequentially.

**Background Symbol Indexer & `.mesh/symbols.cache.json`.** Codebase AST symbols are indexed in the background on a worker thread pool. Parsed signatures, classes, functions, and docstrings are saved to disk in `.mesh/symbols.cache.json`, enabling instantaneous startup and cache invalidation based on file modification times (`mtime`) and byte sizes.

**Persistent History (`.mesh/history.txt`).** Input history persists across CLI launches so you can navigate prior commands using the `↑` and `↓` arrow keys or manage entries via `/history`.

**Provider Backoff & Retries.** Network hiccups and HTTP 429 rate limit spikes are handled automatically via configurable exponential backoff with randomized jitter (`/config set retry`).

**Modes & Safety Guard.** Blanket tool policies (`build`, `plan`, `review`, `chat`, `yolo`) combine with the LLM-backed `SafetyGuard` to prevent accidental damage.

---

## 6. Talking to Mesh

Anything you type that doesn't start with `/`, `!`, or `#` is sent to the model as a normal chat message.

**Shortcuts:**

| Prefix | Meaning |
|---|---|
| `/command args` | Runs a slash command directly — see [Section 7](#7-command-reference). |
| `!command` | Runs a shell command immediately, without going through the LLM. Equivalent to `/shell`. |
| `#code` | Executes a line of Python in a persistent session namespace. Equivalent to `/python`. |
| `@filename` | Inside a normal prompt, `@` mentions are expanded to inject file content directly into your message. |

---

## 7. Command Reference

Type `/help` any time for a live categorized list, or `/help <command>` for detailed usage.

### ⚙️ Models & Providers

| Command | Description |
| --- | --- |
| `/providers [list\|add\|remove\|test\|header] <args>` | Configure provider endpoints without manual editing of `config.json`. |
| `/status` | Active model, router model, proxy, thinking mode, symbol count, disk cache state, git branch, metrics, context usage. |
| `/models` | List configured models (`/models`), discover remote endpoints (`/models discover`), batch-add models (`/models add openrouter *free*`), or remove models (`/models remove <key>`). |
| `/switch` | Switch model or enable routing: `/switch <key>`, `/switch auto`, `/switch router [<key>]`. |
| `/config` | Configure subsystems: `distill`, `proxy`, `repair`, `hooks`, `compact`, `thinking`, `effort`, `tokens`, `cost`, `statistics`, `schema`, `set`. |
| `/mode` | Switch operating mode: `/mode build \| plan \| review \| chat \| yolo`. |
| `/guard` | Configure the tool-call Safety Guard: `on`, `off`, `mode supervised\|autonomous`, `model [<key>]`, `trust <tool>`. |

### 🤖 Agents & Workflows

| Command | Description |
| --- | --- |
| `/agent [explore\|squad\|consensus\|delegate\|advisor] <args>` | Run sub-agent swarm and reasoning workflows |
| `/loop <test_cmd>` | Iterative auto-fix loop: runs a test/build command, feeds failures back to the model, retries. |
| `/jobs` | View/manage background async processes: `/jobs log <id>`, `/jobs stop <id>`, `/jobs clear`. |

### 🛠️ Workspace & Developer Tools

| Command | Description |
| --- | --- |
| `/cd <path>` | Change working directory; syncs allowed directories, `PROJECT.md` rules, and triggers background symbol reindexing. |
| `/project` | View/reload project rules (`PROJECT.md`) or the repo architecture map (`/project map`). Use `/project reload` to reindex symbols. |
| `/git` | `status`, `diff`, `commit` (AI-generated commit message), `push`, `branch`. |
| `/diff` | View colorized diffs of recent file edits (`/diff`), or revert them (`/diff undo`). |
| `/shell` \| `!` | Direct shell execution outside the LLM loop. |
| `/python` \| `#` | Direct Python execution in a persistent namespace. |
| `/script <file>` | Runs commands and prompts line-by-line from a script file. |

### 🧠 Memory & Knowledge

| Command | Description |
| --- | --- |
| `/goal` | View/set a pinned session goal, folded directly into the system prompt. |
| `/note` | View/edit persistent Markdown notes (`notes.md`). |
| `/memory` | Manage the persistent key-value store (`memory.json`), including semantic search. |
| `/dream` | Interactively extract durable notes, memory facts, and skills from conversation history. |
| `/reflexion` | View or distill cross-session error lessons into durable system rules (`/reflexion distill`). |

### 🔌 Context & Integration

| Command | Description |
| --- | --- |
| `/context` | Raw conversation history, active tool names, MCP status. |
| `/system [text]` | Show or set the system prompt. |
| `/tools [on\|off]` | List registered tools with schemas, or toggle tool-calling entirely. |
| `/skills` | Enable/disable/register skills. |
| `/dirs` | Manage the `PermissionManager` allow-list of directories. |
| `/mcps [on\|off]` | View connected MCP servers or toggle them. |
| `/compact` | Manually trigger semantic summarization of older conversation history. |

### 💻 Session & System

| Command | Description |
| --- | --- |
| `/help [command]` | Command categories, or usage for one command. |
| `/history [<limit>\|clear]` | View or clear interactive terminal command history (`.mesh/history.txt`). |
| `/session` | Save, load, list, or delete disk session snapshots under `sessions/`. |
| `/log` | Toggle and configure Markdown session logging. |
| `/checkpoint` | `save <tag>`, `fork <branch>`, `restore <tag>` — session state snapshots. |
| `/clear` | Clear conversation history; keeps system prompt, goal, and skills. |
| `/retry` | Re-run the last LLM turn. |
| `/debug [on\|off]` | Show Chain-of-Thought reasoning and sub-agent execution traces. |
| `/exit` | Gracefully stop background jobs, close MCP connections, and quit. |

---

## 8. Operating Modes (Safety Model)

Mesh has two independent safety layers: **mode** (what tools are allowed) and **Safety Guard** (risk assessment before execution).

### Modes

| Mode | Tool access | When to use it |
|---|---|---|
| **build** *(default)* | Full — reads and writes | Normal day-to-day work. |
| **plan** | Read-only: `read_file`, `glob_files`, `web_search`, `web_fetch`, `consult_advisor` | Propose a plan without modifying state. |
| **review** | Read-only, same tool set as `plan` | Critique existing code for bugs and security risks. |
| **chat** | Conversation only (`calculator`, `web_search`, `web_fetch`, `advisor`, `memory`) | General Q&A and research. |
| **yolo** | Full access, no confirmation prompts for ambiguous-risk actions | Fast iterative work. High-risk actions are still blocked. |

---

## 9. Tools & Concurrency Model

### Parallel Read-Only Execution
When the model requests multiple tool calls in a single turn, `ToolOrchestrator` partitions them:
- **Read-Only Batches** (`read_file`, `glob_files`, `web_search`, `web_fetch`, `search_symbols`, `calculator`, `git_status`, `git_diff`, `memory` read): execute concurrently via `asyncio.gather()`.
- **Mutating Tools** (`write_file`, `edit_file`, `hash_edit`, `shell`, `job`, `git_commit`, `git_push`, MCP tools): execute sequentially in order.

### Editing Strategies
- **`hash_edit`**: Uses 4-character line hashes (`show_hashes: true` in `read_file`) to guarantee drift-free replacement.
- **`edit_file`**: Exact string matching with fuzzy block fallback at ≥85% similarity.

---

## 10. Configuration Files & IDE Setup

### `config.json` & IDE Schema Auto-Completion
`config.json` links directly to `config.schema.json`:

```json
{
  "$schema": "./config.schema.json",
  "active_model": "anthropic:claude-3-7-sonnet-20250219",
  "retry_settings": {
    "retries": 3,
    "initial-delay": 1.0,
    "max-delay": 30.0,
    "backoff-factor": 2.0,
    "jitter": true
  }
}
```

In VS Code, Cursor, or JetBrains, this provides instant autocomplete, hover documentation, and validation for all configuration keys. Use `/config schema` to regenerate the schema file at any time.

### Fine-Tuning via `/config set`
Fine-tune system settings live from the CLI:
```
/config set retry retries 5
/config set retry initial-delay 0.5
/config set timeout web 30
/config set budget repo-map 1000
```

---

## 11. Common Workflows

**Set up a new provider and discover models:**
```
/providers add deepseek https://api.deepseek.com/v1 "DeepSeek Official" DEEPSEEK_API_KEY
/providers test deepseek
/models discover deepseek
/models add deepseek *
/switch deepseek:deepseek-reasoner
```

**Investigate before modifying:**
```
/mode plan
> analyze the authentication middleware in auth.py
/mode build
> implement the recommended fix
/diff
/git commit
```

**Consult the second-opinion advisor:**
```
/agent advisor should we use Redis or SQLite for the background queue?
```

**Run autonomous test-and-repair:**
```
/loop pytest tests/
```

**Take a snapshot before refactoring:**
```
/checkpoint save before-refactor
... edits ...
/checkpoint restore before-refactor   # if needed
```

---

## 12. Sub-Agent Workflows

| Workflow | What it does | Good for |
|---|---|---|
| `explore [<n>] <task>` | Runs `n` (2–5) speculative branches in parallel and synthesizes the winning solution | Ambiguous problems with multiple valid paths |
| `squad <task>` | 4-stage pipeline: Architect → Coder → Tester → Auditor | Large, multi-faceted feature development |
| `consensus <q> \| <proposal>` | Red-team auditor critiques, consensus referee verifies | High-stakes architectural choices |
| `delegate <task>` | Autonomous sub-agent handles task with isolated tool loop | Well-scoped side tasks |
| `advisor <question>` | Quick second opinion without switching models | Fast sanity checks |

---

## 13. Memory, Notes & Learning Over Time

| Mechanism | Command | Best for |
|---|---|---|
| **Memory** | `/memory` | Structured key-value facts with semantic natural-language recall |
| **Notes** | `/note` | Free-form running Markdown notes (`notes.md`) |
| **Goal** | `/goal` | Pinned objective and criteria preserved across compactions |
| **Reflexion** | `/reflexion` | Cross-session lessons distilled from past tool errors |
| **Dream** | `/dream` | Post-session extraction of reusable notes, memory facts, and skills |

---

## 14. Troubleshooting

**Rate limits / 429 Errors**
- Mesh automatically retries with exponential backoff and jitter. Adjust via `/config set retry retries 5` or `/config set retry initial-delay 2.0`.

**Symbol search or repo map seems outdated**
- Run `/project reload` to force a background scan and update `.mesh/symbols.cache.json`.

**Context window filling up**
- Verify `auto_compact` is on (`/config compact on`). Lower threshold with `/config set compact threshold 60`.

---

## 15. Quick Reference Card

```
LAUNCH
  python main.py
  python main.py --session <name>
  python main.py --resume

SHORTCUTS
  <message>            normal chat turn
  @file.py <message>   inject file content into prompt
  !command             run shell command directly
  #code                run Python snippet directly

PROVIDERS & MODELS
  /providers list|add|remove|test|header
  /models discover|add|remove
  /switch <key> | /switch auto

CONFIG & SETTINGS
  /status
  /history [<limit>|clear]
  /config set retry retries 5
  /config schema

SAFETY & MODES
  /mode [build|plan|review|chat|yolo]
  /guard [on|off|mode supervised|autonomous|trust <tool>]
  /dirs

DEV TOOLS
  /git status|diff|commit|push|branch
  /diff [undo]
  /loop <test_cmd>
  /project [map|reload]

PERSISTENCE
  /session save|load|list|delete
  /checkpoint save|fork|restore <tag>
  /memory | /note | /goal | /dream | /reflexion
```
