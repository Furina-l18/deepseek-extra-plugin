"""从 LivingMemory 的会话库读取按人拆分的聊天记忆。

数据来自 astrbot_plugin_livingmemory 的 conversations.db：
    messages(id, session_id, role, content, sender_id, sender_name,
             group_id, platform, timestamp, metadata)
sender_id 就是 QQ 号，正好可以用来分人。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

LIVINGMEMORY_DIR = "astrbot_plugin_livingmemory"
DB_NAME = "conversations.db"


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: float
    id: int = 0


@dataclass
class SenderStat:
    sender_id: str
    sender_name: str
    count: int
    last_ts: float


def resolve_db(plugin_data_dir: Path) -> Path | None:
    """在 plugin_data 的兄弟目录里找 LivingMemory 的会话库。"""
    candidate = plugin_data_dir.parent / LIVINGMEMORY_DIR / DB_NAME
    if candidate.is_file():
        return candidate
    # 兜底：有些部署把数据放在插件目录下的 data/
    fallback = Path(__file__).parent.parent / LIVINGMEMORY_DIR / "data" / DB_NAME
    if fallback.is_file():
        return fallback
    return None


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def list_senders(db_path: Path, limit: int = 200) -> list[SenderStat]:
    """按发言量列出联系人。"""
    try:
        con = _connect(db_path)
    except Exception:
        return []
    try:
        rows = con.execute(
            """
            SELECT sender_id,
                   (SELECT sender_name FROM messages m2
                     WHERE m2.sender_id = m1.sender_id
                     ORDER BY timestamp DESC LIMIT 1) AS sender_name,
                   COUNT(*) AS c,
                   MAX(timestamp) AS last_ts
              FROM messages m1
             WHERE role = 'user' AND sender_id IS NOT NULL AND sender_id <> ''
             GROUP BY sender_id
             ORDER BY c DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            SenderStat(
                sender_id=str(r["sender_id"]),
                sender_name=str(r["sender_name"] or r["sender_id"]),
                count=int(r["c"]),
                last_ts=float(r["last_ts"] or 0.0),
            )
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


def fetch_messages(db_path: Path, sender_id: str, limit: int = 200) -> list[ChatMessage]:
    """取某个人最近的发言（时间正序）。"""
    try:
        con = _connect(db_path)
    except Exception:
        return []
    try:
        rows = con.execute(
            """
            SELECT id, role, content, timestamp
              FROM messages
             WHERE sender_id = ? AND role = 'user'
             ORDER BY timestamp DESC
             LIMIT ?
            """,
            (sender_id, limit),
        ).fetchall()
        out = [
            ChatMessage(
                role=str(r["role"]),
                content=str(r["content"] or ""),
                timestamp=float(r["timestamp"] or 0.0),
                id=int(r["id"] or 0),
            )
            for r in rows
        ]
        out.reverse()
        return out
    except Exception:
        return []
    finally:
        con.close()


def fetch_messages_since(
    db_path: Path, sender_id: str, since_ts: float, limit: int = 2000
) -> list[ChatMessage]:
    """只取某个时间点之后的新发言（时间正序），用于每日增量推理。"""
    try:
        con = _connect(db_path)
    except Exception:
        return []
    try:
        rows = con.execute(
            """
            SELECT id, role, content, timestamp
              FROM messages
             WHERE sender_id = ? AND role = 'user' AND timestamp > ?
             ORDER BY timestamp ASC
             LIMIT ?
            """,
            (sender_id, float(since_ts), limit),
        ).fetchall()
        return [
            ChatMessage(
                role=str(r["role"]),
                content=str(r["content"] or ""),
                timestamp=float(r["timestamp"] or 0.0),
                id=int(r["id"] or 0),
            )
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()


def fetch_all_messages(db_path: Path, sender_id: str, limit: int = 4000) -> list[ChatMessage]:
    """按人取更多历史（用于首次全量总结）。"""
    return fetch_messages(db_path, sender_id, limit)


def fetch_messages_after_id(
    db_path: Path, sender_id: str, after_id: int, limit: int = 2000
) -> list[ChatMessage]:
    """只取「还没被情感推理标记过」的发言（按消息 id 水位，正序）。"""
    try:
        con = _connect(db_path)
    except Exception:
        return []
    try:
        rows = con.execute(
            """
            SELECT id, role, content, timestamp
              FROM messages
             WHERE sender_id = ? AND role = 'user' AND id > ?
             ORDER BY id ASC
             LIMIT ?
            """,
            (sender_id, int(after_id), limit),
        ).fetchall()
        return [
            ChatMessage(
                role=str(r["role"]),
                content=str(r["content"] or ""),
                timestamp=float(r["timestamp"] or 0.0),
                id=int(r["id"] or 0),
            )
            for r in rows
        ]
    except Exception:
        return []
    finally:
        con.close()
