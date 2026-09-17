"""
Standalone diagnostic script - exercises the REAL execute_python tool
(skills.code_skill.PythonExecutionTool) exactly the way the model would
call it during a conversation, bypassing the need to coax the LLM into
doing so. Run this from your Mesh checkout root:

    python test_windows_execute_python.py

Reads results directly - no Mesh session needed. Requires
sandbox_windows_experimental: true in config.json (same requirement as
the shell path we've already tested).
"""

import asyncio
import os

from config import ConfigManager
from skills.code_skill import PythonExecutionTool
from tools.permissions import PermissionManager


async def main():
    cfg = ConfigManager()
    if not getattr(cfg.config, "sandbox_windows_experimental", False):
        print("sandbox_windows_experimental is not enabled in config.json - enable it first.")
        return

    pm = PermissionManager()
    # Match your current Mesh session's allow-list as closely as possible;
    # adjust this if your actual /dirs list differs.
    pm.allowed_dirs = [os.getcwd()]

    tool = PythonExecutionTool(cfg, pm)

    print("=== Test 1: basic execution ===")
    r = await tool.execute(code="print('hello from execute_python')")
    print(r)

    print("\n=== Test 2: write inside the allow-list (should succeed) ===")
    target = os.path.join(os.getcwd(), "execute_python_test.txt")
    r = await tool.execute(code=f"open(r'{target}', 'w').write('written by execute_python')")
    print(r)
    print("File exists after write:", os.path.exists(target))
    if os.path.exists(target):
        print("File contents:", open(target).read())
        os.remove(target)

    print("\n=== Test 3: write OUTSIDE the allow-list (should fail) ===")
    outside_target = r"C:\Windows\Temp\execute_python_should_not_exist.txt"
    r = await tool.execute(code=f"open(r'{outside_target}', 'w').write('should not happen')")
    print(r)
    print("File exists after blocked write (should be False):", os.path.exists(outside_target))

    print("\n=== Test 4: a command that takes a couple seconds, to sanity-check timing/cleanup ===")
    r = await tool.execute(code="import time; time.sleep(2); print('done sleeping')")
    print(r)


if __name__ == "__main__":
    asyncio.run(main())
