import asyncio
import ast
import difflib
import json
from typing import Dict, List, Any, Optional
from tools.base import BaseTool
import self_heal
from theme import console


def _extract_error(raw_result: Any) -> Optional[str]:
    """Returns the error string from a tool result if it represents a
    failure (the {"error": ...} convention used across every tool in this
    codebase), otherwise None."""
    if isinstance(raw_result, dict):
        if "error" in raw_result:
            return str(raw_result["error"])
        return None

    if isinstance(raw_result, str):
        s = raw_result.strip()
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict) and "error" in parsed:
                    return str(parsed["error"])
            except Exception:
                pass

    return None


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self.subagent_proxy: Optional[Any] = None
        # Set externally (see main.py) - two independent, additive recovery
        # layers for failed tool calls. Left None here so ToolRegistry has
        # no hard dependency on it; execute() degrades to "no healing" when
        # self_healer is None or disabled.
        self.self_healer: Optional[Any] = None
        # Set externally (see main.py) - risk-assesses tools flagged with
        # requires_guard=True before they execute. None/disabled means no
        # guard check runs at all.
        self.safety_guard: Optional[Any] = None

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        if tool_name in self._tools:
            del self._tools[tool_name]

    def get_schemas(self, inject_intent: bool = True) -> List[Dict[str, Any]]:
        use_intent = inject_intent and (
            self.subagent_proxy is not None and self.subagent_proxy.enabled
        )
        return [tool.to_openai_schema(inject_intent=use_intent) for tool in self._tools.values()]

    async def _run_tool_once(self, tool: BaseTool, tool_name: str, kwargs: Dict[str, Any]):
        try:
            result = await tool.execute(**kwargs)
            return result, _extract_error(result)
        except Exception as e:
            return None, f"Error executing tool '{tool_name}': {str(e)}"

    async def _execute_with_healing(self, tool: BaseTool, tool_name: str, kwargs: Dict[str, Any]):
        """Runs the tool, applying the two SelfHealer recovery layers on
        failure if a healer is attached and enabled. Returns (raw_result,
        healing_notes) - healing_notes is empty unless healing actually
        changed the outcome or was attempted."""
        healer = self.self_healer
        notes: List[str] = []

        result, err = await self._run_tool_once(tool, tool_name, kwargs)

        if err is None:
            return result, notes

        if healer is None or not healer.enabled or self_heal.is_non_healable(err):
            return (result if result is not None else {"error": err}), notes

        # Layer 1: mechanical retry for transient-looking errors, no model call.
        if self_heal.is_transient(err):
            for attempt in range(1, healer.mechanical_retries + 1):
                await asyncio.sleep(healer.mechanical_delay * attempt)
                console.print(
                    f"[warning]\U0001F501 Self-heal:[/warning] transient error from "
                    f"'{tool_name}', retrying ({attempt}/{healer.mechanical_retries})..."
                )
                result, err = await self._run_tool_once(tool, tool_name, kwargs)
                if err is None:
                    notes.append(f"Recovered from a transient error after {attempt} automatic retry(ies).")
                    return result, notes
            # Still failing after mechanical retries - fall through to LLM repair below.

        # Layer 2: one LLM-assisted argument repair attempt.
        corrected = await healer.attempt_repair(
            tool_schema=tool.to_openai_schema(inject_intent=False),
            tool_name=tool_name,
            failed_arguments=kwargs,
            error_message=err
        )
        if corrected is not None and corrected != kwargs:
            console.print(f"[warning]\U0001FA79 Self-heal:[/warning] retrying '{tool_name}' with auto-corrected arguments.")
            new_result, new_err = await self._run_tool_once(tool, tool_name, corrected)
            if new_err is None:
                notes.append("Auto-repaired the failed arguments and succeeded on retry.")
                return new_result, notes
            # Repair attempt also failed - fall through to the original error.

        return (result if result is not None else {"error": err}), notes

    async def execute(self, tool_name: str, arguments_json: str) -> str:
        try:
            return await self._execute_inner(tool_name, arguments_json)
        except Exception as e:
            # Last-resort safety net: nothing above this should normally
            # raise (each stage has its own handling), but execute() must
            # never propagate an exception - callers in main.py/delegation.py
            # await it directly with no try/except of their own.
            return json.dumps({"error": f"Error executing tool '{tool_name}': {str(e)}"})

    async def _execute_inner(self, tool_name: str, arguments_json: str) -> str:
        healer = self.self_healer
        healing_notes: List[str] = []

        resolved_name = tool_name
        if resolved_name not in self._tools:
            # Mechanical fix: a close typo of a real tool name (e.g. the
            # model wrote "todo_manger") is auto-corrected with no model
            # call, rather than failing outright.
            close = difflib.get_close_matches(tool_name, list(self._tools.keys()), n=1, cutoff=0.72)
            if close:
                resolved_name = close[0]
                healing_notes.append(f"Tool '{tool_name}' not found - auto-corrected to '{resolved_name}'.")
                console.print(f"[warning]\U0001F501 Self-heal:[/warning] unknown tool '{tool_name}', using closest match '{resolved_name}'.")
            else:
                return json.dumps({"error": f"Tool '{tool_name}' not registered."})

        tool = self._tools[resolved_name]

        try:
            kwargs = json.loads(arguments_json) if arguments_json else {}
        except Exception as e:
            parse_error = f"Arguments were not valid JSON: {e}"
            if healer is not None and healer.enabled and resolved_name not in self_heal.REPAIR_EXCLUDED_TOOLS:
                corrected = await healer.attempt_repair(
                    tool_schema=tool.to_openai_schema(inject_intent=False),
                    tool_name=resolved_name,
                    failed_arguments={"_raw_arguments": arguments_json},
                    error_message=parse_error
                )
                if corrected is not None:
                    kwargs = corrected
                    healing_notes.append("Malformed tool arguments were auto-repaired before execution.")
                    console.print(f"[warning]\U0001FA79 Self-heal:[/warning] repaired malformed arguments for '{resolved_name}'.")
                else:
                    return json.dumps({"error": f"Error executing tool '{resolved_name}': {parse_error}"})
            else:
                return json.dumps({"error": f"Error executing tool '{resolved_name}': {parse_error}"})

        # Extract and strip _intent parameter if present
        intent = kwargs.pop("_intent", "").strip()

        # Safety Guard: risk-assess tools flagged with requires_guard=True
        # (shell, file writes/edits, MCP tools) before executing. A denial
        # blocks the call outright - it's never handed to self-healing,
        # since a blocked call isn't a bug to fix.
        guard = self.safety_guard
        guard_info: Optional[Dict[str, Any]] = None
        if getattr(tool, "requires_guard", False) and guard is not None and guard.enabled:
            allowed, guard_info = await guard.check(resolved_name, kwargs)
            if not allowed:
                return json.dumps({
                    "error": f"Blocked by Safety Guard: {guard_info.get('reason', 'assessed as too risky to run automatically.')}",
                    "_guard": guard_info
                })

        raw_result, run_notes = await self._execute_with_healing(tool, resolved_name, kwargs)
        healing_notes.extend(run_notes)

        result_str = json.dumps(raw_result) if not isinstance(raw_result, str) else raw_result

        # Fold in a short transparency note about any healing that occurred,
        # without breaking JSON validity for anything downstream that parses
        # the result (including SubAgentProxy distillation below).
        if (healing_notes or guard_info) and result_str.startswith("{"):
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, dict):
                    if healing_notes:
                        parsed["_self_healed"] = healing_notes
                    if guard_info:
                        parsed["_guard"] = guard_info
                    result_str = json.dumps(parsed)
            except Exception:
                pass

        # Route through SubAgentProxy if tool is proxied and sub-agent is enabled
        if (
            tool.is_proxied 
            and self.subagent_proxy is not None 
            and self.subagent_proxy.enabled 
            and intent
        ):
            return await self.subagent_proxy.distill_tool_result(
                tool_name=resolved_name, 
                intent=intent, 
                raw_result=result_str
            )

        # Ensure valid JSON string returned for non-proxied tools or when proxy is disabled
        if not (result_str.startswith("{") or result_str.startswith("[")):
            return json.dumps({"result": result_str})

        return result_str


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluates basic arithmetic expressions."
    is_proxied = False  # Direct execution
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression to evaluate (e.g. '12 * 4')"
            }
        },
        "required": ["expression"]
    }

    # Only these AST node types are permitted - no Name, Call, Attribute, or
    # Subscript nodes exist in this whitelist, which is exactly what closes
    # off the classic `eval(expr, {"__builtins__": None}, {})` sandbox
    # escape (e.g. `().__class__.__bases__[0].__subclasses__()`): that
    # attack never calls a builtin or looks up a name, it only chains
    # attribute access and calls on a literal, so stripping __builtins__
    # alone does nothing to stop it. Rejecting Attribute/Call/Subscript
    # nodes at the AST level does.
    _ALLOWED_NODES = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.UAdd, ast.USub,
    )

    @classmethod
    def _safe_eval(cls, expression: str):
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid expression: {e}")

        for node in ast.walk(tree):
            if not isinstance(node, cls._ALLOWED_NODES):
                raise ValueError(f"Expression contains a disallowed construct: {type(node).__name__}")
            if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric constants are allowed.")

        return cls._eval_node(tree.body)

    @classmethod
    def _eval_node(cls, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                # Guard against absurdly expensive exponents (e.g. 9**9**9)
                # tying up the event loop, since this whole evaluator runs
                # synchronously with no timeout.
                if isinstance(right, (int, float)) and abs(right) > 1000:
                    raise ValueError("Exponent too large.")
                return left ** right
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        if isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    async def execute(self, expression: str) -> Dict[str, Any]:
        try:
            result = self._safe_eval(expression)
            return {"result": result}
        except ZeroDivisionError:
            return {"error": "Division by zero."}
        except Exception as e:
            return {"error": str(e)}