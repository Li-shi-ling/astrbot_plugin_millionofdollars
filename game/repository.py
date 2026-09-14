"""SQLite 持久化。

设计依据：``docs/game-implementation-design.md`` 第 8 节。

使用标准库 :mod:`sqlite3`，不新增依赖。房间以 ``(platform_id, group_openid)``
为键，消息结果以 ``(platform_id, group_openid, message_id)`` 保证幂等。
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import SCHEMA_VERSION, GameSnapshot, SnapshotError

META_SCHEMA_VERSION = "schema_version"


class RepositoryError(RuntimeError):
    """持久化层错误。"""


class GameRepository:
    """对局与幂等结果的 SQLite 仓储。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 连接与建表 ----

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        # 注意：不使用 executescript，因为它会隐式提交并关闭当前事务。
        statements = (
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value BLOB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS games (
              platform_id TEXT NOT NULL,
              group_openid TEXT NOT NULL,
              game_uuid TEXT NOT NULL,
              status TEXT NOT NULL,
              snapshot_json TEXT NOT NULL,
              updated_at INTEGER NOT NULL,
              PRIMARY KEY (platform_id, group_openid)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS processed_messages (
              platform_id TEXT NOT NULL,
              group_openid TEXT NOT NULL,
              message_id TEXT NOT NULL,
              result_json TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              PRIMARY KEY (platform_id, group_openid, message_id)
            )
            """,
        )
        with self.transaction() as conn:
            for statement in statements:
                conn.execute(statement)
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (META_SCHEMA_VERSION,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    (META_SCHEMA_VERSION, str(SCHEMA_VERSION)),
                )
            elif str(row["value"]) != str(SCHEMA_VERSION):
                raise RepositoryError(
                    f"数据库 schema 版本不匹配：{row['value']} != {SCHEMA_VERSION}"
                )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """开启一个立即写事务，异常时回滚。"""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover - 回滚失败时保留原异常
                pass
            raise
        finally:
            conn.close()

    # ---- 对局快照 ----

    def load_snapshot(
        self,
        conn: sqlite3.Connection,
        platform_id: str,
        group_openid: str,
    ) -> GameSnapshot | None:
        row = conn.execute(
            "SELECT snapshot_json FROM games WHERE platform_id = ? AND group_openid = ?",
            (platform_id, group_openid),
        ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["snapshot_json"])
            return GameSnapshot.from_dict(data)
        except (json.JSONDecodeError, SnapshotError, KeyError, TypeError) as exc:
            raise RepositoryError(f"快照损坏，无法反序列化：{exc}") from exc

    def store_snapshot(self, conn: sqlite3.Connection, snapshot: GameSnapshot) -> None:
        payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, separators=(",", ":"))
        conn.execute(
            """
            INSERT INTO games (platform_id, group_openid, game_uuid, status, snapshot_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform_id, group_openid) DO UPDATE SET
              game_uuid = excluded.game_uuid,
              status = excluded.status,
              snapshot_json = excluded.snapshot_json,
              updated_at = excluded.updated_at
            """,
            (
                snapshot.platform_id,
                snapshot.group_openid,
                snapshot.game_uuid,
                snapshot.phase.value,
                payload,
                int(time.time()),
            ),
        )

    def delete_snapshot(
        self,
        conn: sqlite3.Connection,
        platform_id: str,
        group_openid: str,
    ) -> None:
        conn.execute(
            "DELETE FROM games WHERE platform_id = ? AND group_openid = ?",
            (platform_id, group_openid),
        )

    def load(
        self,
        platform_id: str,
        group_openid: str,
    ) -> GameSnapshot | None:
        """便捷读取：自建只读连接，供测试与非事务调用方使用。"""
        conn = self.connect()
        try:
            return self.load_snapshot(conn, platform_id, group_openid)
        finally:
            conn.close()

    def save(self, snapshot: GameSnapshot) -> None:
        """便捷写入：自建事务。"""
        with self.transaction() as conn:
            self.store_snapshot(conn, snapshot)

    # ---- 幂等结果 ----

    def load_processed(
        self,
        conn: sqlite3.Connection,
        platform_id: str,
        group_openid: str,
        message_id: str,
    ) -> dict | None:
        if not message_id:
            return None
        row = conn.execute(
            """
            SELECT result_json FROM processed_messages
            WHERE platform_id = ? AND group_openid = ? AND message_id = ?
            """,
            (platform_id, group_openid, message_id),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["result_json"])
        except json.JSONDecodeError as exc:  # pragma: no cover - 数据损坏
            raise RepositoryError(f"消息结果损坏：{exc}") from exc

    def store_processed(
        self,
        conn: sqlite3.Connection,
        platform_id: str,
        group_openid: str,
        message_id: str,
        result: dict,
    ) -> None:
        if not message_id:
            return
        conn.execute(
            """
            INSERT INTO processed_messages
              (platform_id, group_openid, message_id, result_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (platform_id, group_openid, message_id) DO NOTHING
            """,
            (
                platform_id,
                group_openid,
                message_id,
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                int(time.time()),
            ),
        )

    def purge_processed(
        self,
        conn: sqlite3.Connection,
        platform_id: str,
        group_openid: str,
    ) -> None:
        conn.execute(
            "DELETE FROM processed_messages WHERE platform_id = ? AND group_openid = ?",
            (platform_id, group_openid),
        )
