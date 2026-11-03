"""Shared fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path

import pytest


@pytest.fixture
def murmur_log(tmp_path: Path) -> Callable[..., Path]:
    """Makes a database holding a log, with the table as Murmur 1.5.517 creates it."""

    def make(rows: Sequence[tuple[str, str]], server_id: int = 1) -> Path:
        path = tmp_path / "murmur.sqlite"
        with closing(sqlite3.connect(path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS `slog`(`server_id` INTEGER NOT NULL, "
                "`msg` TEXT, `msgtime` DATE)"
            )
            db.executemany(
                "INSERT INTO slog (server_id, msgtime, msg) VALUES (?, ?, ?)",
                [(server_id, time, message) for time, message in rows],
            )
            db.commit()
        return path

    return make
