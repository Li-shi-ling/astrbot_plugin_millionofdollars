"""SQLite 仓储测试（设计文档 11.5）。"""

from __future__ import annotations

import sqlite3

import pytest
from game.models import (
    SCHEMA_VERSION,
    CharacterSlot,
    GameSnapshot,
    LootCard,
    Phase,
    Player,
    Role,
)
from game.repository import GameRepository, RepositoryError


def make_snapshot() -> GameSnapshot:
    snapshot = GameSnapshot(
        game_uuid="uuid-1",
        platform_id="platform-1",
        group_openid="group-1",
        phase=Phase.NEGOTIATION,
        round_number=2,
        leader_index=1,
    )
    player = Player(
        member_openid="user-a",
        display_name="小明",
        join_order=0,
        cash=7,
        threat_cards=1,
        action_generation=4,
        ready=True,
    )
    player.slots = [CharacterSlot(slot_id="user-a:0", role=Role.BRUTE, ante_total=1)]
    snapshot.players.append(player)
    snapshot.loot_deck = [LootCard("c0", 10, 1, Role.DRIVER)]
    snapshot.public_role_counts = {"brute": 1}
    snapshot.hidden_slot_id = "user-a:0"
    snapshot.negotiation_started_at = 1234.5
    return snapshot


@pytest.fixture()
def repo(tmp_path) -> GameRepository:
    repository = GameRepository(tmp_path / "data" / "game.sqlite3")
    repository.initialize()
    return repository


def test_initialize_creates_schema_and_records_version(repo: GameRepository) -> None:
    conn = repo.connect()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        version = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()["value"]
    finally:
        conn.close()

    assert {"meta", "games", "processed_messages"} <= tables
    assert str(version) == str(SCHEMA_VERSION)


def test_initialize_twice_is_idempotent(repo: GameRepository) -> None:
    repo.initialize()
    repo.initialize()


def test_snapshot_round_trip_keeps_every_field(repo: GameRepository) -> None:
    snapshot = make_snapshot()

    repo.save(snapshot)
    loaded = repo.load(snapshot.platform_id, snapshot.group_openid)

    assert loaded is not None
    assert loaded.to_dict() == snapshot.to_dict()


def test_load_missing_room_returns_none(repo: GameRepository) -> None:
    assert repo.load("platform-x", "group-x") is None


def test_processed_messages_are_idempotent(repo: GameRepository) -> None:
    with repo.transaction() as conn:
        assert repo.load_processed(conn, "p", "g", "m1") is None
        repo.store_processed(conn, "p", "g", "m1", {"text": "第一次"})
        repo.store_processed(conn, "p", "g", "m1", {"text": "第二次"})

    with repo.transaction() as conn:
        assert repo.load_processed(conn, "p", "g", "m1") == {"text": "第一次"}
        assert repo.load_processed(conn, "p", "g", "m2") is None


def test_transaction_rolls_back_on_error(repo: GameRepository) -> None:
    snapshot = make_snapshot()

    with pytest.raises(RuntimeError):
        with repo.transaction() as conn:
            repo.store_snapshot(conn, snapshot)
            raise RuntimeError("boom")

    assert repo.load(snapshot.platform_id, snapshot.group_openid) is None


def test_corrupted_snapshot_is_reported(repo: GameRepository) -> None:
    snapshot = make_snapshot()
    repo.save(snapshot)

    conn = repo.connect()
    try:
        conn.execute(
            "UPDATE games SET snapshot_json = ? WHERE group_openid = ?",
            ("{not json", snapshot.group_openid),
        )
    finally:
        conn.close()

    with pytest.raises(RepositoryError):
        repo.load(snapshot.platform_id, snapshot.group_openid)


def test_repository_rejects_foreign_schema_version(tmp_path) -> None:
    path = tmp_path / "version.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value BLOB NOT NULL)")
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', '999')"
    )
    conn.commit()
    conn.close()

    repo = GameRepository(path)
    with pytest.raises(RepositoryError):
        repo.initialize()
