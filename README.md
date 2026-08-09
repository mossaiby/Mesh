# ⚡ Mesh

**v1.0.0**

A modular, text-based AI CLI built in Python. Designed for local and cloud-hosted LLMs, featuring **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **Sub-Agent Proxy Distillation**, **Declarative Skills**, **Directory Permissions**, and **Semantic Context Compaction**.

---

## 🌟 Key Features

- **Multi-Provider OpenAI Compatibility**: Seamlessly connect to OpenAI, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint via `models.json`.
- **Interactive Model Switcher (`/switch`)**: Switch active models on the fly using a cross-platform arrow-key selection menu or command arguments.
- **Sub-Agent Proxy Architecture (`/proxy`)**: Reduces context window noise. Heavy tools (`read_file`, `shell`, `web_search`, MCP tools) require an `_intent` parameter. A dedicated sub-agent distills raw outputs into concise, structured JSON before handing them back to the main LLM.
- **Model Context Protocol (MCP) (`/mcps`)**: Native stdio JSON-RPC MCP client supporting `mcps.json`. Dynamically discovers and executes tools from external MCP servers (SQLite, Filesystem, GitHub, etc.) with global and per-server toggles.
- **Modular Skills Subsystem (`/skills`)**: Package specialized system prompts and tools into reusable skills. Supports dynamic loading from `skills.json` or custom Python classes.
- **Rich Native Tool Suite**:
  - **File Operations**: `read_file`, `write_file`, `edit_file`, `glob_files`.
  - **System Shell**: `run_shell_command` with execution timeouts.
  - **Zero-Key Web Search & Fetch**: `web_search` (DuckDuckGo search without API keys) and `web_fetch` (clean HTML-to-text extraction).
  - **Human-in-the-Loop**: `ask_user` with interactive arrow-key option selection and free-form input.
  - **Session State**: `memory` (persistent JSON key-value store), `note_manager` (persistent `notes.md` manager), and `todo_manager` (multi-step task tracking).
- **Directory Authorization & Security (`/dirs`)**: `PermissionManager` enforces directory boundaries. If a tool requests path access outside allowed directories, an interactive prompt asks the human user for access permission.
- **Semantic Context Compaction (`/compact`)**: Summarizes older conversation context using the LLM without truncating system prompts or breaking active tool-call history pairs.
- **Dream Extraction (`/dream`)**: Runs a dedicated analysis pass over the current conversation to surface durable notes, key-value memory facts, and reusable Skills worth keeping - with an interactive review before anything is persisted.
- **Real-Time Token Streaming & CoT**: Live Markdown rendering with code syntax highlighting and toggleable Chain of Thought (CoT) reasoning displays (`/debug on|off`).
- **Unified Theming**: A single shared, themed console (`theme.py`) applies one consistent, semantic color palette across every command, tool log, and prompt in the CLI.

---

## 🏗️ Architecture Overview

```text
               ┌─────────────────────────────────────────────────────────┐
               │                      User (CLI)                         │
               └────────────────────────────┬────────────────────────────┘
                                            │
                                  ┌─────────▼─────────┐
                                  │      Mesh CLI      │
                                  └─────────┬─────────┘
                                            │
        ┌───────────────────┬───────────────┼───────────────┬───────────────────┐
        │                   │               │               │                   │
┌───────▼───────┐   ┌───────▼───────┐  ┌────▼────┐   ┌──────▼──────┐   ┌────────▼────────┐
│ OpenAI / Local│   │ Tool Registry │  │ Skills  │   │ MCP Client  │   │ Sub-Agent Proxy │
│  Providers    │   │  & Security   │  │ Registry│   │ (mcps.json) │   │  (Distillation) │
└───────────────┘   └───────────────┘  └─────────┘   └─────────────┘   └─────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python **3.10** or higher
- Node.js / `npx` (optional, for Node-based MCP servers)
- `uv` / `uvx` (optional, for Python-based MCP servers)

### 2. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/mossaiby/Mesh.git
cd Mesh
pip install -r requirements.txt
```

### 3. Configure API Keys

Set your API environment variables (or configure them in `models.json`):

```bash
# Cloud Providers
export OPENAI_API_KEY="sk-..."
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-..."

# Local Providers (Optional)
export OLLAMA_API_KEY="dummy"
export LOCAL_API_KEY="dummy"
```

### 4. Run Mesh

```bash
python main.py
```

---

## 🛠️ Slash Commands Reference

| Command | Description |
| :--- | :--- |
| `/help` | List all available slash commands. |
| `/status` | Display a detailed status overview of active models, tools, MCPs, skills, and memory. |
| `/version` | Show the current Mesh version. |
| `/models` | List all configured models and their provider endpoints. |
| `/switch [key]` | Interactively switch models using arrow keys, or directly by model key. |
| `/context` | Display conversation history, active tool schemas, and MCP statuses. |
| `/system [text]` | Display, update, or clear (`/system clear`) the current system prompt. |
| `/skills [enable|disable] <name>` | List registered skills or enable/disable specific skills. |
| `/tools [on|off]` | View registered tools or toggle tool inclusion/execution globally. |
| `/proxy [on|off]` | Toggle Sub-Agent Proxy tool output distillation on or off. |
| `/dirs [add|remove|clear] <path>` | Manage authorized directory paths for file and shell operations. |
| `/mcps [on|off]` | View connected MCP servers or toggle MCP tools globally/per-server. |
| `/note [append|clear] [text]` | View, append to, or clear persistent project notes (`notes.md`). |
| `/memory [save|get|delete|clear]` | View or manage persistent key-value items (`memory.json`). |
| `/compact` | Semantically compact older conversation history using the LLM. |
| `/dream` | Analyze the conversation and interactively extract candidate notes, memory facts, and reusable skills. |
| `/retry` | Re-run the last completion turn (strips the last assistant/tool response). |
| `/debug [on|off]` | Toggle debug mode to show Chain of Thought (CoT) and sub-agent logs. |
| `/clear` | Clear conversation history while keeping system prompt and skills intact. |
| `/exit` | Safely close MCP process connections and exit. |

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints and model configurations, plus a single global system prompt shared by every model. Mesh always talks to whichever model is active with the same base instructions - switching models (`/switch`) changes only the endpoint/model ID, never the assistant's persona or instructions. Use `/system` to view or temporarily override the prompt for the current session.

```json
{
  "active_model": "llama3-groq",
  "system_prompt": "You are a helpful, intelligent AI assistant running inside Mesh, an interactive terminal CLI.",
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
      "model_id": "llama-3.3-70b-versatile"
    },
    "gemma-4-e4b-lmstudio": {
      "name": "Gemma 4 E4B (Local)",
      "provider": "lmstudio",
      "model_id": "google/gemma-4-e4b"
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

### `skills.json`
Configures declarative skills that inject specialized instructions and tools.

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

## 🤖 Sub-Agent Proxy Architecture

When `/proxy on` is active:
1. **Dynamic Intent Injection**: Heavy tools (`read_file`, `shell`, `web_search`, `mcps`) dynamically require an `_intent` string parameter in their function schema.
2. **Execution & Interception**: The main LLM specifies why it is calling the tool (e.g. `_intent="Find active_model key"`).
3. **Sub-Agent Distillation**: `SubAgentProxy` intercepts the raw tool output, passes it through a focused sub-agent pass, and extracts only the relevant information matching the requested intent.
4. **Context Optimization**: The main LLM receives a clean, structured JSON summary instead of thousands of lines of raw file content or build logs.

*Note: Short outputs (under 4 lines / 300 characters) and lightweight tools (`calculator`, `memory`) automatically bypass distillation for zero-latency execution.*

---

## \U0001F4A4 Dream Extraction (`/dream`)

`/dream` runs a dedicated, out-of-band analysis pass (implemented in `dream.py`) over the current conversation - separate from the main chat loop - to surface durable knowledge that's easy to lose once the session ends:

1. **Transcript Analysis**: The full conversation (minus the system prompt) is sent to the active model with a focused extraction prompt asking it to return structured JSON only.
2. **Three Categories**: The model identifies candidate **notes** (durable facts/decisions worth logging), **memory** (small key-value facts worth recalling automatically next session), and **skills** (a workflow that was clearly repeated, or that you explicitly asked Mesh to remember).
3. **Interactive Review**: Each category is listed with numbered items. You choose which ones to keep per category (`all`, `none`, or specific numbers like `1,3`) - nothing is written until you confirm.
4. **Persistence**: Accepted notes are appended to `notes.md`, accepted memory facts are merged into `memory.json`, and accepted skills are registered live (so they take effect immediately) and written to `skills.json` as `DeclarativeSkill` entries.

`/dream` is conservative by design - it won't invent a skill from a single one-off request, only from a pattern that actually recurred or that you asked to be remembered.

---

## 🎨 Unified Theming

Mesh renders every command, prompt, and log line through a single shared, themed `rich.console.Console` instance defined in `theme.py`, instead of each module picking its own colors ad hoc. All output maps onto a small set of semantic styles:

| Style | Meaning | Used for |
| :--- | :--- | :--- |
| `brand` | Mesh identity | Startup/shutdown banners |
| `success` | Positive outcome | Enabled/connected states, successful operations |
| `error` | Failure | Denials, disabled/disconnected states, exceptions |
| `warning` | Caution | Hints, clears, destructive-ish actions |
| `label` | Field name | Keys in `/status`, `/models`, `/dirs`, etc. |
| `accent` | Highlight | Active selections, secondary emphasis |
| `info` | Informational header | The assistant reply header |
| `text` | Plain emphasis | Generic bolded values |
| `muted` | De-emphasis | Secondary/contextual detail (maps to Rich's built-in `dim`) |

Every module imports the shared instance — `from theme import console` — rather than instantiating its own `Console()`, so the palette can be changed in exactly one place (`theme.py`) and it updates everywhere consistently.

---

## 🛡️ Security & Directory Permissions

Mesh includes a built-in `PermissionManager`. File tools (`read_file`, `write_file`, `edit_file`, `glob_files`, `run_shell_command`) validate paths against `/dirs`.

If a tool attempts to access a path outside allowed directories, an interactive menu is displayed:

```text
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

```text
Mesh/
├── requirements.txt         # Project Python dependencies
├── models.json               # Provider endpoints and model configurations
├── mcps.json                 # Model Context Protocol server definitions
├── skills.json                # Declarative skills configuration
├── memory.json                # Persistent key-value memory storage
├── notes.md                   # Persistent Markdown notes
├── version.py                 # Single source of truth for the app version
├── theme.py                   # Shared Rich theme & console instance
├── config.py                  # Configuration manager and Pydantic schemas
├── subagent.py                # Sub-Agent Proxy distillation engine
├── compaction.py               # Semantic context window compaction module
├── dream.py                    # /dream conversation analysis & knowledge extraction
├── main.py                    # Main CLI entry point and orchestration loop
├── providers/
│   ├── __init__.py
│   └── openai_provider.py     # Async OpenAI-compatible client wrapper
├── render/
│   ├── __init__.py
│   └── stream_renderer.py     # Rich Markdown & CoT streaming renderer
├── tools/
│   ├── __init__.py            # Tool exports
│   ├── base.py                # BaseTool class with dynamic schema injection
│   ├── registry.py            # Central tool execution and proxy dispatcher
│   ├── permissions.py         # PermissionManager and directory authorization
│   ├── native_tools.py        # File, glob, and shell command tools
│   ├── web_tools.py           # Key-less web search (DDG) & web fetch tools
│   ├── memory_tool.py         # Key-value memory tool
│   ├── note_tool.py           # Markdown note manager tool
│   ├── todo_tool.py           # Multi-step task tracking tool
│   └── ask_tool.py            # Interactive human-in-the-loop decision tool
├── commands/
│   ├── __init__.py
│   └── registry.py            # Slash command registry and dispatcher
├── mcp/
│   ├── __init__.py
│   └── client.py               # Stdio JSON-RPC MCP client & manager
└── skills/
    ├── __init__.py
    ├── base.py                 # Skill base class definition
    ├── registry.py              # Skill manager and instruction composer
    └── code_skill.py            # Python coding skill implementation
```

---

## 🩹 Changelog / Bug Fixes (v1.0.0)

- **Missing `httpx` dependency**: `tools/web_tools.py` imports `httpx` for `web_search`/`web_fetch`, but it was never listed in `requirements.txt`, so a clean install would crash the first time either tool ran. Added to `requirements.txt`.
- **Directory-permission misclassification**: `PermissionManager` used to guess "is this a directory?" from whether the path had a file suffix, which misclassified extensionless existing files (`Makefile`, `LICENSE`, `Dockerfile`, ...) as directories — approving "Always Allow" would add the *file itself* to the allow-list instead of its parent directory. Now uses `Path.is_dir()`.
- **Web search title/snippet misalignment**: `web_search` matched result titles and snippets purely by their position in two independently-filtered lists, which could silently pair a title with the wrong snippet whenever unrelated links were filtered out. The link regex is now scoped to DuckDuckGo Lite's actual result-link anchors, and titles/snippets are paired by their original row index rather than by post-filter position.
- **Inconsistent tool de-registration**: `SkillRegistry.set_skill_state` reached directly into `ToolRegistry`'s private `_tools` dict to remove a disabled skill's tools. Switched to the registry's public `unregister()` method.
- **Consolidated system prompt**: Each model in `models.json` used to carry its own near-duplicate `system_prompt`. Replaced with a single global `system_prompt` on the top-level config, so the assistant's persona and instructions stay consistent across `/switch`, and there's one place to edit instead of one per model.

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).
