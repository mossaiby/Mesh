import asyncio
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Any
from rich.markdown import Markdown
from tools.note_tool import _read_notes, _write_notes, _append_notes
from tools.memory_tool import _load_memory, _save_memory
import memory_search
from dream import dream_extract
from skills import DeclarativeSkill
import project_rules
import repo_map
import reflexion
import git_workflow
from file_history import file_history_tracker
from python_executor import python_executor
from theme import console


async def cmd_cd(engine: Any, args: List[str]):
    if not args:
        console.print(f"Current Working Directory: [accent]{os.getcwd()}[/accent]\nUsage: [warning]/cd <path>[/warning]\n")
        return

    target_path_str = " ".join(args).strip()
    try:
        resolved_path = Path(target_path_str).resolve()
        if not resolved_path.exists() or not resolved_path.is_dir():
            console.print(f"[error]Directory '{target_path_str}' does not exist or is not a directory.[/error]")
            return

        old_cwd = str(Path.cwd().resolve())
        os.chdir(resolved_path)
        new_cwd = str(resolved_path)

        # Update allowed_dirs: remove old CWD, add new CWD
        if old_cwd in engine.permission_manager.allowed_dirs:
            engine.permission_manager.allowed_dirs.remove(old_cwd)
        engine.permission_manager.add_dir(new_cwd)

        console.print(f"[success]✔ Changed CWD to:[/success] [accent]{new_cwd}[/accent]")

        # Reload workspace project context, AST symbols, and Repo Map
        engine.reload_project_context()

    except Exception as e:
        console.print(f"[error]Failed to change directory: {e}[/error]")


async def cmd_shell(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /shell <command> | ! <command>[/error]")
        return

    command = " ".join(args).strip()
    console.print(f"[brand]⚡ Direct Shell Execution:[/brand] {command}")

    proc = None
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = (stdout.decode('utf-8', errors='replace') + "\n" + stderr.decode('utf-8', errors='replace')).strip()

        if output:
            console.print(output)
        else:
            console.print("[dim]<no output>[/dim]")

    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Shell command cancelled by user.[/warning]")
        if proc:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    proc.terminate()
                    await asyncio.sleep(0.1)
                    if proc.returncode is None:
                        proc.kill()
            except Exception:
                pass
    except Exception as e:
        console.print(f"[error]Shell command failed: {e}[/error]")


async def cmd_python(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /python <code> | # <code>[/error]")
        return

    code = " ".join(args).strip()
    console.print(f"[brand]🐍 Direct Python Execution:[/brand] #{code}")

    try:
        success, output = python_executor.execute_snippet(code)

        if output:
            style = "success" if success else "error"
            console.print(f"[{style}]{output}[/{style}]")
        else:
            console.print("[dim]<no output>[/dim]")
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Python execution cancelled by user.[/warning]")


async def cmd_checkpoint(engine: Any, args: List[str]):
    if not args:
        info = engine.checkpoint_mgr.list_checkpoints()
        console.print(f"\n[success]Checkpoints (Active Branch: [accent]{info['active_branch']}[/accent]):[/success]")
        if not info["checkpoints"]:
            console.print("  [dim]No saved checkpoints.[/dim]\n")
        else:
            for tag, details in info["checkpoints"].items():
                console.print(f"  • [label]{tag}[/label] (Branch: {details['branch']}, Messages: {details['messages_count']}, Mode: {details['mode']})")
            console.print()
        console.print("Usage: [warning]/checkpoint save <tag>[/warning] | [warning]/checkpoint fork <branch>[/warning] | [warning]/checkpoint restore <tag_or_branch>[/warning] | [warning]/checkpoint list[/warning]\n")
        return

    sub = args[0].lower()

    if sub == "save" and len(args) >= 2:
        tag = args[1]
        engine.checkpoint_mgr.create_snapshot(tag, engine)
        console.print(f"[success]Checkpoint '[label]{tag}[/label]' saved on branch '[accent]{engine.checkpoint_mgr.active_branch}[/accent]'.[/success]")

    elif sub == "fork" and len(args) >= 2:
        branch_name = args[1].strip()
        engine.checkpoint_mgr.active_branch = branch_name
        engine.checkpoint_mgr.create_snapshot(f"branch_{branch_name}_start", engine)
        console.print(f"[success]Forked current session into new branch: [accent]{branch_name}[/accent].[/success]")

    elif sub in ("restore", "checkout") and len(args) >= 2:
        target = args[1].strip()
        success = engine.checkpoint_mgr.restore_snapshot(target, engine)
        if success:
            console.print(f"[success]Restored session state from checkpoint/branch: [accent]{target}[/accent].[/success]")
        else:
            console.print(f"[error]Checkpoint or branch '[accent]{target}[/accent]' not found. See /checkpoint list for available tags.[/error]")

    elif sub == "list":
        await cmd_checkpoint(engine, [])

    else:
        console.print("[error]Usage: /checkpoint [save|fork|restore|list] <args>[/error]")


async def cmd_diff(engine: Any, args: List[str]):
    if args and args[0].lower() == "undo":
        success, message = file_history_tracker.undo_last()
        if success:
            console.print(f"[success]{message}[/success]")
        else:
            console.print(f"[error]{message}[/error]")
        return

    diff_info = file_history_tracker.get_last_diff()
    if not diff_info:
        console.print("[dim]No file edits recorded in current session history.[/dim]")
        return

    console.print(f"\n[label]Unified Diff ({diff_info['action']} -> '{diff_info['path']}'):[/label]")
    if diff_info["diff_text"]:
        for line in diff_info["diff_text"].splitlines():
            if line.startswith("+"):
                console.print(f"[success]{line}[/success]")
            elif line.startswith("-"):
                console.print(f"[error]{line}[/error]")
            else:
                console.print(f"[dim]{line}[/dim]")
    else:
        console.print("[dim]No content changes detected.[/dim]")
    console.print("Usage: [warning]/diff[/warning] | [warning]/diff undo[/warning] (revert last file edit)\n")


async def cmd_git(engine: Any, args: List[str]):
    try:
        if not git_workflow.is_git_repository("."):
            console.print("[error]Current directory is not a Git repository.[/error]")
            return

        if not args:
            status = git_workflow.get_git_status(".")
            console.print(f"\n[success]Git Status (Branch: [accent]{status.get('branch', 'unknown')}[/accent]):[/success]")
            changes = status.get("changes", [])
            if changes:
                for c in changes:
                    console.print(f"  • {c}")
            else:
                console.print("  [dim]Working tree clean - no modified or untracked files.[/dim]")
            console.print("\nUsage: [warning]/git status[/warning] | [warning]/git diff[/warning] | [warning]/git commit [<msg>][/warning] | [warning]/git push [<remote>] [<branch>][/warning] | [warning]/git branch [<name>][/warning]\n")
            return

        sub = args[0].lower()

        if sub == "status":
            await cmd_git(engine, [])

        elif sub == "diff":
            staged = len(args) > 1 and args[1].lower() in ("staged", "--cached")
            diff_text = git_workflow.get_git_diff(staged=staged, root_dir=".")
            console.print(f"\n[label]Git Diff ({'staged' if staged else 'unstaged'}):[/label]")
            if diff_text and diff_text != "<no git diff output>":
                for line in diff_text.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        console.print(f"[success]{line}[/success]")
                    elif line.startswith("-") and not line.startswith("---"):
                        console.print(f"[error]{line}[/error]")
                    else:
                        console.print(f"[dim]{line}[/dim]")
            else:
                console.print("  [dim]<no git diff output>[/dim]")
            console.print()

        elif sub == "commit":
            status = git_workflow.get_git_status(".")
            if not status.get("changes"):
                console.print("[warning]No modified or staged files to commit.[/warning]")
                return

            if len(args) > 1:
                message = " ".join(args[1:]).strip()
            else:
                console.print("[brand]🧠 Generating conventional commit message from git diff...[/brand]")
                message = await git_workflow.generate_commit_message(engine.config_mgr, ".")

            console.print(f"Commit Message: [accent]'{message}'[/accent]")
            success, output = git_workflow.run_git_commit(message=message, add_all=True)

            if success:
                console.print(f"[success]✔ Staged all changes and created commit:[/success] {message}")
            else:
                console.print(f"[error]Git commit failed:[/error] {output}")

        elif sub == "push":
            remote = args[1] if len(args) > 1 else "origin"
            branch = args[2] if len(args) > 2 else git_workflow.get_git_branch(".")
            console.print(f"[brand]🚀 Pushing active branch '[accent]{branch}[/accent]' to remote '[accent]{remote}[/accent]'...[/brand]")
            
            success, output = git_workflow.run_git_push(remote=remote, branch=branch)
            if success:
                console.print(f"[success]✔ Pushed successfully:[/success] {output}")
            else:
                console.print(f"[error]Git push failed:[/error] {output}")

        elif sub == "branch":
            if len(args) > 1:
                new_branch = args[1].strip()
                success, msg = git_workflow.create_or_switch_branch(new_branch)
                if success:
                    console.print(f"[success]{msg}[/success]")
                else:
                    console.print(f"[error]{msg}[/error]")
            else:
                current = git_workflow.get_git_branch(".")
                console.print(f"Current Git branch: [accent]{current}[/accent]\nUsage: [warning]/git branch <branch_name>[/warning]\n")

        else:
            console.print("[error]Usage: /git status | /git diff | /git commit [<msg>] | /git push [<remote>] [<branch>] | /git branch [<name>][/error]")

    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Git operation cancelled by user.[/warning]")


async def cmd_goal(engine: Any, args: List[str]):
    if not args:
        engine.goal_tool.render(console)
        return

    subcmd = args[0].lower()

    if subcmd == "clear":
        await engine.goal_tool.execute("clear")
        console.print("[warning]Goal cleared.[/warning]")

    elif subcmd == "done" and len(args) >= 2:
        try:
            idx = int(args[1])
        except ValueError:
            console.print("[error]Usage: /goal done <criterion number>[/error]")
            return
        result = await engine.goal_tool.execute("complete_criterion", criterion_index=idx)
        if "error" in result:
            console.print(f"[error]{result['error']}[/error]")
        else:
            console.print(f"[success]Marked criterion #{idx} complete.[/success]")
            engine.goal_tool.render(console)

    else:
        raw = " ".join(args)
        parts = [p.strip() for p in raw.split("|")]
        goal_text, criteria = parts[0], [p for p in parts[1:] if p]

        result = await engine.goal_tool.execute("set", goal=goal_text, success_criteria=criteria)
        if "error" in result:
            console.print(f"[error]{result['error']}[/error]")
        else:
            engine.goal_tool.render(console)


async def cmd_note(engine: Any, args: List[str]):
    if not args:
        notes = _read_notes()
        if not notes.strip():
            console.print("[dim]notes.md is currently empty.[/dim]")
        else:
            console.print("\n[success]=== Current Notes (notes.md) ===[/success]\n")
            console.print(Markdown(notes))
            console.print()
        console.print("Usage: [warning]/note[/warning], [warning]/note append <text>[/warning], or [warning]/note clear[/warning]\n")
        return

    subcmd = args[0].lower()
    if subcmd == "clear":
        _write_notes("")
        console.print("[warning]notes.md cleared.[/warning]")
    elif subcmd == "append":
        text_to_append = " ".join(args[1:]).strip()
        if not text_to_append:
            console.print("[error]Usage: /note append <text>[/error]")
            return
        _append_notes(text_to_append)
        console.print("[success]Appended text to notes.md.[/success]")
    else:
        text_to_append = " ".join(args).strip()
        _append_notes(text_to_append)
        console.print("[success]Appended text to notes.md.[/success]")


async def cmd_memory(engine: Any, args: List[str]):
    try:
        mem = _load_memory()

        if not args:
            console.print("\n[success]=== Saved Memory Items (memory.json) ===[/success]\n")
            if not mem:
                console.print("  [dim]No memory keys saved.[/dim]")
            else:
                for k, v in mem.items():
                    console.print(f"  • [label]{k}[/label]: {v}")
            console.print("\nUsage: [warning]/memory[/warning], [warning]/memory save <key> <value>[/warning], [warning]/memory get <key>[/warning], [warning]/memory search <query>[/warning], [warning]/memory delete <key>[/warning], or [warning]/memory clear[/warning]\n")
            return

        subcmd = args[0].lower()

        if subcmd == "save" and len(args) >= 3:
            key = args[1]
            val = " ".join(args[2:]).strip()
            mem[key] = val
            _save_memory(mem)
            console.print(f"[success]Saved memory key '{key}'.[/success]")

        elif subcmd == "get" and len(args) >= 2:
            key = args[1]
            if key in mem:
                console.print(f"[label]{key}:[/label] {mem[key]}")
            else:
                console.print(f"[error]Memory key '{key}' not found.[/error]")

        elif subcmd == "search" and len(args) >= 2:
            query = " ".join(args[1:]).strip()
            result = await memory_search.semantic_memory_search(query, mem, engine.config_mgr, verbose=True)

            if result["status"] == "empty":
                console.print("[dim]Memory is empty - nothing to search.[/dim]")
            elif result["status"] == "error":
                console.print(f"[error]Search failed:[/error] {result.get('error', 'Unknown error')}")
            else:
                matches = result["matches"]
                if result.get("answer"):
                    console.print(f"\n[success]Answer:[/success] {result['answer']}")
                if matches:
                    console.print("\n[label]Matching memory entries:[/label]")
                    for m in matches:
                        console.print(f"  • [accent]{m['key']}[/accent]: {m['value']}  [dim]({m['why']})[/dim]")
                elif not result.get("answer"):
                    console.print("[dim]No relevant memory entries found.[/dim]")

        elif subcmd == "delete" and len(args) >= 2:
            key = args[1]
            if key in mem:
                del mem[key]
                _save_memory(mem)
                console.print(f"[warning]Deleted memory key '{key}'.[/warning]")
            else:
                console.print(f"[error]Memory key '{key}' not found.[/error]")

        elif subcmd == "clear":
            _save_memory({})
            console.print("[warning]Cleared all persistent memories from memory.json.[/warning]")

        else:
            console.print("[error]Usage: /memory save <key> <value> | /memory get <key> | /memory search <query> | /memory delete <key> | /memory clear[/error]")
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Memory operation cancelled by user.[/warning]")


async def cmd_dream(engine: Any, args: List[str]):
    try:
        console.print("[brand]💤 Dreaming...[/brand] [dim]Analyzing the conversation for reusable notes, memories, and skills.[/dim]")

        extraction, error = await dream_extract(engine.messages, engine.config_mgr)
        if error:
            console.print(f"[warning]{error}[/warning]")
            return

        notes = extraction["notes"]
        memory_items = extraction["memory"]
        skills = extraction["skills"]

        if not notes and not memory_items and not skills:
            console.print("[dim]Nothing worth extracting from this conversation.[/dim]")
            return

        def prompt_selection() -> str:
            try:
                return input("Selection > ").strip()
            except (EOFError, KeyboardInterrupt):
                return ""

        def resolve_indices(raw: str, count: int) -> set:
            raw = raw.lower().strip()
            if raw in ("all", "a", "y", "yes"):
                return set(range(count))
            if raw in ("none", "n", "no", "", "skip"):
                return set()
            indices = set()
            for part in raw.replace(" ", "").split(","):
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < count:
                        indices.add(idx)
            return indices

        loop = asyncio.get_running_loop()
        applied_notes = applied_memory = applied_skills = 0

        if notes:
            console.print(f"\n[label]📝 Candidate Notes ({len(notes)}):[/label]")
            for i, n in enumerate(notes, 1):
                console.print(f"  {i}. {n}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(notes))
            for i in sorted(chosen):
                _append_notes(f"- {notes[i]}")
            applied_notes = len(chosen)

        if memory_items:
            console.print(f"\n[label]🧠 Candidate Memory Facts ({len(memory_items)}):[/label]")
            for i, m in enumerate(memory_items, 1):
                console.print(f"  {i}. [accent]{m['key']}[/accent] = {m['value']}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(memory_items))
            if chosen:
                mem = _load_memory()
                for i in chosen:
                    mem[memory_items[i]["key"]] = memory_items[i]["value"]
                _save_memory(mem)
            applied_memory = len(chosen)

        if skills:
            console.print(f"\n[label]🛠️ Candidate Skills ({len(skills)}):[/label]")
            existing_names = set(engine.skill_registry.list_skills().keys())
            for i, s in enumerate(skills, 1):
                dup_tag = " [warning](exists - will be overwritten)[/warning]" if s["name"] in existing_names else ""
                console.print(f"  {i}. [accent]{s['name']}[/accent]{dup_tag} - {s['description']}")
            console.print("[dim]Enter numbers to save (e.g. 1,3), 'all', or 'none':[/dim]")
            raw = await loop.run_in_executor(None, prompt_selection)
            chosen = resolve_indices(raw, len(skills))
            for i in chosen:
                s = skills[i]
                decl = DeclarativeSkill(
                    name=s["name"],
                    description=s["description"] or "Skill extracted via /dream.",
                    system_instruction=s["system_instruction"],
                    enabled=True
                )
                engine.skill_registry.register(decl)
            if chosen:
                engine.skill_registry.save_to_file()
                engine.update_system_message()
            applied_skills = len(chosen)

        console.print(
            f"\n[success]Dream complete.[/success] Saved {applied_notes} note(s), "
            f"{applied_memory} memory fact(s), and {applied_skills} skill(s)."
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Dream operation cancelled by user.[/warning]")


async def cmd_script(engine: Any, args: List[str]):
    if not args:
        console.print("[error]Usage: /script <path/to/script.txt>[/error]")
        return

    filepath = " ".join(args).strip()
    try:
        await engine.run_script_file(filepath)
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Script execution cancelled by user.[/warning]")


async def cmd_project(engine: Any, args: List[str]):
    if args and args[0].lower() in ("map", "graph"):
        map_text = repo_map.get_repo_map_instructions(".", token_budget=engine.config_mgr.config.budgets.repo_map)
        if map_text:
            console.print(f"\n[success]=== Repository Architecture Map ===[/success]\n")
            console.print(Markdown(map_text))
            console.print()
        else:
            console.print("[dim]No codebase symbols found to generate repository map.[/dim]")
        return

    filename, content = project_rules.find_and_read_project_rules(".")
    if args and args[0].lower() == "reload":
        engine.update_system_message()
        if filename:
            console.print(f"[success]Reloaded project rules from '{filename}'.[/success]")
        else:
            console.print("[dim]No project rules file (PROJECT.md, MESH.md, AGENTS.md) found in workspace.[/dim]")
        return

    if filename and content:
        console.print(f"\n[success]=== Project Rules ({filename}) ===[/success]\n")
        console.print(Markdown(content))
        console.print()
    else:
        console.print("[dim]No project rules file (PROJECT.md, MESH.md, AGENTS.md) found in current directory.[/dim]")
    console.print("Usage: [warning]/project[/warning] | [warning]/project map[/warning] | [warning]/project reload[/warning]\n")


async def cmd_reflexion(engine: Any, args: List[str]):
    try:
        if not args:
            lessons_text = reflexion.get_reflexion_instructions()
            if lessons_text:
                console.print("\n[success]=== Reflexion Journal ===[/success]\n")
                console.print(Markdown(lessons_text))
                console.print()
            else:
                console.print("[dim]No distilled reflexion lessons currently saved.[/dim]")
            console.print("Usage: [warning]/reflexion distill[/warning] | [warning]/reflexion clear[/warning]\n")
            return

        sub = args[0].lower()
        if sub == "distill":
            console.print("[brand]🧠 Distilling reflexion lessons...[/brand]")
            success, msg = await reflexion.distill_reflexion_lessons(engine.config_mgr)
            if success:
                engine.update_system_message()
                console.print(f"[success]{msg}[/success]")
            else:
                console.print(f"[warning]{msg}[/warning]")
        elif sub == "clear":
            reflexion.clear_reflexion()
            engine.update_system_message()
            console.print("[warning]Reflexion journal cleared.[/warning]")
        else:
            console.print("[error]Usage: /reflexion distill | /reflexion clear[/error]")
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[warning]⛔ Reflexion operation cancelled by user.[/warning]")


def register_session_commands(engine: Any):
    engine.cmd_registry.register("cd", "Change working directory and reload workspace context: /cd <path>", lambda args: cmd_cd(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("shell", "Execute shell command directly (bypasses LLM): /shell <cmd> | !<cmd>", lambda args: cmd_shell(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("python", "Execute Python snippet directly (bypasses LLM): /python <code> | #<code>", lambda args: cmd_python(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("goal", "View, set, or manage pinned session goal: /goal [<text>] [| criteria] | /goal done <#> | /goal clear", lambda args: cmd_goal(engine, args), category="Memory & Knowledge")
    engine.cmd_registry.register("note", "View or edit persistent Markdown notes: /note [append <text>|clear]", lambda args: cmd_note(engine, args), category="Memory & Knowledge")
    engine.cmd_registry.register("memory", "View or edit persistent memory key-value store: /memory [save|get|list|search|delete|clear] <args>", lambda args: cmd_memory(engine, args), category="Memory & Knowledge")
    engine.cmd_registry.register("dream", "Analyze conversation transcript and extract persistent notes, memory facts, and skills: /dream", lambda args: cmd_dream(engine, args), category="Memory & Knowledge")
    engine.cmd_registry.register("script", "Execute commands and prompts line-by-line from script file: /script <file.txt>", lambda args: cmd_script(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("project", "View or reload project rules and repository map: /project [map|reload]", lambda args: cmd_project(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("reflexion", "View or distill cross-session error lessons: /reflexion [distill|clear]", lambda args: cmd_reflexion(engine, args), category="Memory & Knowledge")
    engine.cmd_registry.register("checkpoint", "Save, fork, restore, or list session checkpoints: /checkpoint [save|fork|restore|list] <args>", lambda args: cmd_checkpoint(engine, args), category="Session & System")
    engine.cmd_registry.register("diff", "Display unified file diff or revert last edit: /diff | /diff undo", lambda args: cmd_diff(engine, args), category="Workspace & Developer Tools")
    engine.cmd_registry.register("git", "Run native Git commands: /git [status|diff|commit|push|branch]", lambda args: cmd_git(engine, args), category="Workspace & Developer Tools")
