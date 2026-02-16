from __future__ import annotations

import os
import sqlite3
from typing import Dict, List


class Storage:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS image_hashes (
                image_url TEXT PRIMARY KEY,
                image_hash TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def add_subscriber(self, chat_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO subscribers(chat_id) VALUES (?)",
            (chat_id,),
        )
        self._conn.commit()

    def remove_subscriber(self, chat_id: int) -> None:
        self._conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        self._conn.commit()

    def list_subscribers(self) -> List[int]:
        rows = self._conn.execute("SELECT chat_id FROM subscribers").fetchall()
        return [row[0] for row in rows]

    def get_hashes(self) -> Dict[str, str]:
        rows = self._conn.execute(
            "SELECT image_url, image_hash FROM image_hashes"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def upsert_hash(self, image_url: str, image_hash: str) -> None:
        self._conn.execute(
            """
            INSERT INTO image_hashes(image_url, image_hash)
            VALUES (?, ?)
            ON CONFLICT(image_url) DO UPDATE SET
                image_hash = excluded.image_hash,
                updated_at = CURRENT_TIMESTAMP
            """,
            (image_url, image_hash),
        )
        self._conn.commit()

