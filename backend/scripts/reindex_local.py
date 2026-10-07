"""在 backend 目录执行：.venv/Scripts/python.exe scripts/reindex_local.py。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db
from app.knowledge.reindex import rebuild_local_index

if __name__ == "__main__":
    init_db()
    print(rebuild_local_index())
