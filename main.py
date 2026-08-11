import argparse
import asyncio
from engine import MeshEngine


def main():
    parser = argparse.ArgumentParser(description="Mesh - Modular AI CLI")
    parser.add_argument("script", nargs="?", help="Optional path to a script file to execute on launch")
    parser.add_argument("-f", "--file", help="Path to a script file to execute on launch")
    parser.add_argument("-n", "--non-interactive", action="store_true", help="Exit automatically after running script file")
    
    parsed_args = parser.parse_args()
    script_path = parsed_args.file or parsed_args.script

    engine = MeshEngine()
    asyncio.run(engine.run(script_file=script_path, non_interactive=parsed_args.non_interactive))


if __name__ == "__main__":
    main()
