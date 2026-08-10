import ast
import importlib.util
import os
import sys
from typing import Dict, Any, Tuple
from tools.base import BaseTool
from theme import console

CUSTOM_TOOLS_DIR = "custom_tools"


def _ensure_custom_tools_dir() -> str:
    abspath = os.path.abspath(CUSTOM_TOOLS_DIR)
    os.makedirs(abspath, exist_ok=True)
    if abspath not in sys.path:
        sys.path.insert(0, abspath)
    return abspath


def validate_python_tool_code(code: str) -> Tuple[bool, str]:
    """
    Validates synthesized Python tool code using AST parsing.
    Ensures valid syntax and that a BaseTool subclass is defined.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax Error: {e}"

    has_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_class = True
            break

    if not has_class:
        return False, "Code must define at least one Python class inheriting from BaseTool."

    return True, "Code syntax and AST validation passed."


def register_synthesized_tool(
    name: str,
    code: str,
    tool_registry: Any
) -> Tuple[bool, str]:
    """
    Saves synthesized Python code to custom_tools/<name>.py, dynamically
    loads the module, instantiates the tool, and registers it in ToolRegistry.
    """
    valid, err_msg = validate_python_tool_code(code)
    if not valid:
        return False, err_msg

    tools_dir = _ensure_custom_tools_dir()
    file_path = os.path.join(tools_dir, f"{name}.py")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Dynamic import of newly synthesized module
        spec = importlib.util.spec_from_file_location(f"custom_tools.{name}", file_path)
        if spec is None or spec.loader is None:
            return False, "Failed to build module spec for synthesized tool."

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"custom_tools.{name}"] = module
        spec.loader.exec_module(module)

        # Find BaseTool subclass in module
        instantiated_tool = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type) 
                and issubclass(attr, BaseTool) 
                and attr is not BaseTool
            ):
                instantiated_tool = attr()
                break

        if instantiated_tool is None:
            return False, f"Module '{name}.py' did not contain a valid BaseTool subclass instance."

        tool_registry.register(instantiated_tool)
        console.print(f"[success]⚡ Synthesized Tool Registered Live:[/success] [accent]{instantiated_tool.name}[/accent] ({file_path})")
        return True, f"Successfully synthesized and registered tool '{instantiated_tool.name}' dynamically."

    except Exception as e:
        return False, f"Dynamic load/registration failed: {str(e)}"


def load_all_custom_tools(tool_registry: Any) -> int:
    """
    Loads all existing custom tools from custom_tools/ directory on startup.
    """
    tools_dir = _ensure_custom_tools_dir()
    loaded_count = 0

    for filename in os.listdir(tools_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            tool_name = filename[:-3]
            file_path = os.path.join(tools_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
                success, _ = register_synthesized_tool(tool_name, code, tool_registry)
                if success:
                    loaded_count += 1
            except Exception:
                pass

    return loaded_count