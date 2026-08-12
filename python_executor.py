import io
import sys
from typing import Dict, Any, Tuple


class PythonExecutor:
    """
    Executes Python code snippets inside a persistent session namespace,
    capturing stdout/stderr and return values.
    """
    def __init__(self):
        self.globals_namespace: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
        }

    def execute_snippet(self, code: str) -> Tuple[bool, str]:
        """
        Executes code string inside persistent globals_namespace.
        Returns (success, captured_output).
        """
        code = code.strip()
        if not code:
            return True, ""

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = stdout_buffer
        sys.stderr = stderr_buffer

        success = True
        result_output = ""

        try:
            # First try evaluating as an expression to return value directly
            try:
                compiled_expr = compile(code, "<python_snippet>", "eval")
                eval_res = eval(compiled_expr, self.globals_namespace)
                if eval_res is not None:
                    print(repr(eval_res))
            except SyntaxError:
                # Fall back to executing as multi-line statements
                compiled_exec = compile(code, "<python_snippet>", "exec")
                exec(compiled_exec, self.globals_namespace)

        except Exception as e:
            success = False
            print(f"Python Execution Error: {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        out_str = stdout_buffer.getvalue().strip()
        err_str = stderr_buffer.getvalue().strip()

        if out_str and err_str:
            result_output = f"{out_str}\n{err_str}"
        elif out_str:
            result_output = out_str
        elif err_str:
            result_output = err_str

        return success, result_output


# Global python executor instance
python_executor = PythonExecutor()
