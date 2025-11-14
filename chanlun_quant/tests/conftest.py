"""pytest 配置，确保可以从源码根目录导入包。"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_on_path() -> None:
    tests_dir = Path(__file__).resolve().parent
    project_root = tests_dir.parent.parent
    project_str = str(project_root)
    if project_str not in sys.path:
        sys.path.insert(0, project_str)

    root_drive = str(project_root.parent)
    if root_drive in sys.path:
        sys.path.remove(root_drive)



_ensure_project_on_path()

