"""
StudySensei Database Layer — SQLite-backed session and time-series persistence.

Architecture:
- Repository-style API: create_session, end_session, insert_time_series_point, insert_behavior_pattern.
- Single SQLite file (studysensei.db) in app directory; persists across restarts.
- Batch-friendly: callers control write frequency; we use parameterized writes and pragmas for performance.
- Thread-safe: one connection per process; serialized writes via connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional

# Default DB path: same directory as this module, then project root fallback
_DEFAULT_DB_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("STUDYSENSEI_DB_PATH", str(_DEFAULT_DB_DIR / "studysensei.db"))


class DatabaseManager:
    """
    Manages SQLite persistence for sessions, time-series points, and behavior patterns.
    All data persists between app restarts.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._path = db_path or DB_PATH
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def initialize(self) -> None:
        """Create tables and indexes if they do not exist. Idempotent."""
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Create a new study session. Returns session_id (integer).
        """
        meta_json = json.dumps(metadata or {})
        cur = self._conn().execute(
            "INSERT INTO sessions (metadata_json, started_at) VALUES (?, strftime('%s', 'now'))",
            (meta_json,),
        )
        self._conn().commit()
        return cur.lastrowid

    def end_session(self, session_id: int, session_stats: Dict[str, Any]) -> None:
        """
        End a session and store aggregate stats.
        session_stats: total_duration, avg_focus_score, avg_posture_score, total_blinks, total_slouch_alerts.
        """
        duration = session_stats.get("total_duration", 0.0)
        avg_focus = session_stats.get("avg_focus_score", 0.0)
        avg_posture = session_stats.get("avg_posture_score", 0.0)
        total_blinks = session_stats.get("total_blinks", 0)
        total_slouch = session_stats.get("total_slouch_alerts", 0)
        self._conn().execute(
            """
            UPDATE sessions
            SET ended_at = strftime('%s', 'now'),
                total_duration_sec = ?, avg_focus_score = ?, avg_posture_score = ?,
                total_blinks = ?, total_slouch_alerts = ?
            WHERE id = ?
            """,
            (duration, avg_focus, avg_posture, total_blinks, total_slouch, session_id),
        )
        self._conn().commit()

    def insert_time_series_point(
        self,
        session_id: int,
        timestamp: float,
        payload: Dict[str, Any],
    ) -> None:
        """
        Insert a single time-series point for the given session.
        payload: focus_score, posture_score, gaze_confidence, blink_detected, slouching, text_neck, fps.
        """
        self._conn().execute(
            """
            INSERT INTO time_series (session_id, ts, focus_score, posture_score, gaze_confidence,
                                    blink_detected, slouching, text_neck, fps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                payload.get("focus_score"),
                payload.get("posture_score"),
                payload.get("gaze_confidence"),
                1 if payload.get("blink_detected") else 0,
                1 if payload.get("slouching") else 0,
                1 if payload.get("text_neck") else 0,
                payload.get("fps"),
            ),
        )
        self._conn().commit()

    def insert_behavior_pattern(
        self,
        session_id: int,
        pattern_type: str,
        start_time: float,
        end_time: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a detected behavior pattern (e.g. prolonged_slouch, focus_drop)."""
        meta_json = json.dumps(metadata or {})
        self._conn().execute(
            """
            INSERT INTO behavior_patterns (session_id, pattern_type, start_time, end_time, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, pattern_type, start_time, end_time, meta_json),
        )
        self._conn().commit()

    def get_recent_sessions(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Return recent sessions for analytics/UI. Not used by real-time loop."""
        cur = self._conn().execute(
            """
            SELECT id, metadata_json, started_at, ended_at, total_duration_sec,
                   avg_focus_score, avg_posture_score, total_blinks, total_slouch_alerts
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "metadata": json.loads(r["metadata_json"] or "{}"),
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "total_duration_sec": r["total_duration_sec"],
                "avg_focus_score": r["avg_focus_score"],
                "avg_posture_score": r["avg_posture_score"],
                "total_blinks": r["total_blinks"],
                "total_slouch_alerts": r["total_slouch_alerts"],
            })
        return out


_SCHEMA = """
-- Sessions: one row per study session
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_json TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    total_duration_sec REAL,
    avg_focus_score REAL,
    avg_posture_score REAL,
    total_blinks INTEGER,
    total_slouch_alerts INTEGER
);

-- Time-series: high-frequency points per session (batch every ~2s in app)
CREATE TABLE IF NOT EXISTS time_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    focus_score REAL,
    posture_score REAL,
    gaze_confidence REAL,
    blink_detected INTEGER,
    slouching INTEGER,
    text_neck INTEGER,
    fps REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_time_series_session_ts ON time_series(session_id, ts);

-- Behavior patterns: detected events (slouch, focus drop, etc.)
CREATE TABLE IF NOT EXISTS behavior_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    pattern_type TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_behavior_session ON behavior_patterns(session_id);

-- Performance pragmas
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;
"""
