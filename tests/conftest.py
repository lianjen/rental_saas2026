"""
Pytest shared fixtures - v1.0.0
避免測試連到真實資料庫，並提供共用範例資料。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import services.base_db as base_db


def _build_fake_pool() -> MagicMock:
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = None
    fake_cursor.fetchone.return_value = None
    fake_cursor.fetchall.return_value = []
    fake_cursor.rowcount = 0

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    fake_pool = MagicMock()
    fake_pool.get_connection.return_value = fake_conn
    fake_pool.return_connection.return_value = None
    return fake_pool


@pytest.fixture(autouse=True)
def mock_database(monkeypatch):
    """自動 mock DB 連線池，避免測試連到真實 PostgreSQL。"""
    fake_pool = _build_fake_pool()
    monkeypatch.setattr(base_db, "get_connection_pool", lambda: fake_pool)
    yield fake_pool


@pytest.fixture
def sample_electricity_readings():
    """電費計算測試用範例資料。"""
    return [
        {"room_number": "1A", "prev_reading": 100, "curr_reading": 150, "kwh": 50},
        {"room_number": "1B", "prev_reading": 200, "curr_reading": 280, "kwh": 80},
        {"room_number": "2A", "prev_reading": 300, "curr_reading": 360, "kwh": 60},
        {"room_number": "2B", "prev_reading": 400, "curr_reading": 470, "kwh": 70},
    ]
