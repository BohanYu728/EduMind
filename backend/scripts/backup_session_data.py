"""升级会话归属前，以 SQLite 在线备份保存主库和两种索引。"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = root / ".local" / "backups" / ("sessions-" + datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S"))
target.mkdir(parents=True, exist_ok=True)
for relative in ("edumind.db", "data/vectors.db", "data/vectors-local-v1.db"):
    source = root / "backend" / relative
    if source.exists():
        with (
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src,
            sqlite3.connect(target / source.name) as dst,
        ):
            src.backup(dst)
print(target)
