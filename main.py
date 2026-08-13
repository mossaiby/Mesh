import argparse
import asyncio
from engine import MeshEngine


def main():
    parser = argparse.ArgumentParser(description="Mesh - Modern AI Harness CLI")
    parser.add_argument("script", nargs="?", help="Optional path to a script file to execute on launch")
    parser.add_argument("-f", "--file", help="Path to a script file to execute on launch")
    parser.add_argument("-n", "--non-interactive", action="store_true", help="Exit automatically after running script file")
    
    # Logging and Session CLI flags
    parser.add_argument("-l", "--log", nargs="?", const="session.md", help="Enable Markdown session logging to specified file (default: session.md)")
    parser.add_argument("-s", "--session", help="Load or create a named disk session under sessions/")
    parser.add_argument("-r", "--resume", action="store_true", help="Resume the most recently saved disk session")

    parsed_args = parser.parse_args()
    script_path = parsed_args.file or parsed_args.script

    engine = MeshEngine()
    asyncio.run(
        engine.run(
            script_file=script_path,
            non_interactive=parsed_args.non_interactive,
            log_file=parsed_args.log,
            session_name=parsed_args.session,
            resume_latest=parsed_args.resume
        )
    )


if __name__ == "__main__":
    main()
