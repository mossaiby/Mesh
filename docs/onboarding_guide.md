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
| `/models` | List configured models (`/models`), discover remote endpoints (`/models discover`), or batch-add models (`/models add openrouter *free*`). |
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
| `/session` | Save, load, list, or delete disk session snapshots under `sessions/`. |
| `/log` | Toggle and configure Markdown session logging. |
| `/checkpoint` | `save <tag>`, `fork <branch>`, `restore <tag>` — session state snapshots. |
| `/clear` | Clear conversation history; keeps system prompt, goal, and skills. |
| `/retry` | Re-run the last LLM turn.
