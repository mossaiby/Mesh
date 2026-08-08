# ⚡ Mesh AI Harness

A modular, text-based AI CLI harness built in Python. Designed for local and cloud-hosted LLMs, featuring **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **Sub-Agent Proxy Distillation**, **Declarative Skills**, **Directory Permissions**, and **Semantic Context Compaction**.

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
- **Real-Time Token Streaming & CoT**: Live Markdown rendering with code syntax highlighting and toggleable Chain of Thought (CoT) reasoning displays (`/debug on|off`).

---

## 🏗️ Architecture Overview

```text
               ┌─────────────────────────────────────────────────────────┐
               │                      User (CLI)                         │
               └────────────────────────────┬────────────────────────────┘
                                            │
                                  ┌─────────▼─────────┐
                                  │   AI Harness CLI  │
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
git clone https://github.com/your-username/mesh-ai-harness.git
cd mesh-ai-harness
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

### 4. Run the Harness

```bash
python main.py
```

---

## 🛠️ Slash Commands Reference

| Command | Description |
| :--- | :--- |
| `/help` | List all available slash commands. |
| `/status` | Display a detailed status overview of active models, tools, MCPs, skills, and memory. |
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
| `/retry` | Re-run the last completion turn (strips the last assistant/tool response). |
| `/debug [on|off]` | Toggle debug mode to show Chain of Thought (CoT) and sub-agent logs. |
| `/clear` | Clear conversation history while keeping system prompt and skills intact. |
| `/exit` | Safely close MCP process connections and exit. |

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints and model configurations, including model-specific system prompts.

```json
{
  "active_model": "llama3-groq",
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
      "system_prompt": "You are Llama 3 70B running on Groq acceleration, a fast AI assistant."
    },
    "gemma-4-e4b-lmstudio": {
      "name": "Gemma 4 E4B (Local)",
      "provider": "lmstudio",
      "model_id": "google/gemma-4-e4b",
      "system_prompt": "You are Gemma 4 E4B running locally via LM Studio."
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

## 🛡️ Security & Directory Permissions

The harness includes a built-in `PermissionManager`. File tools (`read_file`, `write_file`, `edit_file`, `glob_files`, `run_shell_command`) validate paths against `/dirs`.

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
ai_harness/
├── requirements.txt         # Project Python dependencies
├── models.json              # Provider endpoints and model configurations
├── mcps.json                # Model Context Protocol server definitions
├── skills.json              # Declarative skills configuration
├── memory.json              # Persistent key-value memory storage
├── notes.md                 # Persistent Markdown notes
├── config.py                # Configuration manager and Pydantic schemas
├── subagent.py              # Sub-Agent Proxy distillation engine
├── compaction.py            # Semantic context window compaction module
├── main.py                  # Main CLI entry point and orchestration loop
├── providers/
│   ├── __init__.py
│   └── openai_provider.py   # Async OpenAI-compatible client wrapper
├── render/
│   ├── __init__.py
│   └── stream_renderer.py   # Rich Markdown & CoT streaming renderer
├── tools/
│   ├── __init__.py          # Tool exports
│   ├── base.py              # BaseTool class with dynamic schema injection
│   ├── registry.py          # Central tool execution and proxy dispatcher
│   ├── permissions.py       # PermissionManager and directory authorization
│   ├── native_tools.py      # File, glob, and shell command tools
│   ├── web_tools.py         # Key-less web search (DDG) & web fetch tools
│   ├── memory_tool.py       # Key-value memory tool
│   ├── note_tool.py         # Markdown note manager tool
│   ├── todo_tool.py         # Multi-step task tracking tool
│   └── ask_tool.py          # Interactive human-in-the-loop decision tool
├── commands/
│   ├── __init__.py
│   └── registry.py          # Slash command registry and dispatcher
└── skills/
    ├── __init__.py
    ├── base.py              # Skill base class definition
    ├── registry.py          # Skill manager and instruction composer
    └── code_skill.py        # Python coding skill implementation
```

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).
