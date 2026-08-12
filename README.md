# ⚡ Mesh

**v1.0.0**

A modular, text-based AI CLI built in Python for local and cloud-hosted LLMs. Designed for developer productivity with **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **sub-agent swarm workflows**, **native Anthropic API support (with Prompt Caching & Extended Thinking)**, **dynamic LLM model routing**, **hash-anchored & fuzzy file editing**, **post-edit linter hooks**, **Git native tools**, **session checkpointing**, and **semantic context compaction**.

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

### 2. Configure API Keys & Network Proxies
Set environment variables for cloud or local providers (or configure endpoints in `models.json`):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
export OPENROUTER_API_KEY="sk-or-..."

# Optional: Configure Network Proxy via CLI or env vars
# Mesh supports HTTP, HTTPS, and SOCKS5 proxies (via httpx[socks])
export HTTP_PROXY="http://proxy.corp.com:8080"
export HTTPS_PROXY="http://proxy.corp.com:8080"
export ALL_PROXY="socks5://127.0.0.1:1080"
```

You can also set or clear network proxies directly inside Mesh using `/config proxy <url>` or `/config proxy clear`.

> **OS GUI Proxy Settings Note:** If your proxy is configured solely in OS system settings (Windows Internet Options or macOS Network Settings) without exporting terminal environment variables, Python CLI tools will not see it. Always export standard `HTTP_PROXY`/`HTTPS_PROXY` variables in your terminal or configure `/config proxy <url>` inside Mesh.

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

### ⚙️ Models & Settings
| Command | Description |
| :--- | :--- |
| **`/status`** | Display active model, router model, network proxy, thinking mode, effort level, tools, MCPs, symbol count, branch, token metrics display settings, and context status. |
| **`/models`** | List configured models with tags/descriptions (`/models`), discover remote endpoints (`/models discover`), or batch-add models (`/models add openrouter *free*`). |
| **`/switch`** | Switch active model/mode: `/switch auto` (sticky dynamic router), `/switch router [<key>]`, or directly via key (`/switch <key>`). |
| **`/config`** | Configure system options: `/config distill`, `/config proxy`, `/config repair`, `/config hooks`, `/config compact`, `/config thinking`, `/config effort`, `/config tokens`, `/config cost`, `/config statistics`. |
| **`/mode`** | Switch operating mode (`/mode build`, `/mode plan`, `/mode review`, `/mode yolo`). |
| **`/guard`** | Configure tool-call safety guard risk assessment (`/guard on`, `/guard mode supervised|autonomous`). |

### 🤖 Agents & Workflows
| Command | Description |
| :--- | :--- |
| **`/agent`** | Sub-agent swarm & reasoning workflows: `/agent explore`, `/agent squad`, `/agent consensus`, `/agent delegate`, `/agent advisor`. |
| **`/loop`** | Iterative auto-test/fix loop (`/loop <test_cmd>`). |
| **`/jobs`** | View or manage async background processes (`/jobs log <id>`, `/jobs stop <id>`, `/jobs clear`). |

### 🛠️ Workspace & Developer Tools
| Command | Description |
| :--- | :--- |
| **`/cd`** | Change working directory & automatically sync allowed directories, project rules (`PROJECT.md`), and AST symbol index. |
| **`/project`** | View or reload workspace project rules (`PROJECT.md`) or repository architecture map (`/project map`). |
| **`/git`** | Vendor-agnostic Git workflow: `/git status`, `/git diff`, `/git commit` (AI auto-commit), `/git push`, `/git branch`. |
| **`/diff`** | View colorized unified diffs of file edits (`/diff`), or revert recent edits (`/diff undo`). |
| **`/shell` \| `!`** | Direct shell execution (`! <cmd>`) — runs directly without modifying conversation history or triggering LLM turns. |
| **`/python` \| `#`** | Direct Python execution (`# <code>`) inside a persistent session namespace without modifying conversation history. |
| **`/script`** | Execute commands and prompts line-by-line from a script file (`/script <file.txt>`). |

### 🧠 Memory & Knowledge
| Command | Description |
| :--- | :--- |
| **`/goal`** | View, set, or update pinned session goals folded directly into the system prompt. |
| **`/note`** | View or edit persistent Markdown project notes (`notes.md`). |
| **`/memory`** | Manage persistent key-value facts (`memory.json`) and semantic meaning search. |
| **`/dream`** | Interactively extract durable notes, memory facts, and skills from conversation history. |
| **`/reflexion`** | View or distill cross-session error lessons into durable system rules (`/reflexion distill`). |

### 🔌 Context & Integration
| Command | Description |
| :--- | :--- |
| **`/context`** | Display raw conversation history, active tool names, and MCP status. |
| **`/system`** | Show current system prompt (rendered in Markdown) or set it (`/system <text>`). |
| **`/tools`** | List registered tools with full detailed descriptions and schemas, or toggle inclusion (`/tools on|off`). |
| **`/skills`** | Enable, disable, or register custom system skills. |
| **`/dirs`** | Manage authorized directory paths enforced by `PermissionManager`. |
| **`/mcps`** | View connected Model Context Protocol servers or toggle tools (`/mcps on|off`). |
| **`/compact`** | Semantically summarize older conversation context using the LLM. |

### 💻 Session & System
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

### 🧠 Native Anthropic Support (Prompt Caching & Extended Thinking)
* **Native Anthropic API Integration:** Built-in driver for Claude models (`claude-3.7-sonnet`, `claude-3.5-haiku`, etc.) with text, tool calls, and streaming CoT.
* **Prompt Caching (`cache_control`):** Automatically attaches ephemeral prompt cache headers to system instructions and tools for a **90% discount** on cached tokens and faster response times.
* **Thinking & Effort Controls (`/config thinking`, `/config effort`):** Toggle extended thinking on/off and tune reasoning budget levels (`low`, `medium`, `high`) across Anthropic and OpenAI reasoning models.

### 🌐 Network Proxy & SOCKS5 Support (`/config proxy`)
* **HTTP, HTTPS & SOCKS5 Proxy:** Seamlessly routes Mesh LLM traffic, model discovery, and web tools through enterprise HTTP/HTTPS proxies or local SOCKS5 tunnels (`socks5://127.0.0.1:1080`).
* **Runtime & Persistent Config:** Use `/config proxy <url>` inside Mesh to apply and persist network proxy settings immediately without restarting.

### 🔀 Dynamic LLM Model Router (`/switch auto`)
* **Sticky Auto-Routing:** Enters auto mode via `/switch auto`. Every incoming non-slash prompt is analyzed by the configured `router_model` before execution.
* **Metadata & Tag Awareness:** Inspects model tags (`free`, `reasoning`, `coding`, `fast`, `large-context`), descriptions, context windows, and providers to pick the optimal model for the prompt.
* **Pre-Streaming Notification:** Prints a clear notification header displaying the selected target model and short routing rationale before generation begins.

### 🎯 Hash-Anchored & Fuzzy Block File Editing
* **Hash-Anchored Edits (`hash_edit`):** Passing `show_hashes: true` to `read_file` returns line-numbered content with stable 4-character hashes (e.g. `L12|a3f1| def foo():`). Using `hash_edit` verifies line hashes before applying changes, guaranteeing safe, drift-free replacements.
* **Fuzzy Block Matching (`edit_file`):** If exact string replacement fails in `edit_file` due to minor indentation or whitespace variations, Mesh calculates sequence similarity using `difflib.SequenceMatcher`. If similarity is $\ge 85\%$, the target block is replaced automatically.

### ⚡ Post-Edit Linter Hooks (`/config hooks`)
* **Automated Post-Edit Checks:** Automatically detects installed linters (`ruff`, `flake8`, `eslint`, `cargo check`, `gofmt`) using `shutil.which()` after file edits (`write_file`, `edit_file`, `hash_edit`).
* **Real-time Repair:** Captures non-zero linter outputs and appends `_linter_feedback` directly into the tool output, allowing the LLM to fix syntax errors or broken imports in the exact same turn.

### ⏱️ Performance Statistics & Configurable Footer Metrics
* **Token Counts (`/config tokens`):** Displays input and output prompt/completion token counts per turn.
* **Cost Metering (`/config cost`):** Tracks real-time USD costs per turn and cumulative session totals.
* **Token Performance Statistics (`/config statistics`):** Measures Time to First Token (**TTFT** in `ms` or `s`) and generation throughput (**tok/s**).

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints, model configurations, router settings, network proxy settings, model tags/descriptions, metrics toggles, auto-compaction rules, and global system prompts.

```json
{
  "active_model": "lmstudio:gemma-4-e4b",
  "system_prompt": "You are Mesh, a helpful, precise, and efficient AI assistant running inside an interactive terminal CLI.",
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
  "providers": {
    "anthropic": {
      "name": "Anthropic Official",
      "base_url": "https://api.anthropic.com/v1",
      "api_key_env": "ANTHROPIC_API_KEY",
      "default_headers": null
    },
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
    "anthropic:claude-3-7-sonnet-20250219": {
      "name": "Claude 3.7 Sonnet",
      "provider": "anthropic",
      "model_id": "claude-3-7-sonnet-20250219",
      "context_window": 200000,
      "tags": ["reasoning", "coding", "agent", "thinking", "large-context"],
      "description": "Anthropic's flagship hybrid reasoning model with native extended thinking and prompt caching."
    },
    "lmstudio:gemma-4-e4b": {
      "name": "Gemma 4 E4B",
      "provider": "lmstudio",
      "model_id": "google/gemma-4-e4b",
      "context_window": 8192,
      "tags": ["local", "fast", "general"],
      "description": "Lightweight local Gemma model for quick answers"
    }
  }
}
```

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
