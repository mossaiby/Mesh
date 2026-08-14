import os
import pytest
from pathlib import Path
from tools.permissions import PermissionManager


def test_permission_manager_path_containment(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]

    inside_file = os.path.join(temp_workspace, "src", "main.py")
    outside_file = str(Path(temp_workspace).parent / "sensitive.txt")

    assert pm.is_path_allowed(inside_file) is True
    assert pm.is_path_allowed(outside_file) is False


def test_permission_manager_add_and_remove(temp_workspace):
    pm = PermissionManager()
    extra_dir = os.path.join(temp_workspace, "extra")
    os.makedirs(extra_dir, exist_ok=True)

    pm.add_dir(extra_dir)
    assert any(Path(extra_dir).resolve() == Path(d).resolve() for d in pm.allowed_dirs)

    pm.remove_dir(extra_dir)
    assert not any(Path(extra_dir).resolve() == Path(d).resolve() for d in pm.allowed_dirs)


@pytest.mark.asyncio
async def test_permission_manager_auto_approve_in_yolo(temp_workspace):
    pm = PermissionManager()
    pm.allowed_dirs = [temp_workspace]
    pm.auto_approve = True  # Simulates YOLO mode

    outside_file = str(Path(temp_workspace).parent / "external.txt")
    # Should automatically allow without prompting user
    allowed = await pm.check_and_request_permission("read_file", outside_file)
    assert allowed is True
