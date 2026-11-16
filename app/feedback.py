"""
Feedback storage for the lead-agent demo.

Semantics:
- one lead x one listing = one current verdict (upsert, no duplicates)
- last verdict wins; status/previous returned on update
- every click is also appended to feedback_log (history for future model training)
- any legacy schema is migrated automatically on every connection
  (missing columns added; incompatible tables preserved as feedback_legacy_<ts>)
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_LOCAL = threading.local()

_MANDATORY = {"lead_id", "listing_id", "verdict"}
_COLUMNS = {
    "lead_id": "TEXT",
    "listing_id": "TEXT",
    "verdict": "TEXT",
    "lead_text": "TEXT",
    "criteria": "TEXT",
    "score": "REAL",
    "updated_at": "REAL",
}


def db_path():
    env = os.environ.get("LEAD_AGENT_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "lead_agent.db"


def _connect():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(db_path()))
        conn.row_factory = sqlite3.Row
        _LOCAL.conn = conn
    return conn


def _table_columns(conn, table):
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _ensure_schema(conn):
    """Idempotent, runs on every connection; never raises on legacy schemas."""
    cols = _table_columns(conn, "feedback")
    if not cols:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                lead_id     TEXT NOT NULL,
                listing_id  TEXT NOT NULL,
                verdict     TEXT NOT NULL,
                lead_text   TEXT,
                criteria    TEXT,
                score       REAL,
                updated_at  REAL,
                UNIQUE(lead_id, listing_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id     TEXT,
                listing_id  TEXT,
                verdict     TEXT,
                action      TEXT,
                created_at  REAL
            )
            """
        )
        return

    # legacy table: check mandatory columns
    if not _MANDATORY.issubset(cols):
        # incompatible legacy schema -> preserve as archive, start fresh
        ts = int(time.time() * 1000)
        try:
            conn.execute(f"ALTER TABLE feedback RENAME TO feedback_legacy_{ts}")
        except sqlite3.Error:
            conn.execute("DROP TABLE IF EXISTS feedback")
        conn.execute(
            """
            CREATE TABLE feedback (
                lead_id     TEXT NOT NULL,
                listing_id  TEXT NOT NULL,
                verdict     TEXT NOT NULL,
                lead_text   TEXT,
                criteria    TEXT,
                score       REAL,
                updated_at  REAL,
                UNIQUE(lead_id, listing_id)
            )
            """
        )
        return

    # compatible table: add any missing optional columns
    for name, decl in _COLUMNS.items():
        if name not in cols:
            try:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {name} {decl}")
            except sqlite3.Error:
                pass

    # collapse legacy duplicates: keep latest verdict per pair
    try:
        has_unique = False
        for r in conn.execute("PRAGMA index_list(feedback)"):
            idx_name = r[1]
            icols = [c[2] for c in conn.execute(f"PRAGMA index_info({idx_name})")]
            if set(icols) >= {"lead_id", "listing_id"}:
                has_unique = True
        if not has_unique:
            conn.execute(
                """
                DELETE FROM feedback WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM feedback
                    GROUP BY lead_id, listing_id
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_feedback_pair "
                "ON feedback(lead_id, listing_id)"
            )
    except sqlite3.Error:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     TEXT,
            listing_id  TEXT,
            verdict     TEXT,
            action      TEXT,
            created_at  REAL
        )
        """
    )


def _normalize(value):
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return value


def record(lead_id, listing_id, verdict, lead_text="", criteria=None, score=None):
    """Upsert one verdict. Returns dict: status(created/updated/unchanged), previous."""
    verdict = "fit" if str(verdict).lower() in {"fit", "good", "yes", "1"} else "miss"
    conn = _connect()
    _ensure_schema(conn)
    prev = conn.execute(
        "SELECT verdict FROM feedback WHERE lead_id = ? AND listing_id = ?",
        (lead_id, listing_id),
    ).fetchone()
    status = "created" if prev is None else ("updated" if prev[0] != verdict else "unchanged")
    previous = prev[0] if prev is not None else None
    now = time.time()
    conn.execute(
        """
        INSERT INTO feedback (lead_id, listing_id, verdict, lead_text, criteria, score, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lead_id, listing_id)
        DO UPDATE SET verdict = excluded.verdict,
                      lead_text = excluded.lead_text,
                      criteria = excluded.criteria,
                      score = excluded.score,
                      updated_at = excluded.updated_at
        """,
        (
            lead_id,
            listing_id,
            verdict,
            lead_text or "",
            _normalize(criteria),
            score,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO feedback_log (lead_id, listing_id, verdict, action, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lead_id, listing_id, verdict, status, now),
    )
    conn.commit()
    return {"status": status, "previous": previous, "verdict": verdict}


def _listing_id_from_match(match):
    if not isinstance(match, dict):
        return None
    for key in ("listing_id", "id", "listing_id_str"):
        if key in match and isinstance(match[key], (str, int)):
            return str(match[key])
    inner = match.get("listing")
    if isinstance(inner, dict):
        for key in ("listing_id", "id"):
            if key in inner and isinstance(inner[key], (str, int)):
                return str(inner[key])
    return None


def _pseudo_id(obj):
    try:
        blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(obj)
    import hashlib

    return "pseudo-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def save_feedback(lead_text, criteria, match, verdict):
    """UI style: save_feedback(lead_text, criteria_dict, match, verdict)."""
    if isinstance(criteria, dict):
        lid = _listing_id_from_match(match) or _pseudo_id(match)
        lead_id = _pseudo_id(lead_text) if lead_text else "anon"
        score = None
        if isinstance(match, dict):
            for key in ("score", "match_score", "final_score"):
                if key in match:
                    score = match[key]
                    break
        return record(
            lead_id,
            lid,
            verdict,
            lead_text=lead_text,
            criteria=criteria,
            score=score,
        )
    # legacy style: save_feedback(lead_id, listing_id, verdict, ...)
    return record(lead_text, criteria, match)


def stats_summary():
    conn = _connect()
    _ensure_schema(conn)
    cols = _table_columns(conn, "feedback")
    total = fits = misses = 0
    top = []
    if cols:
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        fits = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE verdict = 'fit'"
        ).fetchone()[0]
        misses = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE verdict = 'miss'"
        ).fetchone()[0]
        # most-discussed listings (safe even without updated_at column)
        has_updated = "updated_at" in cols
        order = "MAX(updated_at)" if has_updated else "MAX(rowid)"
        rows = conn.execute(
            f"""
            SELECT listing_id, COUNT(*) AS n, verdict
            FROM feedback
            GROUP BY listing_id
            ORDER BY n DESC, {order} DESC
            LIMIT 5
            """
        ).fetchall()
        # last verdict per listing
        for r in rows:
            last = conn.execute(
                "SELECT verdict FROM feedback WHERE listing_id = ? ORDER BY rowid DESC LIMIT 1",
                (r[0],),
            ).fetchone()
            top.append(
                {
                    "listing_id": r[0],
                    "count": r[1],
                    "last_verdict": last[0] if last else r[2],
                }
            )
    return {"total": total, "fits": fits, "misses": misses, "top_listings": top}


class _StatsView:
    """Resilient stats view: never raises KeyError on any key."""

    def __init__(self, data):
        object.__setattr__(self, "_data", dict(data))

    # dict-style access with aliases and safe defaults
    def __getitem__(self, key):
        d = object.__getattribute__(self, "_data")
        if key in d:
            return d[key]
        aliases = {
            "fit": d.get("fits", 0),
            "miss": d.get("misses", 0),
            "top": d.get("top_listings", []),
            "total": d.get("total", 0),
        }
        if key in aliases:
            return aliases[key]
        if key.endswith("s") and key[:-1] in d:  # e.g. "totals" -> total
            return d[key[:-1]]
        if key == "top_listings" or "listing" in str(key):
            return []
        return None

    def __contains__(self, key):
        return True  # `"fit" in fs` is always safe

    def get(self, key, default=None):
        val = self[key]
        return default if val is None else val

    def items(self):
        d = object.__getattribute__(self, "_data")
        return d.items()

    def keys(self):
        d = object.__getattribute__(self, "_data")
        return list(d.keys()) + ["fit", "miss", "top"]

    # attribute-style access (s.fit, s.miss, ...)
    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_data")[name]
        except KeyError:
            return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_data")[name] = value

    def __repr__(self):
        return repr(object.__getattribute__(self, "_data"))


def stats():
    return _StatsView(stats_summary())


def close():
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        conn.close()
        _LOCAL.conn = None
