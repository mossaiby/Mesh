# ⚡ Mesh

**v1.0.0**

A modular, text-based AI CLI built in Python. Designed for local and cloud-hosted LLMs, featuring **real-time Markdown streaming**, **Model Context Protocol (MCP)** integration, **Sub-Agent Proxy Distillation**, **Speculative Swarm Exploration**, **Autonomous Tool Synthesis**, **Adversarial Multi-Model Consensus**, **Multi-Role Autonomous Task Squads**, **Cross-Session Reflexion Journaling**, **AST Codebase Symbol Indexing**, **Session Checkpointing & Branching**, **Unified Diff Previews & File Rollback**, **Declarative Skills**, **Directory Permissions**, and **Semantic Context Compaction**.

---

## 🌟 Key Features

- **Multi-Provider OpenAI Compatibility**: Seamlessly connect to OpenAI, Groq, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, or any OpenAI-compatible REST endpoint via `models.json`.
- **Interactive Model Switcher (`/switch`)**: Switch active models on the fly using a cross-platform arrow-key selection menu or command arguments.
- **Model Discovery & Batch Configuration (`/models discover` / `/models add`)**: Query provider REST endpoints (`/v1/models`) to discover remote models offered by backends. Interactively pick discovered models with arrow keys or batch-add models using wildcard patterns (e.g., `/models add openrouter *free*` or `/models add groq llama`).
- **Script File Execution & Headless Automation (`/script` & CLI `--file`)**: Execute commands and prompts line-by-line from a script file interactively via `/script <file.txt>` or on startup via `python main.py script.txt --non-interactive` for headless CI/CD and Docker pipelines.
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
- **Advisor (`consult_advisor`)**: A tool-free, single-shot "second opinion" the model can consult before committing to a risky or ambiguous plan - optionally from a different configured model than the one driving the conversation, for a genuinely independent perspective rather than the same model re-asked. Switch the advisor model live via `/advisor model [<key>]`.
- **Tool-Call Safety Guard (`/guard`)**: Shell commands, file writes/edits, and MCP tool calls are automatically risk-assessed by a dedicated (ideally cheap/local) model before they run - low risk proceeds, medium risk asks for permission (or auto-approves in autonomous mode), high risk is blocked outright regardless of mode.
- **Operating Modes (`/mode`)**: Switch between Build (default, full access), Plan/Review (read-only - investigate and propose without touching anything), and YOLO (full access, no confirmation prompts for ambiguous-risk actions). Mode restrictions are enforced twice - hidden from the model's own tool list *and* hard-blocked at execution - so a read-only mode is read-only even against a model that ignores its own tool list.
- **Self-Healing Tool-Error Recovery (`/selfheal`)**: Failed tool calls get one automatic recovery attempt before the model ever sees the error - transient failures (timeouts, rate limits) are mechanically retried with no model call, and failures likely caused by malformed arguments are diagnosed and retried once by a focused repair sub-agent.
- **Pinned Session Goal (`/goal`)**: A single objective (with optional success criteria) that's folded directly into the live system prompt rather than a chat message, so it stays visible to the model across `/compact`, `/switch`, and `/clear` - the one thing in a session that's designed to never get summarized away.
- **Model Context Protocol (MCP) (`/mcps`)**: Native stdio JSON-RPC MCP client supporting `mcps.json`. Dynamically discovers and executes tools from external MCP servers (SQLite, Filesystem, GitHub, etc.) with global and per-server toggles.
- **Modular Skills Subsystem (`/skills`)**: Package specialized system prompts and tools into reusable skills. Supports dynamic loading from `skills.json` or custom Python classes.
- **Rich Native Tool Suite**:
  - **File Operations**: `read_file`, `write_file`, `edit_file`, `glob_files`.
  - **System Shell**: `run_shell_command` with execution timeouts.
  - **Zero-Key Web Search & Fetch**: `web_search` (DuckDuckGo search without API keys) and `web_fetch` (clean HTML-to-text extraction).
  - **Human-in-the-Loop**: `ask_user` with interactive arrow-key option selection and free-form input.
  - **Session State**: `memory` (persistent JSON key-value store, with `search` for meaning-based recall via a dedicated sub-agent call rather than exact keys or embeddings), `note_manager` (persistent `notes.md` manager), and `todo_manager` (dependency-aware, multi-step task tracking - tasks can declare `depends_on` other tasks, and `next` surfaces what's actually unblocked).
- **Directory Authorization & Security (`/dirs`)**: `PermissionManager` enforces directory boundaries. If a tool requests path access outside allowed directories, an interactive prompt asks the human user for access permission.
- **Semantic Context Compaction (`/compact`)**: Summarizes older conversation context using the LLM without truncating system prompts or breaking active tool-call history pairs.
- **Auto-Compaction (`/autocompact`)**: Automatically triggers `/compact` once the conversation's estimated token usage crosses a configurable percentage of the active model's context window - no manual intervention needed, even in long agentic sessions.
- **Dream Extraction (`/dream`)**: Runs a dedicated analysis pass over the current conversation to surface durable notes, key-value memory facts, and reusable Skills worth keeping - with an interactive review before anything is persisted.
- **Real-Time Token Streaming & CoT**: Live Markdown rendering with code syntax highlighting and toggleable Chain of Thought (CoT) reasoning displays (`/debug on|off`).
- **Unified Theming**: A single shared, themed console (`theme.py`) applies one consistent, semantic color palette across every command, tool log, and prompt in the CLI.

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

### 5. Execute Script Files (Headless Automation)

Run Mesh with a script file on launch:

```bash
# Execute script and transition to interactive mode
python main.py script.txt

# Execute script in headless non-interactive mode and exit automatically
python main.py --file script.txt --non-interactive
```

---

## 🛠️ Slash Commands Reference

| Command | Description |
| :--- | :--- |
| `/help` | List all available slash commands. |
| `/status` | Display a detailed status overview of active models, tools, MCPs, skills, memory, symbols, and checkpoints. |
| `/version` | Show the current Mesh version. |
| `/models [discover\|add]` | List configured models (`/models`), query endpoints (`/models discover`), or interactively/batch add models (`/models add [<provider>] [<pattern>]`). |
| `/switch [key]` | Interactively switch models using arrow keys, or directly by model key. |
| `/script <file.txt>` | Execute commands and prompts line-by-line from a script file. |
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
| `/selfheal [on\|off]` | Toggle automatic tool-error recovery (mechanical retry + LLM-assisted argument repair) on or off. |
| `/dirs [add\|remove\|clear] <path>` | Manage authorized directory paths for file and shell operations. |
| `/mcps [on\|off]` | View connected MCP servers or toggle MCP tools globally/per-server. |
| `/note [append\|clear] [text]` | View, append to, or clear persistent project notes (`notes.md`). |
| `/memory [save\|get\|search\|delete\|clear]` | View or manage persistent key-value items (`memory.json`); `search` recalls by meaning via a sub-agent call. |
| `/compact` | Semantically compact older conversation history using the LLM. |
| `/autocompact [on\|off\|threshold <0-100>]` | View or configure automatic compaction, which triggers `/compact` once estimated token usage crosses the threshold. |
| `/dream` | Analyze the conversation and interactively extract candidate notes, memory facts, and reusable skills. |
| `/delegate <task>` \| `/delegate depth [<n>]` | Manually hand a task to an autonomous sub-agent and print its final report; view or set the recursive delegation depth limit. |
| `/goal <text> [\| criterion \| ...]` | View, set (with optional success criteria), or manage the pinned session goal; `/goal done <#>` marks a criterion complete, `/goal clear` removes it. |
| `/advisor <question>` | Manually consult the advisor for a second opinion or set its model via `/advisor model [<key>]`. |
| `/guard [on\|off]` | View or configure the tool-call safety guard: `/guard mode [supervised\|autonomous]`, `/guard model [<key>]`, `/guard trust <tool>`. |
| `/mode [plan\|build\|review\|yolo]` | View or switch operating mode - see below for what each restricts. |
| `/retry` | Re-run the last completion turn (strips the last assistant/tool response). |
| `/debug [on\|off]` | Toggle debug mode to show Chain of Thought (CoT) and sub-agent logs. |
| `/clear` | Clear conversation history while keeping system prompt and skills intact. |
| `/exit` | Safely close MCP process connections and exit. |

---

## 📜 Script File Execution & Headless Automation (`/script` & CLI `--file`)

Execute preset command macros or automated prompts line-by-line:

```text
# Example script: bootstrap_session.txt
/mode build
/goal Implement User Authentication | Add JWT middleware | Write unit tests
/memory search auth_token_secret
Explain the user authentication setup in this repository.
```

- **In interactive mode:** `/script bootstrap_session.txt`
- **On launch (interactive):** `python main.py bootstrap_session.txt`
- **Headless CI/CD / Docker:** `python main.py -f bootstrap_session.txt -n`

---

## ⚙️ Configuration Files

### `models.json`
Defines provider REST endpoints and model configurations, plus a single global system prompt shared by every model. Mesh always talks to whichever model is active with the same base instructions - switching models (`/switch`) changes only the endpoint/model ID, never the assistant's persona or instructions. Use `/system` to view or temporarily override the prompt for the current session.

`auto_compact` and `auto_compact_threshold` control Auto-Compaction (see below) globally. `max_delegation_depth` controls how many levels deep recursive Task Delegation (see below) may go. `advisor_model` and `guard_*` configure the Advisor and Safety Guard (see below) - both can point at a different model key than `active_model`, so a second opinion or a risk check doesn't have to come from the same model doing the work. Each model entry's `context_window` (in tokens) tells Mesh how much room that specific model has, so the same threshold behaves correctly across models with very different context sizes.

```json
{
  "active_model": "llama3-groq",
  "system_prompt": "You are a helpful, intelligent AI assistant running inside Mesh, an interactive terminal CLI.",
  "auto_compact": true,
  "auto_compact_threshold": 0.75,
  "max_delegation_depth": 2,
  "advisor_model": null,
  "guard_enabled": true,
  "guard_model": "lmstudio:local-1b-model",
  "guard_autonomy": "supervised",
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
      "context_window": 128000
    },
    "gemma-4-e4b-lmstudio": {
      "name": "Gemma 4 E4B (Local)",
      "provider": "lmstudio",
      "model_id": "google/gemma-4-e4b",
      "context_window": 8192
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

## 🌲 Speculative Swarm Exploration (`explore_branches` / `/explore`)

`explore.py` and `tools/explore_tool.py` introduce Monte Carlo Tree Search (MCTS) / Tree-of-Thoughts style parallel exploration to Mesh.

1. **Parallel Branching**: Instead of sequentially attempting a complex task step-by-step, Mesh spawns $N$ parallel sub-agents (branches) with distinct strategy prompts (e.g., Direct Implementation, Defensive/Edge-Case Heavy, Alternative Structural Pattern).
2. **Concurrent Execution**: All branches run asynchronously via `asyncio.gather()` using Mesh's delegation engine.
3. **LLM Judge Pass**: A dedicated Judge pass evaluates all branch reports and tool logs, selects the winning strategy (or synthesizes the best ideas across branches), and presents a unified solution.

Run via `/explore <task description>` or through the model calling the `explore_branches` tool.

---

## ⚡ Autonomous Tool Synthesis (`synthesize_tool` / `custom_tools/`)

`tool_synthesis.py` and `tools/synthesis_tool.py` allow Mesh (or the user) to generate new deterministic Python tools on the fly when repetitive tasks are detected.

1. **AST Validation**: Code generated by the model is validated via Python's `ast` module to guarantee clean syntax and valid `BaseTool` subclassing.
2. **Persistence**: Validated tools are saved as Python modules inside `custom_tools/`.
3. **Live Registration**: Newly synthesized tools are imported and registered dynamically into `ToolRegistry` at runtime without restarting the CLI session.
4. **Auto-Load on Startup**: All saved tools in `custom_tools/` are automatically re-loaded every time Mesh starts.

---

## ⚖️ Adversarial Multi-Model Consensus (`consult_consensus` / `/consensus`)

`consensus.py` and `tools/consensus_tool.py` implement an adversarial cross-examination loop for critical code changes or architectural proposals.

1. **Proposal**: Model A generates a candidate plan, command, or patch.
2. **Red-Team Audit**: Model B (configured via `advisor_model` or specified directly) acts as an auditor, red-teaming the proposal for security vulnerabilities, edge cases, and side effects.
3. **Referee Synthesis**: A referee pass reviews the original proposal alongside the auditor's critique to synthesize a final, verified consensus recommendation.

Run via `/consensus <question> | <proposed solution>` or via the `consult_consensus` tool.

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

## 🔄 Session Checkpointing & Branching (`/checkpoint`, `/fork`, `/checkout`)

`checkpoint.py` takes snapshots of Mesh's active state (messages, goals, todos, notes, memory, mode). Use `/checkpoint save <tag>` to save, `/fork <branch_name>` to fork context into an isolated working branch, and `/checkout <tag_or_branch>` to restore state freely.

---

## ↩️ Unified Diff Previews & File Rollback (`/diff`, `/undo`)

`file_history.py` intercepts `write_file` and `edit_file` executions before modifying disk, computes colorized unified diffs, and maintains an in-memory session undo stack. Use `/diff` to inspect recent edits and `/undo` to revert file changes instantly.

---

## 🤖 Sub-Agent Proxy Architecture

When `/proxy on` is active:
1. **Dynamic Intent Injection**: Heavy tools (`read_file`, `shell`, `web_search`, `mcps`) dynamically require an `_intent` string parameter in their function schema.
2. **Execution & Interception**: The main LLM specifies why it is calling the tool (e.g. `_intent="Find active_model key"`).
3. **Sub-Agent Distillation**: `SubAgentProxy` intercepts the raw tool output, passes it through a focused sub-agent pass, and extracts only the relevant information matching the requested intent.
4. **Context Optimization**: The main LLM receives a clean, structured JSON summary instead of thousands of lines of raw file content or build logs.

*Note: Short outputs (under 4 lines / 300 characters) and lightweight tools (`calculator`, `memory`) automatically bypass distillation for zero-latency execution.*

---

## 🚦 Operating Modes (`/mode`)

`modes.py` defines four modes that constrain what the model can do without touching what it's allowed to *know* - the system prompt, memory, and notes stay fully available in every mode; only tool access and confirmation behavior change.

| Mode | Tool access | Confirmation behavior |
| :--- | :--- | :--- |
| **Build** (default) | Full | Normal - Safety Guard/permissions behave as configured |
| **Plan** | Read-only (no `write_file`, `edit_file`, `run_shell_command`, `delegate_task`, or MCP tools) | Normal |
| **Review** | Read-only (same restriction as Plan) | Normal |
| **YOLO** | Full | Ambiguous-risk ("ask") actions auto-approve; genuinely high-risk actions are still always blocked |

Plan and Review both reuse the exact same signal the Safety Guard already relies on - every tool with `requires_guard = True` (see below) plus `delegate_task` - rather than a second hardcoded blocklist that could drift out of sync as new tools or MCP servers are added. The difference between them is purely the model's *framing*: Plan is told to investigate and produce a step-by-step plan; Review is told to critique what's already there, not propose new work.

**Enforced twice, not once**: switching modes both hides blocked tools from the schema offered to the model *and* hard-blocks them at `ToolRegistry.execute()` if called anyway. The first layer is what a well-behaved model actually sees; the second is what makes Plan/Review mode a real guarantee rather than a polite suggestion, for models that sometimes call tools outside their own advertised schema.

**YOLO mode** temporarily forces `guard_autonomy` to `"autonomous"` and `PermissionManager.auto_approve` to `True`, restoring whatever you'd actually set before entering it (not a hardcoded default) when you switch back out. High-risk actions are never auto-approved in any mode - YOLO removes friction for ambiguous cases, it never bypasses an outright Safety Guard denial.

The active mode is folded into the live system prompt the same way the Pinned Session Goal is, so it survives `/compact`, `/switch`, and `/clear` just like the goal does.

---

## 🛡️ Tool-Call Safety Guard (`/guard`)

`SafetyGuard` (`guard.py`) risk-assesses tool calls flagged `requires_guard = True` - `run_shell_command`, `write_file`, `edit_file`, and every MCP tool - before they're allowed to execute. It's wired into `ToolRegistry.execute()`, the same single choke point used by self-healing, so it automatically covers the main agent, `delegate_task` sub-agents at every recursion depth, and calls made through `/proxy` alike.

This is deliberately a *different* check from `PermissionManager`'s directory allow-list: permissions ask "is this **path** somewhere I'm allowed to touch" (a boundary check); the guard asks "is this call's actual **content** dangerous, regardless of where it happens" (a semantic risk check). A `write_file` call to an already-allowed path can still carry destructive content; a shell command can be dangerous no matter what directory it runs in. Both checks can fire independently on the same call.

1. **Risk assessment**: A dedicated model - configured separately via `guard_model`, so it can be a small/cheap/local model rather than whatever (possibly large, possibly per-token-billed) model is driving the conversation - looks at the tool name and its exact arguments and classifies risk as `low` / `medium` / `high`.
2. **Verdict**:
   - **low -> allow**: proceeds immediately, no friction for routine work.
   - **medium -> ask**: in `supervised` mode (default), the same interactive picker `PermissionManager` uses pops up - *Allow Once* / *Always Allow this tool for the session* / *Deny*. In `autonomous` mode, it proceeds automatically instead.
   - **high -> deny**: blocked outright and returned to the model as an error, in *either* mode - autonomy only removes friction for ambiguous medium-risk cases, it never bypasses an outright high-risk denial.
3. **Session trust**: choosing "Always Allow" for a tool - or running `/guard trust <tool_name>` directly - skips future guard model calls for that specific tool for the rest of the session, not a blanket bypass of every guarded tool.
4. **Concurrency-safe prompting**: interactive "ask" prompts are serialized behind a lock, so a fan-out of parallel delegated sub-agents (see Task Delegation below) can't produce overlapping/garbled terminal prompts - they queue instead of colliding.

When a guard check runs, its outcome is folded into the result as a `_guard` note for transparency, the same way self-healing adds `_self_healed`.

Configure via `models.json` (`guard_enabled`, `guard_model`, `guard_autonomy`) or live with `/guard on|off`, `/guard mode supervised|autonomous`, `/guard model <key>`, `/guard trust <tool_name>`.

---

## 🧭 Advisor (`consult_advisor`)

`advisor.py` provides a single-shot, tool-free "second opinion" the main model can ask for via the `consult_advisor` tool, or you can trigger directly with `/advisor <question>`. It's a genuinely different kind of call from everything else in Mesh that spins up a focused sub-agent:

- **`delegate_task`** does the work and reports back what happened.
- **`self_heal`**'s repair pass fixes one specific tool-call failure.
- **`consult_advisor`** takes no action and has no tools at all - it exists purely to give a candid opinion, flag risks/tradeoffs, and suggest alternatives, which the main model is free to weigh and disagree with.

Set `advisor_model` in `models.json` to always consult a specific model (e.g. a stronger reasoning model) regardless of which model is actively driving the conversation, so a "second opinion" is an opinion from somewhere genuinely different - not the same model re-asked. Leave it `null` to just use whichever model is currently active. Switch the advisor model on the fly using `/advisor model [<key>]` or reset it with `/advisor model clear`.

---

## 🩹 Self-Healing Tool-Error Recovery (`/selfheal`)

Every tool call - from the main agent, `delegate_task` sub-agents, and `/proxy` distillation alike, since they all go through the same `ToolRegistry.execute()` - gets a best-effort automatic recovery attempt before a failure is ever handed back to the model. This is implemented in `self_heal.py` and is independent of Sub-Agent Proxy above; it never masks a real failure, it only adds a couple of cheap recovery attempts in front of one.

Two layers, tried in order:

1. **Mechanical retry (no model call)** - if the error looks transient (`timeout`, `connection reset`, `rate limit`, `503`, etc.), the exact same call is retried a couple of times with a short delay. This also covers an unknown-tool-name typo (e.g. the model calls `todo_manger`): it's corrected to the closest registered tool name via string similarity, with no LLM involved at all.
2. **LLM-assisted argument repair (one attempt)** - if the failure survives mechanical retry, a small focused sub-agent call (same pattern as `/dream`/`/compact`/`memory search`) is shown the tool's schema, the arguments that failed, and the error message, and asked to propose corrected arguments - but only if it's confident the fix is purely structural (wrong type, invalid enum value, malformed JSON, a typo'd parameter). It's explicitly told not to guess at things it can't know, like the actual correct file path for a "file not found" error - those are passed through untouched.

A few things are deliberately never auto-healed: permission-denied results (a security boundary, not a bug), and arguments to `run_shell_command`/`ask_user` are never auto-corrected and blindly re-run. When healing does change the outcome, the tool result includes a `_self_healed` note so both you and the model can see it happened.

---

## 🧠 Semantic Memory Search (`memory` → `search`)

Memory recall doesn't rely on exact keys or an embedding/vector index. `memory search <query>` (implemented in `memory_search.py`) uses the same "small, focused sub-agent call" pattern as `/dream`, `/compact`, and `delegate_task`: the full memory store plus a natural-language query are sent to the active model with instructions to find relevant entries by meaning, not keyword overlap, and return them as structured JSON with a short synthesized answer.

This was chosen deliberately over cosine-similarity search:
- **No embedding infrastructure required** - works uniformly across every backend Mesh talks to, including local servers that don't expose an embeddings endpoint at all.
- **Short key-value pairs are a weak fit for embeddings** - a one-line fact like `ci_provider: GitHub Actions` doesn't embed distinctively; an LLM's judgment handles paraphrase, synonyms, and "the value answers this even though the key shares no words with it" far better than vector distance on short strings.
- **No index to build or keep in sync** - the memory store is read fresh on every search, so there's nothing that can go stale.

`get` still exists for the common case where you already know the exact key - `search` is for when you don't.

---

## 🕸️ Dependency-Aware TODOs (`todo_manager`)

`todo_manager` (`tools/todo_tool.py`) tracks a TODO list as a small DAG rather than a flat sequence, so the model (and the user, via `/dream`'s and `display`'s rendering) can see which work is actually independent versus which is waiting on something else:

- **`add`** accepts an optional `depends_on: [id, ...]` list. A task can only depend on IDs that already exist, which makes the dependency graph acyclic by construction - there's no separate cycle-detection step needed.
- **`complete`** is gated: completing a task whose dependencies aren't finished yet returns an error naming exactly which task(s) are blocking it, instead of silently marking it done out of order.
- **`next`** returns only the tasks that are ready right now (incomplete, with every dependency already completed) - useful for identifying independent branches that could be worked on in either order, or delegated out via `delegate_task`, instead of assuming the list must be done top-to-bottom.
- **`display`** renders each task's live status: ✔ done, ▶ ready, or ⏳ blocked (with the specific blocking task IDs shown), including transitive blocking (a task waiting on a task that's itself still blocked).

---

## 🎯 Pinned Session Goal (`goal_manager` / `/goal`)

`todo_manager` tracks the *how* - the individual steps. `goal_manager` (`tools/goal_tool.py`) tracks the *why* - a single overall objective for the session, with optional `success_criteria` defining what "done" actually looks like.

What makes this different from just telling the model the goal in a chat message: once set, the goal is folded directly into the live system prompt (via the same `update_system_message()` path used for skill instructions), not left sitting in conversation history. That means it's designed to survive the things that would otherwise bury or discard it:

- **`/compact`** summarizes old chat messages, but never touches the system prompt - the goal stays exact, not paraphrased into a summary.
- **`/switch`** changes the active model, but `update_system_message()` is rebuilt fresh each time regardless of which model is active - the goal carries over.
- **`/clear`** wipes the conversation history entirely by design, but explicitly preserves the system prompt - the goal survives a full context reset.

Actions: `set` (replaces any existing goal), `get` (raw JSON for the model), `display` (renders to the user), `complete_criterion`, and `clear`. The model can set and update it itself via the `goal_manager` tool; `/goal <text> | <criterion 1> | <criterion 2>` sets it manually, `/goal done <#>` marks a criterion met, and `/goal` alone shows the current state.

---

## 🧑‍🚀 Task Delegation (`delegate_task`)

Task Delegation is a separate capability from Sub-Agent Proxy above, implemented independently in `delegation.py` and `tools/delegate_tool.py`. Where `/proxy` distills the *output* of a single tool call the main model already decided to make, `delegate_task` lets the main model hand off an entire multi-step task and get out of the loop until it's done:

1. **Hand-off**: The main model calls the `delegate_task` tool with a self-contained task description (e.g. *"investigate why the build is failing and report what's wrong"*).
2. **Independent Sub-Agent Loop**: A fresh sub-agent conversation is created with its own system prompt and its own bounded tool-calling loop (default up to 6 turns, capped at 10, tapering down at deeper recursion levels - see below) - it plans, calls tools, reads results, and iterates entirely on its own.
3. **Tool Access**: The sub-agent shares the same live `ToolRegistry` as the main agent (so it can read/write files, run shell commands, search the web, use notes/memory, etc.), minus `ask_user` (there's no live user for it to interact with mid-task).
4. **Final Report Only**: Once the sub-agent stops calling tools, its final message becomes a single structured result - `{status, report, tool_calls, turns_used, depth}` - handed back to whoever delegated to it. The caller never sees the sub-agent's intermediate turns, only the outcome.

Because the sub-agent's tool schemas are always built with intent-injection disabled, its tool calls never carry an `_intent` argument - so `delegate_task` never routes through `SubAgentProxy`/`/proxy`, regardless of whether `/proxy` is on or off. The two features compose but don't interfere with each other.

You can also trigger delegation directly for testing via `/delegate <task description>`, without needing the main model to decide to call the tool.

### Recursive delegation

A sub-agent can itself call `delegate_task` - genuinely splitting a task into independent pieces and handing those to further sub-agents, rather than doing everything in one conversation:

- **Depth limit (user-selectable)**: controlled by `max_delegation_depth` in `models.json` (default **2** - a sub-agent can delegate once more, but that second-level sub-agent cannot delegate again). View or change it live with `/delegate depth [<n>]`. At the deepest allowed level, `delegate_task` is simply absent from that sub-agent's own tools, so recursion always terminates - there's no separate cycle-detection needed, the same way `todo_manager`'s dependency graph is acyclic by construction.
- **Fan-out**: if a sub-agent calls `delegate_task` multiple times in the same turn, those child sub-agents run **concurrently** (bounded to 4 at once) rather than one at a time - real parallel work-splitting, not just sequential hand-offs. Every other tool still executes sequentially in call order, since most of them touch shared, unlocked, file-backed state (`memory.json`, `notes.md`, the todo list) where concurrent execution could race; `delegate_task` is safe to parallelize because each sub-agent operates in its own isolated message history.
- **Turn-budget tapering**: the per-call turn cap shrinks with depth (`max(2, 10 - 2*(depth-1))` - 10 at depth 1, 8 at depth 2, 6 at depth 3, ...), so a deep recursive chain can't multiply total work unboundedly even within the depth cap.
- Depth is tracked via a `contextvars.ContextVar` rather than an explicit parameter, since the same `delegate_task` tool instance is shared by every level of delegation - each nested (and each parallel) sub-agent needs to know "how deep am I being called from right now" without the levels interfering with each other.

---

## 💤 Dream Extraction (`/dream`)

`/dream` runs a dedicated, out-of-band analysis pass (implemented in `dream.py`) over the current conversation - separate from the main chat loop - to surface durable knowledge that's easy to lose once the session ends:

1. **Transcript Analysis**: The full conversation (minus the system prompt) is sent to the active model with a focused extraction prompt asking it to return structured JSON only.
2. **Three Categories**: The model identifies candidate **notes** (durable facts/decisions worth logging), **memory** (small key-value facts worth recalling automatically next session), and **skills** (a workflow that was clearly repeated, or that you explicitly asked Mesh to remember).
3. **Interactive Review**: Each category is listed with numbered items. You choose which ones to keep per category (`all`, `none`, or specific numbers like `1,3`) - nothing is written until you confirm.
4. **Persistence**: Accepted notes are appended to `notes.md`, accepted memory facts are merged into `memory.json`, and accepted skills are registered live (so they take effect immediately) and written to `skills.json` as `DeclarativeSkill` entries.

`/dream` is conservative by design - it won't invent a skill from a single one-off request, only from a pattern that actually recurred or that you asked to be remembered.

---

## 🗜️ Auto-Compaction (`/autocompact`)

Long-running agentic sessions can quietly fill up a model's context window with tool output and history. Auto-compaction watches for that and steps in automatically:

1. **Token Estimation**: Before every model call, Mesh estimates the current conversation's token usage from a provider-agnostic character-based heuristic (`compaction.py::estimate_tokens`) - deliberately simple so it works reasonably across very different model families rather than being tied to one tokenizer.
2. **Threshold Check**: That estimate is compared against `auto_compact_threshold` (default `0.75`, i.e. 75%) of the active model's `context_window` (set per model in `models.json`).
3. **Automatic Compaction**: If usage crosses the threshold, Mesh runs the same summarization pass used by `/compact` - preserving the system prompt and the most recent messages while summarizing everything older - before sending the next request, and prints a short notice so you know it happened.
4. **Per-Model Awareness**: Because `context_window` is set per model, the same global threshold correctly triggers earlier for a small local model (e.g. a 4K-context 1B model) and later for a large hosted one (e.g. a 128K-context model), without any manual tuning when you `/switch`.

Use `/autocompact` (no args) to see current status, `/autocompact on`/`off` to toggle it, and `/autocompact threshold <0-100>` to adjust the trigger percentage. You can always still run `/compact` manually regardless of this setting.

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
├── engine.py                  # Central MeshEngine orchestration & inference turn loop
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
├── terminal_ui.py             # Prompt_toolkit session with Tab-completion
├── project_rules.py           # Project instructions & rules loader (PROJECT.md)
├── main.py                    # Clean CLI entry point and REPL loop
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
│   ├── registry.py            # Slash command registry
│   ├── agent_commands.py      # /delegate, /explore, /consensus, /squad, /advisor, /guard, /mode
│   ├── model_commands.py      # /models, /switch
│   ├── session_commands.py    # /goal, /note, /memory, /dream, /script, /project, /reflexion, /checkpoint, /fork, /checkout, /diff, /undo
│   └── system_commands.py     # /help, /status, /version, /context, /system, /tools, /skills, /dirs, /mcps, /proxy, /selfheal, /compact, /autocompact, /clear, /retry, /debug, /exit
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

## 🩹 Changelog / Bug Fixes (v1.0.0)

- **Refactored Architecture (`main.py` -> `engine.py` & `commands/`)**: Split `main.py` into `MeshEngine` (`engine.py`) and 4 modular command submodules (`commands/model_commands.py`, `commands/agent_commands.py`, `commands/session_commands.py`, `commands/system_commands.py`), reducing `main.py` to a clean ~110-line CLI entry point.
- **Added `prompt_toolkit` Tab-Completion (`terminal_ui.py`)**: Asynchronous Tab-completion for all slash commands, model keys, operating modes, and file paths.
- **Added `PROJECT.md` Project Rules Support (`project_rules.py`)**: Automatically scans workspace roots for project rule files (`PROJECT.md`, `MESH.md`, `AGENTS.md`) and injects instructions directly into the system prompt.
- **Added Script File Execution & Headless Automation (`/script`, CLI `-f`/`-n`)**: Execute commands and prompts line-by-line from a file interactively or headlessly (`python main.py script.txt --non-interactive`).
- **Added Pattern-Based Batch Model Addition (`/models add [<provider>] [<pattern>]`)**: Allows interactively picking discovered models or batch-adding models matching wildcard patterns (e.g. `/models add openrouter *free*` or `/models add groq llama`) directly into `models.json`.
- **Added Model Discovery (`/models discover`)**: Queries provider REST endpoints (`/v1/models`) to discover models offered by local or cloud backends dynamically.
- **Added Live Advisor Model Switching (`/advisor model <key>`)**: Added live command switching to update `advisor_model` in `models.json` on the fly or reset it to fall back to the active model (`/advisor model clear`).
- **Added Multi-Role Autonomous Task Squad (`/squad`)**: Coordinates a 4-stage pipeline of specialized persona sub-agents (Architect -> Coder -> Test Engineer -> Security Auditor) to plan, write code, run unit tests, and audit security autonomously.
- **Added Cross-Session Reflexion Journal (`/reflexion`)**: Automatically captures tool execution failures and user corrections across sessions. Distills them into durable "Lessons Learned" (`reflexion.json`) that are injected into the system prompt so Mesh never repeats mistakes across sessions.
- **Added AST Codebase Symbol Indexing (`search_symbols`)**: Zero-vector AST parsing indexes classes, functions, methods, and docstrings across workspace Python files, allowing the model to pinpoint function signatures instantly without globbing or reading whole files.
- **Added Session Checkpointing & Branching (`/checkpoint`, `/fork`, `/checkout`)**: Take full state snapshots of conversation history, goal state, todo graph, notes, and memory. Fork into isolated branches to test experimental plans, and checkout previous checkpoints freely.
- **Added Unified Diff Previews & File Rollback (`/diff`, `/undo`)**: Displays colorized git-style unified diffs (`-`/`+`) for file mutations. Maintains a session undo stack allowing instant rollback of recent file edits.
- **Added Speculative Swarm Exploration (`/explore`, `explore_branches`)**: Spawns $N$ parallel sub-agents with distinct strategies, evaluates intermediate reports with a Judge pass, and synthesizes a unified solution.
- **Added Autonomous Tool Synthesis (`synthesize_tool`, `custom_tools/`)**: Generates, AST-validates, saves, and dynamically registers new Python tools at runtime without restarting Mesh.
- **Added Adversarial Multi-Model Consensus (`/consensus`, `consult_consensus`)**: Runs a 2-stage red-team audit and referee synthesis pass before executing critical operations.
- **Missing `httpx` dependency**: `tools/web_tools.py` imports `httpx` for `web_search`/`web_fetch`, but it was never listed in `requirements.txt`, so a clean install would crash the first time either tool ran. Added to `requirements.txt`.
- **Directory-permission misclassification**: `PermissionManager` used to guess "is this a directory?" from whether the path had a file suffix, which misclassified extensionless existing files (`Makefile`, `LICENSE`, `Dockerfile`, ...) as directories — approving "Always Allow" would add the *file itself* to the allow-list instead of its parent directory. Now uses `Path.is_dir()`.
- **Web search title/snippet misalignment**: `web_search` matched result titles and snippets purely by their position in two independently-filtered lists, which could silently pair a title with the wrong snippet whenever unrelated links were filtered out. The link regex is now scoped to DuckDuckGo Lite's actual result-link anchors, and titles/snippets are paired by their original row index rather than by post-filter position.
- **Inconsistent tool de-registration**: `SkillRegistry.set_skill_state` reached directly into `ToolRegistry`'s private `_tools` dict to remove a disabled skill's tools. Switched to the registry's public `unregister()` method.
- **Consolidated system prompt**: Each model in `models.json` used to carry its own near-duplicate `system_prompt`. Replaced with a single global `system_prompt` on the top-level config, so the assistant's persona and instructions stay consistent across `/switch`, and there's one place to edit instead of one per model.
- **Added Auto-Compaction**: Mesh previously only compacted context on manual `/compact`. Long sessions could silently overflow a model's context window with no warning. Added automatic, threshold-based compaction (`/autocompact`) driven by a new per-model `context_window` field and global `auto_compact`/`auto_compact_threshold` settings in `models.json`.
- **Added Task Delegation**: New `delegate_task` tool and `delegation.py` engine let the main model hand off a self-contained multi-step task to an autonomous sub-agent with its own tool loop, separate from and unaffected by Sub-Agent Proxy (`/proxy`). Also added `/delegate <task>` for manual testing.
- **Added Dependency-Aware TODOs**: `todo_manager` previously tracked a flat list with no notion of ordering constraints. Added an optional `depends_on` field on `add`, dependency-gated `complete`, a new `next` action to surface unblocked work, and richer `display` rendering (done/ready/blocked, with blocking task IDs shown).
- **Added Semantic Memory Search**: `memory` previously only supported exact-key lookup via `get`. Added a `search` action (`memory_search.py`) that recalls entries by meaning using a dedicated sub-agent call - chosen over embedding/cosine-similarity search since it needs no vector infrastructure and handles short key-value pairs more reliably.
- **Added Self-Healing Tool-Error Recovery**: Failed tool calls previously went straight back to the model with no recovery attempt. Added `self_heal.py` and wired it into `ToolRegistry.execute()` (shared by the main loop, `delegate_task` sub-agents, and `/proxy` distillation): transient errors get mechanically retried with no model call, unknown tool-name typos are auto-corrected, and structurally-fixable argument errors get one LLM-assisted repair attempt. New `/selfheal on|off` toggle.
- **Added Pinned Session Goal**: New `goal_manager` tool and `/goal` command track a single objective (with optional success criteria) that's folded directly into the live system prompt rather than left in chat history - unlike a todo item or a chat message, it survives `/compact`, `/switch`, and `/clear` by construction.
- **Made Task Delegation recursive**: `delegate_task` previously excluded itself from every sub-agent's own tools, capping delegation at exactly one level. Sub-agents can now delegate further sub-tasks themselves, up to a new user-configurable `max_delegation_depth` (`models.json`, default 2, adjustable live via `/delegate depth [<n>]`). Multiple delegations issued in the same turn now also run concurrently (bounded to 4 at once) instead of sequentially, and the per-call turn budget tapers down with depth to bound total work.
- **Added the Advisor**: New `consult_advisor` tool and `/advisor` command give the model a tool-free "second opinion" call, optionally from a different configured model (`advisor_model`) than whichever one is driving the conversation.
- **Added the Tool-Call Safety Guard**: New `guard.py`, wired into `ToolRegistry.execute()` alongside self-healing, risk-assesses `run_shell_command`, `write_file`, `edit_file`, and every MCP tool before they run, using a dedicated (`guard_model`, defaults to the smallest local model configured) model - low risk allows, medium risk asks (or auto-approves in `autonomous` mode via `guard_autonomy`), high risk is always blocked. Reuses `PermissionManager`'s interactive picker for consistent UX, with prompts serialized so concurrent delegated sub-agents can't produce overlapping terminal prompts. New `/guard` command family.
- **Fixed a real code-execution vulnerability in `calculator`**: it evaluated expressions with `eval(expr, {"__builtins__": None}, {})`, which is not actually a sandbox - the classic escape `().__class__.__bases__[0].__subclasses__()` (and variants that reach `os.system`/file access from there) uses only attribute access and calls on a literal, never a builtin or a name lookup, so stripping `__builtins__` does nothing to stop it. Replaced with an AST-based evaluator that only permits numeric literals and arithmetic operators - no `Name`, `Call`, `Attribute`, or `Subscript` nodes are accepted at all, which closes the escape completely rather than probabilistically (the fix is a provably-safe grammar restriction, not an LLM guard - the latter would only reduce risk, not eliminate a real injection bug).
- **Added Operating Modes**: New `modes.py` and `/mode` command add Plan, Build (default), Review, and YOLO modes. Plan/Review block every tool flagged `requires_guard` plus `delegate_task` (enforced both at the schema level shown to the model and hard-blocked in `ToolRegistry.execute()`, so it holds even against a model that calls a tool outside its own advertised list); YOLO temporarily forces `guard_autonomy` to `autonomous` and `PermissionManager.auto_approve` to `True`, restoring your prior settings on leaving. The active mode is folded into the live system prompt the same way the Pinned Session Goal is, so it survives `/compact`, `/switch`, and `/clear`.
- **Fixed Context Compaction API turn sequence crashes**: `compaction.py::find_safe_split_index()` now strictly enforces that context compaction boundaries split at a `user` turn (`role == "user"`). This eliminates adjacent `assistant` message sequences when appending history summaries, resolving HTTP `400 Bad Request` schema errors across strict API providers (Anthropic, OpenRouter, DeepSeek, Groq).
- **Prevented Safety Guard Infinite Self-Healing Loops**: Expanded `NON_HEALABLE_PATTERNS` in `self_heal.py` to match `"blocked by safety guard"`, `"denied by user"`, and `"execution denied"`, ensuring Safety Guard blocks never trigger token-wasting argument repair loops.
- **Added MCP Stdio Subprocess Cleanup Registry**: Added `atexit` hooks and process registration in `mcp/client.py` to guarantee stdio MCP server processes are killed on process exit or signal interrupts.
- **Fixed Terminal Raw Mode Corruption on KeyboardInterrupt**: Handled `KeyboardInterrupt` alongside `Exception` in `tools/ask_tool.py` during option selection loops so terminal settings are cleanly restored on Ctrl+C.
- **Handled Exceptions in Slash Command Dispatching**: Wrapped slash command execution in `commands/registry.py` inside a `try...except` block to prevent unhandled command exceptions from crashing the main CLI loop.

---

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).
