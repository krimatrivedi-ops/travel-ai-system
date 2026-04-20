"""
Durable SQLite storage for generated itineraries (Epic 2).

Uses stdlib sqlite3 only. Path from DATA_DIR + itineraries.sqlite3 or TRAVEL_AI_DB.
See docs/persistence.md.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.itinerary_schema import parse_trip_duration_days
from core.preference_schema import trip_anchor_date

logger = logging.getLogger(__name__)

_DB_PATH_OVERRIDE: Optional[str] = None


def set_database_path_for_tests(path: Optional[str]) -> None:
    """Point the store at a file or ':memory:' (tests only)."""
    global _DB_PATH_OVERRIDE
    _DB_PATH_OVERRIDE = path


def _database_path() -> str:
    if _DB_PATH_OVERRIDE is not None:
        return _DB_PATH_OVERRIDE
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.environ.get("TRAVEL_AI_DB", os.path.join(data_dir, "itineraries.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _database_path()
    if path != ":memory:":
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_itineraries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            destination TEXT NOT NULL,
            trip_date_start TEXT,
            trip_date_end TEXT,
            persona_snapshot TEXT NOT NULL,
            itinerary_bundle TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT,
            is_read INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()


def save_notification(ntype: str, message: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """Persist a notification."""
    nid = str(uuid.uuid4())
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None

    conn = _connect()
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO notifications (id, created_at, type, message, payload, is_read)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (nid, created, ntype, message, payload_json),
        )
        conn.commit()
    finally:
        conn.close()
    return nid


def list_notifications() -> List[Dict[str, Any]]:
    """List all notifications, newest first."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT id, created_at, type, message, payload, is_read FROM notifications ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    out = []
    for row in rows:
        out.append({
            "id": row[0],
            "created_at": row[1],
            "type": row[2],
            "message": row[3],
            "payload": json.loads(row[4]) if row[4] else None,
            "is_read": bool(row[5])
        })
    return out


def mark_notification_as_read(nid: str) -> None:
    """Mark a notification as read."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (nid,))
        conn.commit()
    finally:
        conn.close()


def _derive_trip_dates(persona: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    try:
        start = trip_anchor_date(persona)
        ndays = parse_trip_duration_days(str(persona.get("trip_duration", "")))
        ndays = max(1, ndays)
        end = start + timedelta(days=ndays - 1)
        return start.isoformat(), end.isoformat()
    except Exception:
        return None, None


def save_generated_itinerary(persona: Dict[str, Any], bundle: Dict[str, Any]) -> str:
    """
    Persist a successful generation. Returns new UUID id.
    Stores full bundle JSON (weather/pricing snapshots) and normalized persona snapshot.
    """
    sid = str(uuid.uuid4())
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    dest = str(persona.get("destination") or "").strip() or "unknown"
    t_start, t_end = _derive_trip_dates(persona)
    persona_json = json.dumps(persona, ensure_ascii=False, sort_keys=False)
    bundle_json = json.dumps(bundle, ensure_ascii=False, sort_keys=False)

    conn = _connect()
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO saved_itineraries (
                id, created_at, destination, trip_date_start, trip_date_end,
                persona_snapshot, itinerary_bundle
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, created, dest, t_start, t_end, persona_json, bundle_json),
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def _summary_title_from_bundle_json(
    bundle_raw: str,
    destination: str,
    trip_start: Optional[str],
    trip_end: Optional[str],
) -> str:
    """
    List row title: prefer first day theme from stored bundle; else destination + date range.
    """
    try:
        b = json.loads(bundle_raw)
        days = b.get("days") if isinstance(b, dict) else None
        if isinstance(days, list) and days and isinstance(days[0], dict):
            t = str(days[0].get("title") or "").strip()
            if t:
                return t
    except json.JSONDecodeError:
        pass
    dest = (destination or "").strip() or "Trip"
    if trip_start and trip_end:
        return f"{dest} · {trip_start} – {trip_end}"
    return dest


def list_saved_itinerary_summaries() -> List[Dict[str, Any]]:
    """
    Newest first. Parses itinerary_bundle JSON only to derive display title (POC-scale).
    """
    conn = _connect()
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT id, created_at, destination, trip_date_start, trip_date_end, itinerary_bundle
            FROM saved_itineraries
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    print("rows-----------", rows)
    for row in rows:
        bid, created, dest, ts, te, bundle_raw = row
        title = _summary_title_from_bundle_json(bundle_raw, dest, ts, te)
        out.append(
            {
                "id": bid,
                "title": title,
                "destination": dest,
                "trip_date_start": ts,
                "trip_date_end": te,
                "created_at": created,
            }
        )
    return out


def get_saved_itinerary(saved_id: str) -> Optional[Dict[str, Any]]:
    """Load one saved record; returns parsed JSON fields or None."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT id, created_at, destination, trip_date_start, trip_date_end, "
            "persona_snapshot, itinerary_bundle FROM saved_itineraries WHERE id = ?",
            (saved_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        persona_snapshot = json.loads(row[5])
        itinerary_bundle = json.loads(row[6])
    except json.JSONDecodeError as e:
        logger.warning("Corrupt JSON in saved_itineraries row %s: %s", saved_id, e)
        return None
    return {
        "id": row[0],
        "created_at": row[1],
        "destination": row[2],
        "trip_date_start": row[3],
        "trip_date_end": row[4],
        "persona_snapshot": persona_snapshot,
        "itinerary_bundle": itinerary_bundle,
    }


def update_saved_itinerary_after_replan(
    saved_id: str, persona: Dict[str, Any], bundle: Dict[str, Any]
) -> None:
    """
    Replace persona_snapshot, itinerary_bundle, and derived list columns for an existing row.
    Used when chat regeneration completes for a trip opened via saved_itinerary_id (Story 3.2).
    """
    dest = str(persona.get("destination") or "").strip() or "unknown"
    t_start, t_end = _derive_trip_dates(persona)
    persona_json = json.dumps(persona, ensure_ascii=False, sort_keys=False)
    bundle_json = json.dumps(bundle, ensure_ascii=False, sort_keys=False)
    conn = _connect()
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            UPDATE saved_itineraries SET
                destination = ?,
                trip_date_start = ?,
                trip_date_end = ?,
                persona_snapshot = ?,
                itinerary_bundle = ?
            WHERE id = ?
            """,
            (dest, t_start, t_end, persona_json, bundle_json, saved_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("saved itinerary not found")
    finally:
        conn.close()


def update_saved_itinerary_bundle(saved_id: str, bundle: Dict[str, Any]) -> None:
    """Replace stored itinerary_bundle JSON for a saved row. Raises ValueError if id missing."""
    payload = json.dumps(bundle, ensure_ascii=False)
    conn = _connect()
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            "UPDATE saved_itineraries SET itinerary_bundle = ? WHERE id = ?",
            (payload, saved_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("saved itinerary not found")
    finally:
        conn.close()


def get_all_saved_itineraries() -> List[Dict[str, Any]]:
    """Fetch all records with full bundle and persona snapshots."""
    conn = _connect()
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT id, created_at, destination, trip_date_start, trip_date_end, 
                   persona_snapshot, itinerary_bundle 
            FROM saved_itineraries
            """
        ).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            persona = json.loads(row[5])
            bundle = json.loads(row[6])
            out.append({
                "id": row[0],
                "created_at": row[1],
                "destination": row[2],
                "trip_date_start": row[3],
                "trip_date_end": row[4],
                "persona_snapshot": persona,
                "itinerary_bundle": bundle,
            })
        except json.JSONDecodeError:
            continue
    return out


def init_store() -> None:
    """Create schema on startup (idempotent)."""
    conn = _connect()
    try:
        _ensure_schema(conn)
    finally:
        conn.close()
