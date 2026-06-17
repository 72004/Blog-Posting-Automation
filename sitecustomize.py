from __future__ import annotations

import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent
src_path = project_root / "src"

if src_path.is_dir():
    src_value = str(src_path)
    if src_value not in sys.path:
        sys.path.insert(0, src_value)