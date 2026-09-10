import argparse
import asyncio
import os
import sys
from engine import MeshEngine


def set_terminal_title(title: str) -> None:
    """Set the terminal window/tab title across Windows, macOS, and Linux."""
    if not sys.stdout.isatty():
        return

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(title)
    else:
        # OSC 0 sets both window title and icon/tab name in Unix terminals
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()


def main():
    set_terminal_title("Mesh")

    parser = argparse.ArgumentParser(description="Mesh - Modern AI Harness CLI")
    parser.add_argument("script", nargs="?", help="Optional path to a script file to execute on launch")
    parser.add_argument("-f", "--file", help="Path to a script file to execute on launch")
    parser.add_argument("-n", "--non-interactive", action="store_true", help="Exit automatically after running script file")
    parser.add_argument("-C", "--cwd", "--dir", dest="cwd", help="Set the initial working directory before starting Mesh (defaults to the directory Mesh was launched from)")

    # Logging and Session CLI flags
    parser.add_argument("-l", "--log", nargs="?", const="session.md", help="Enable Markdown session logging to specified file (default: session.md)")
    parser.add_argument("-s", "--session", help="Load or create a named disk session under sessions/")
    parser.add_argument("-r", "--resume", action="store_true", help="Resume the most recently saved disk session")

    parsed_args = parser.parse_args()
    script_path = parsed_args.file or parsed_args.script

    if parsed_args.cwd:
        target_dir = os.path.abspath(os.path.expanduser(parsed_args.cwd))
        if not os.path.isdir(target_dir):
            print(f"[Error] Working directory '{parsed_args.cwd}' does not exist or is not a directory.", file=sys.stderr)
            sys.exit(1)
        os.chdir(target_dir)

    engine = MeshEngine()
    try:
        asyncio.run(
            engine.run(
                script_file=script_path,
                non_interactive=parsed_args.non_interactive,
                log_file=parsed_args.log,
                session_name=parsed_args.session,
                resume_latest=parsed_args.resume
            )
        )
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
