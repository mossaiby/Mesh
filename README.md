# ⚡ Mesh

**v1.1.0**

A modular, text-based AI CLI built in Python. Designed for local and cloud-hosted LLMs, featuring **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **Sub-Agent Proxy Distillation**, **Speculative Swarm Exploration**, **Autonomous Tool Synthesis**, **Adversarial Multi-Model Consensus**, **Multi-Role Autonomous Task Squads**, **Cross-Session Reflexion Journaling**, **AST Codebase Symbol Indexing**, **Session Checkpointing & Branching**, **Unified Diff Previews & File Rollback**, **Declarative Skills**, **Directory Permissions**, and **Semantic Context Compaction**.

---

## 🌟 Key Features

- **Multi-Provider OpenAI Compatibility**: Seamlessly connect to OpenAI, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint via `models.json`.
- **Interactive Model Switcher (`/switch`)**: Switch active models on the fly using a cross-platform arrow-key selection menu or command arguments.
- **Speculative Swarm Exploration (`explore_branches` / `/explore`)**: Runs $N$ parallel sub-agent swarm branches with distinct strategies/hypotheses to solve complex tasks simultaneously. Evaluates intermediate outputs with a Judge LLM pass and synthesizes the winning solution.
- **Autonomous Tool Synthesis (`synthesize_tool` / `custom_tools/`)**: Enables Mesh or the user to write, AST-verify, save, and dynamically register new deterministic Python tools on the fly without restarting CLI sessions.
- **Adversarial Multi-Model Consensus (`consult_consensus` / `/consensus`)**: Cross-examines critical plans or code patches. Model A generates a proposal, Model B red-teams and audits it for security/logic bugs, and a Referee pass synthesizes a verified consensus recommendation.
- **Multi-Role Autonomous Task Squad (`/squad`)**: Coordinates a 4-stage pipeline of specialized persona sub-agents (Architect -> Coder -> Test Engineer -> Security Auditor) to plan, write code, run unit tests, and audit security autonomously.
- **Cross-Session Reflexion Journal (`/reflexion`)**: Automatically captures tool execution failures and user corrections across sessions. Distills them into durable "Lessons Learned" (`reflexion.json`) that are injected into the system prompt so Mesh never repeats mistakes across sessions.
- **AST Codebase Symbol Indexing (`search_symbols`)**: Zero-vector AST parsing indexes classes, functions, methods, and docstrings across workspace Python files, allowing the model to pinpoint function signatures instantly without globbing or reading whole files.
- **Session Checkpointing & Branching (`/checkpoint`, `/fork`, `/checkout`)**: Take full state snapshots of conversation history, goal state, todo graph, notes, and memory. Fork into isolated branches to test experimental plans, and checkout previous checkpoints freely.
- **Unified Diff Previews & File Rollback (`/diff`, `/undo`)**: Displays colorized git-style unified diffs (`-`/`+`) for file mutations. Maintains a session undo stack allowing instant rollback of recent file edits.
- **Sub-Agent Proxy Architecture (`/proxy`)**: Reduces context window noise. Heavy tools (`read_file`, `shell`, `web_search`, MCP tools) require an `_intent` parameter. A dedicated sub-agent distills raw outputs into concise, structured JSON before handing them back to the main LLM.
- **Recursive Task Delegation (`delegate_task`)**: A separate capability from `/proxy` - the main model can hand off a whole self-contained task to an autonomous sub-agent, which runs its own multi-step tool loop independently and reports back one final summary. Sub-agents can delegate further sub-tasks themselves (up to a user-configurable depth, default 2), and multiple delegations in one turn run concurrently.
- **Advisor (`consult_advisor`)**: A tool-free, single-shot "second opinion" the model can consult before committing to a risky or ambiguous plan.
- **Tool-Call Safety Guard (`/guard`)**: Shell commands, file writes/edits, and MCP tool calls are automatically risk-assessed before they run (`low`/`medium`/`high` risk classification).
- **Operating Modes (`/mode`)**: Switch between Build (default, full access), Plan/Review (read-only - investigate and propose without touching anything), and YOLO (full access, no confirmation prompts for ambiguous-risk actions).
- **Self-Healing Tool-Error Recovery (`/selfheal`)**: Failed tool calls get one automatic recovery attempt before the model ever sees the error (mechanical retries + LLM argument repair).
- **Pinned Session Goal (`/goal`)**: A single objective (with optional success criteria) that's folded directly into the live system prompt so it stays visible across `/compact`, `/switch`, and `/clear`.
- **Model Context Protocol (MCP) (`/mcps`)**: Native stdio JSON-RPC MCP client supporting `mcps.json`.
- **Modular Skills Subsystem (`/skills`)**: Package specialized system prompts and tools into reusable skills.
- **Rich Native Tool Suite**:
  - **File Operations**: `read_file`, `write_file`, `edit_file`, `glob_files`.
  - **System Shell**: `run_shell_command` with execution timeouts.
  - **Zero-Key Web Search & Fetch**: `web_search` (DuckDuckGo search without API keys) and `web_fetch` (clean HTML-to-text extraction).
  - **Human-in-the-Loop**: `ask_user` with interactive arrow-key option selection and free-form input.
  - **Session State**: `memory` (persistent key-value store + meaning-based search), `note_manager` (`notes.md`), and `todo_manager` (dependency-aware task tree).
- **Directory Authorization & Security (`/dirs`)**: Enforces directory boundaries.
- **Semantic Context Compaction (`/compact` & `/autocompact`)**: Summarizes older conversation context automatically based on token usage.
- **Dream Extraction (`/dream`)**: Analysis pass over conversation history to extract durable notes, memory facts, and reusable skills.

---

## 🏗️ Architecture Overview

```text
               ┌─────────────────────────────────────────────────────────┐
               │                      User (CLI)                         │
               └─────────────────────────┬───────────────────────────────┘
                                         │
                                  ┌──────▼──────┐
                                  │  Mesh CLI   │
                                  └──────┬──────┘
                                         │
        ┌───────────────────┬────────────┼────────────┬───────────────────┐
        │                   │            │            │                   │
┌───────▼───────┐   ┌───────▼───────┐  ┌─▼───┐   ┌────▼──────┐   ┌────────▼────────┐
│ OpenAI / Local│   │ Tool Registry │  │Skill│   │ MCP Client│   │ Sub-Agent Proxy │
│  Providers    │   │  & Security   │  │Reg. │   │(mcps.json)│   │  (Distillation) │
└───────────────┘   └───────────────┘  └─────┘   └───────────┘   └─────────────────┘
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
| `/status` | Display a detailed status overview of active models, tools, MCPs, skills, symbols, and checkpoints. |
| `/version` | Show the current Mesh version. |
| `/models` | List all configured models and their provider endpoints. |
| `/switch [key]` | Interactively switch models using arrow keys, or directly by model key. |
| `/explore <task>` | Run parallel speculative branch exploration across $N$ strategies. |
| `/consensus <question> \| <proposal>` | Run an adversarial multi-model audit and synthesis pass. |
| `/squad <task>` | Execute 4-stage autonomous task squad (Architect -> Coder -> Test Engineer -> Security Auditor). |
| `/reflexion [distill\|clear]` | View or distill cross-session error lessons into system prompt instructions. |
| `/checkpoint save <tag> \| /checkpoint list` | Save or list full session checkpoints. |
| `/fork <branch_name>` | Fork current session state into a new working branch. |
| `/checkout <tag_or_branch>` | Restore session state from a checkpoint tag or branch. |
| `/diff` | Display unified diff of recent file edits made by tools. |
| `/undo` | Revert the last file modification made on disk by a tool. |
| `/context` | Display conversation history, active tool schemas, and MCP statuses. |
| `/system [text]` | Display, update, or clear (`/system clear`) the current system prompt. |
| `/skills [enable\|disable] <name>` | List registered skills or enable/disable specific skills. |
| `/tools [on\|off]` | View registered tools or toggle tool inclusion/execution globally. |
| `/proxy [on\|off]` | Toggle Sub-Agent Proxy tool output distillation on or off. |
| `/selfheal [on\|off]` | Toggle automatic tool-error recovery on or off. |
| `/dirs [add\|remove\|clear] <path>` | Manage authorized directory paths for file and shell operations. |
| `/mcps [on\|off]` | View connected MCP servers or toggle MCP tools globally/per-server. |
| `/note [append\|clear] [text]` | View, append to, or clear persistent project notes (`notes.md`). |
| `/memory [save\|get\|search\|delete\|clear]` | View or manage persistent key-value items (`memory.json`). |
| `/compact` | Semantically compact older conversation history using the LLM. |
| `/autocompact [on\|off\|threshold <0-100>]` | View or configure automatic context compaction. |
| `/dream` | Analyze conversation and interactively extract candidate notes, memory, and skills. |
| `/delegate <task>` \| `/delegate depth [<n>]` | Manually hand a task to an autonomous sub-agent. |
| `/goal <text> [\| criterion \| ...]` | View, set, or manage the pinned session goal. |
| `/advisor <question>` | Manually consult the advisor for a second opinion. |
| `/guard [on\|off]` | View or configure the tool-call safety guard. |
| `/mode [plan\|build\|review\|yolo]` | View or switch operating mode. |
| `/retry` | Re-run the last completion turn. |
| `/debug [on\|off]` | Toggle debug mode to show Chain of Thought (CoT) and sub-agent logs. |
| `/clear` | Clear conversation history while keeping system prompt and skills intact. |
| `/exit` | Safely close MCP process connections and exit. |

---

## 👥 Multi-Role Autonomous Task Squad (`/squad`)

`squad.py` coordinates 4 specialized persona sub-agents in a sequential automated pipeline:

1. **Architect**: Analyzes the task and produces a technical architecture design and implementation plan.
2. **Coder**: Executes file tool operations (`write_file`, `edit_file`) based on the Architect's plan.
3. **Test Engineer**: Writes unit tests and verifies execution using `run_shell_command`.
4. **Security Auditor**: Audits code changes and test outputs for vulnerabilities, producing the final report.

---

## 🧠 Cross-Session Reflexion Journal (`/reflexion`)

`reflexion.py` records tool failures and corrections into `reflexion.json`. Running `/reflexion distill` triggers a focused LLM pass to synthesize durable project lessons (e.g. build flags, path rules), which are automatically injected into system prompts on launch.

---

## 🌲 Speculative Swarm Exploration (`explore_branches` / `/explore`)

`explore.py` and `tools/explore_tool.py` introduce parallel MCTS-style branch search:
- Generates $N$ task strategies dynamically using the LLM.
- Runs parallel sub-agent swarms concurrently.
- Evaluates branch reports via a Judge pass to synthesize the winning solution.

---

## ⚡ Autonomous Tool Synthesis (`synthesize_tool` / `custom_tools/`)

`tool_synthesis.py` and `tools/synthesis_tool.py` allow writing, AST-validating, saving, and dynamically registering Python tools inside `custom_tools/` at runtime without restarting Mesh.

---

## ⚖️ Adversarial Multi-Model Consensus (`consult_consensus` / `/consensus`)

`consensus.py` and `tools/consensus_tool.py` run a 2-stage red-team audit:
- Model A generates a proposal.
- Model B audits for security flaws and edge cases.
- A Referee pass synthesizes a verified consensus recommendation.

---

## 🛡️ Tool-Call Safety Guard (`/guard`)

`SafetyGuard` (`guard.py`) risk-assesses tool calls before execution. Low risk proceeds, medium risk prompts for permission (or auto-approves in autonomous/YOLO mode), high risk is blocked outright.

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
├── memory_search.py           # Sub-agent-based semantic memory search
├── self_heal.py               # Self-healing tool-error recovery
├── advisor.py                 # Advisor engine
├── guard.py                   # Tool-call Safety Guard
├── modes.py                   # Operating modes (Plan/Build/Review/YOLO)
├── compaction.py              # Semantic context window compaction module
├── dream.py                   # /dream conversation analysis & knowledge extraction
├── main.py                    # Main CLI entry point and orchestration loop
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
│   ├── goal_tool.py           # goal_manager tool
│   ├── advisor_tool.py        # consult_advisor tool
│   ├── explore_tool.py        # explore_branches tool
│   ├── synthesis_tool.py      # synthesize_tool tool
│   ├── consensus_tool.py      # consult_consensus tool
│   └── symbol_tool.py         # search_symbols AST search tool
├── commands/
│   ├── __init__.py
│   └── registry.py            # Slash command registry
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
