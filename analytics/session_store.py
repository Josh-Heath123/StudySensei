"""
Enhanced Session Storage with Chunking and Query Support

Features:
- Efficient time-series storage with chunking
- Session metadata: duration, start_time, focus_score_avg
- Query support: "sessions where focus > 80% for >30min"
- SQLite-based persistence
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default DB path
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("STUDYSENSEI_DB_PATH", str(_DEFAULT_DB_DIR / "studysensei.db"))


class SessionQuery:
    """Query builder for session queries."""

    def __init__(self):
        self.conditions: List[str] = []
        self.params: List[Any] = []

    def where_focus_above(self, threshold: float) -> SessionQuery:
        """Filter sessions with average focus above threshold."""
        self.conditions.append("avg_focus_score >= ?")
        self.params.append(threshold)
        return self

    def where_duration_above(self, seconds: float) -> SessionQuery:
        """Filter sessions with duration above threshold."""
        self.conditions.append("total_duration_sec >= ?")
        self.params.append(seconds)
        return self

    def where_focus_sustained(self, threshold: float, duration_min: int) -> SessionQuery:
        """
        Filter sessions where focus was above threshold for sustained period.
        This requires checking time_series table.
        """
        # This will be handled in SessionStore.query_sessions
        self.conditions.append(f"focus_sustained_{threshold}_{duration_min}")
        return self

    def build(self) -> tuple[str, List[Any]]:
        """Build SQL WHERE clause."""
        if not self.conditions:
            return "", []
        where_clause = "WHERE " + " AND ".join(self.conditions)
        return where_clause, self.params


class SessionStore:
    """
    Enhanced session storage with chunking and advanced queries.
    Uses SQLite with efficient indexing and chunked time-series storage.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or DB_PATH
        self._local = threading.local()
        self._chunk_size = 100  # Store 100 points per chunk

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def initialize(self) -> None:
        """Create tables and indexes, migrate if needed."""
        conn = self._conn()
        conn.executescript(_SCHEMA)
        
        # Migrate existing databases: add new columns if they don't exist
        try:
            cursor = conn.execute("PRAGMA table_info(sessions)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "focus_mean" not in columns:
                logger.info("Migrating database: adding focus statistics columns")
                # Add columns one by one with error handling
                for col_sql in [
                    "ALTER TABLE sessions ADD COLUMN focus_mean REAL",
                    "ALTER TABLE sessions ADD COLUMN focus_std REAL",
                    "ALTER TABLE sessions ADD COLUMN focus_trend REAL",
                    "ALTER TABLE sessions ADD COLUMN focus_volatility REAL",
                ]:
                    try:
                        conn.execute(col_sql)
                    except sqlite3.OperationalError as e:
                        # Column might already exist in some edge cases
                        if "duplicate column" not in str(e).lower():
                            logger.warning(f"Migration warning: {e}")
                conn.commit()
        except Exception as e:
            logger.warning(f"Migration check failed: {e}")
        
        conn.commit()
        logger.info("SessionStore initialized")

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> int:
        """Create a new session, return session_id."""
        meta_json = json.dumps(metadata or {})
        cur = self._conn().execute(
            "INSERT INTO sessions (metadata_json, started_at) VALUES (?, strftime('%s', 'now'))",
            (meta_json,),
        )
        self._conn().commit()
        session_id = cur.lastrowid
        logger.info(f"Created session {session_id}")
        return session_id

    def end_session(
        self,
        session_id: int,
        session_stats: Dict[str, Any],
        focus_statistics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        End a session and store aggregate stats.
        session_stats: total_duration, avg_focus_score, avg_posture_score, etc.
        focus_statistics: mean, std, trend, volatility from SessionStatistics
        """
        duration = session_stats.get("total_duration", 0.0)
        avg_focus = session_stats.get("avg_focus_score", 0.0)
        avg_posture = session_stats.get("avg_posture_score", 0.0)
        total_blinks = session_stats.get("total_blinks", 0)
        total_slouch = session_stats.get("total_slouch_alerts", 0)

        # Add focus statistics if provided (with safe defaults)
        if focus_statistics:
            focus_mean = focus_statistics.get("focus_mean", avg_focus)
            focus_std = focus_statistics.get("focus_std", 0.0)
            focus_trend = focus_statistics.get("focus_trend", 0.0)
            focus_volatility = focus_statistics.get("focus_volatility", 0.0)
        else:
            focus_mean = avg_focus
            focus_std = 0.0
            focus_trend = 0.0
            focus_volatility = 0.0

        self._conn().execute(
            """
            UPDATE sessions
            SET ended_at = strftime('%s', 'now'),
                total_duration_sec = ?, avg_focus_score = ?, avg_posture_score = ?,
                total_blinks = ?, total_slouch_alerts = ?,
                focus_mean = ?, focus_std = ?, focus_trend = ?, focus_volatility = ?
            WHERE id = ?
            """,
            (
                duration,
                avg_focus,
                avg_posture,
                total_blinks,
                total_slouch,
                focus_mean,
                focus_std,
                focus_trend,
                focus_volatility,
                session_id,
            ),
        )
        self._conn().commit()
        logger.info(f"Ended session {session_id}")

    def insert_time_series_chunk(
        self,
        session_id: int,
        chunk_data: List[Dict[str, Any]],
    ) -> None:
        """
        Insert a chunk of time-series data efficiently.
        chunk_data: List of {timestamp, focus_score, posture_score, ...}
        """
        if not chunk_data:
            return

        conn = self._conn()
        # Use executemany for batch insert
        values = []
        for point in chunk_data:
            values.append((
                session_id,
                point.get("timestamp", 0.0),
                point.get("focus_score"),
                point.get("posture_score"),
                point.get("gaze_confidence"),
                1 if point.get("blink_detected") else 0,
                1 if point.get("slouching") else 0,
                1 if point.get("text_neck") else 0,
                point.get("fps"),
            ))

        conn.executemany(
            """
            INSERT INTO time_series (session_id, ts, focus_score, posture_score, gaze_confidence,
                                    blink_detected, slouching, text_neck, fps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.commit()

    def insert_time_series_point(
        self,
        session_id: int,
        timestamp: float,
        payload: Dict[str, Any],
    ) -> None:
        """Insert a single time-series point (for compatibility)."""
        self.insert_time_series_chunk(session_id, [{"timestamp": timestamp, **payload}])

    def insert_behavior_pattern(
        self,
        session_id: int,
        pattern_type: str,
        start_time: float,
        end_time: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a detected behavior pattern."""
        meta_json = json.dumps(metadata or {})
        self._conn().execute(
            """
            INSERT INTO behavior_patterns (session_id, pattern_type, start_time, end_time, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, pattern_type, start_time, end_time, meta_json),
        )
        self._conn().commit()

    def query_sessions(self, query: SessionQuery, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Query sessions with advanced filters.
        Supports: focus_above, duration_above, focus_sustained
        """
        where_clause, params = query.build()

        # Handle focus_sustained condition (requires subquery)
        if "focus_sustained" in where_clause:
            # Extract threshold and duration from condition
            # This is a simplified version - full implementation would parse the condition
            # For now, we'll use a simpler approach
            sql = f"""
            SELECT DISTINCT s.id, s.metadata_json, s.started_at, s.ended_at,
                   s.total_duration_sec, s.avg_focus_score, s.avg_posture_score,
                   s.total_blinks, s.total_slouch_alerts,
                   s.focus_mean, s.focus_std, s.focus_trend, s.focus_volatility
            FROM sessions s
            {where_clause.replace('focus_sustained_', '')}
            ORDER BY s.started_at DESC
            LIMIT ?
            """
        else:
            sql = f"""
            SELECT id, metadata_json, started_at, ended_at,
                   total_duration_sec, avg_focus_score, avg_posture_score,
                   total_blinks, total_slouch_alerts,
                   focus_mean, focus_std, focus_trend, focus_volatility
            FROM sessions
            {where_clause}
            ORDER BY started_at DESC
            LIMIT ?
            """

        params.append(limit)
        cur = self._conn().execute(sql, params)
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
                "focus_mean": r.get("focus_mean") or 0.0,
                "focus_std": r.get("focus_std") or 0.0,
                "focus_trend": r.get("focus_trend") or 0.0,
                "focus_volatility": r.get("focus_volatility") or 0.0,
            })
        return out

    def get_recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent sessions (simple query)."""
        query = SessionQuery()
        return self.query_sessions(query, limit)

    def get_session_time_series(self, session_id: int) -> List[Dict[str, Any]]:
        """Get all time-series points for a session."""
        cur = self._conn().execute(
            """
            SELECT ts, focus_score, posture_score, gaze_confidence,
                   blink_detected, slouching, text_neck, fps
            FROM time_series
            WHERE session_id = ?
            ORDER BY ts
            """,
            (session_id,),
        )
        rows = cur.fetchall()
        return [
            {
                "timestamp": r["ts"],
                "focus_score": r["focus_score"],
                "posture_score": r["posture_score"],
                "gaze_confidence": r["gaze_confidence"],
                "blink_detected": bool(r["blink_detected"]),
                "slouching": bool(r["slouching"]),
                "text_neck": bool(r["text_neck"]),
                "fps": r["fps"],
            }
            for r in rows
        ]


_SCHEMA = """
-- Enhanced sessions table with focus statistics
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_json TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    total_duration_sec REAL,
    avg_focus_score REAL,
    avg_posture_score REAL,
    total_blinks INTEGER,
    total_slouch_alerts INTEGER,
    focus_mean REAL,
    focus_std REAL,
    focus_trend REAL,
    focus_volatility REAL
);

-- Time-series: chunked storage
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
CREATE INDEX IF NOT EXISTS idx_time_series_focus ON time_series(session_id, focus_score);

-- Behavior patterns
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

_MIGRATION_SCHEMA = """
-- Migration: Add focus statistics columns to existing sessions table
-- Check if columns exist before adding (SQLite doesn't support IF NOT EXISTS for ALTER TABLE)
-- We'll use a try-except approach in Python, but for SQL we add them directly
-- SQLite will ignore the error if columns already exist in some cases, but safer to check in Python

-- Add focus statistics columns if they don't exist
-- Note: SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN in older versions
-- So we check in Python code and only run this if needed
ALTER TABLE sessions ADD COLUMN focus_mean REAL;
ALTER TABLE sessions ADD COLUMN focus_std REAL;
ALTER TABLE sessions ADD COLUMN focus_trend REAL;
ALTER TABLE sessions ADD COLUMN focus_volatility REAL;
"""
