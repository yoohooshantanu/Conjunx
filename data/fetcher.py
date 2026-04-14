"""
Space-Track data fetcher with SQLite caching.

Handles authentication, CDM/TLE/SATCAT fetching, and time-based cache
invalidation.  Never makes a network request if valid cached data exists.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.space-track.org"
LOGIN_URL = f"{BASE_URL}/ajaxauth/login"

CDM_URL = (
    f"{BASE_URL}/basicspacedata/query/class/cdm_public"
    "/EMERGENCY_REPORTABLE/Y/TCA/%3Enow/orderby/PC%20desc/limit/50"
    "/format/json/emptyresult/show"
)

GP_URL_TEMPLATE = (
    f"{BASE_URL}/basicspacedata/query/class/gp"
    "/NORAD_CAT_ID/{{ids}}/decay_date/null-val"
    "/epoch/%3Enow-10/orderby/EPOCH%20desc"
    "/format/json/emptyresult/show"
)

SATCAT_URL_TEMPLATE = (
    f"{BASE_URL}/basicspacedata/query/class/satcat"
    "/NORAD_CAT_ID/{{ids}}"
    "/format/json/emptyresult/show"
)

# Cache TTLs
CDM_CACHE_HOURS = 8
TLE_CACHE_HOURS = 1
SATCAT_CACHE_HOURS = 24

DB_PATH = Path(__file__).resolve().parent.parent / "cache.db"

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS cdm_cache (
    cdm_id     TEXT PRIMARY KEY,
    raw_json   TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tle_cache (
    norad_id   INTEGER PRIMARY KEY,
    line1      TEXT NOT NULL,
    line2      TEXT NOT NULL,
    epoch      TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS satcat_cache (
    norad_id    INTEGER PRIMARY KEY,
    object_name TEXT,
    object_type TEXT,
    rcs_size    TEXT,
    launch_date TEXT,
    country     TEXT,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint   TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    count      INTEGER DEFAULT 0,
    cache_hit  INTEGER DEFAULT 0
);
"""


def _init_db(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_CREATE_TABLES)
    return conn


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_fresh(fetched_at_iso: str, max_age_hours: float) -> bool:
    fetched = datetime.fromisoformat(fetched_at_iso)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched
    return age < timedelta(hours=max_age_hours)


def _log_fetch(conn: sqlite3.Connection, endpoint: str,
               count: int, cache_hit: bool) -> None:
    conn.execute(
        "INSERT INTO fetch_log (endpoint, fetched_at, count, cache_hit) "
        "VALUES (?, ?, ?, ?)",
        (endpoint, _utcnow_iso(), count, int(cache_hit)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Fetcher class
# ---------------------------------------------------------------------------

class SpaceTrackFetcher:
    """Authenticated Space-Track API client with SQLite caching."""

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        db_path: Path | str = DB_PATH,
    ):
        self.email = email or os.getenv("SPACETRACK_EMAIL", "")
        self.password = password or os.getenv("SPACETRACK_PASSWORD", "")
        self.db_path = Path(db_path)
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False

    # -- lifecycle -----------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
            )
            self._authenticated = False
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- auth ----------------------------------------------------------------

    async def _authenticate(self) -> None:
        if not self.email or not self.password:
            logger.warning("Space-Track credentials not configured — "
                           "network fetches will be skipped")
            return

        client = await self._get_client()
        resp = await client.post(
            LOGIN_URL,
            data={"identity": self.email, "password": self.password},
        )
        if resp.status_code == 200:
            self._authenticated = True
            logger.info("Space-Track authentication successful")
        else:
            logger.error("Space-Track auth failed: %s %s",
                         resp.status_code, resp.text[:200])
            self._authenticated = False

    async def _authed_get(self, url: str) -> Optional[list[dict]]:
        """GET with auto-reauthentication on 401."""
        if not self.email:
            return None

        client = await self._get_client()

        if not self._authenticated:
            await self._authenticate()
            if not self._authenticated:
                return None

        resp = await client.get(url)

        if resp.status_code == 401:
            logger.info("Session expired — reauthenticating")
            await self._authenticate()
            if not self._authenticated:
                return None
            resp = await client.get(url)

        if resp.status_code != 200:
            logger.error("Space-Track GET %s → %s", url[:80], resp.status_code)
            return None

        data = resp.json()
        if isinstance(data, list):
            return data
        return []

    # -- CDMs ----------------------------------------------------------------

    async def fetch_cdms(self) -> list[dict]:
        """Fetch emergency-reportable CDMs, cached for 8 hours."""
        conn = _init_db(self.db_path)
        try:
            # Check cache freshness
            row = conn.execute(
                "SELECT fetched_at FROM cdm_cache ORDER BY fetched_at DESC LIMIT 1"
            ).fetchone()

            if row and _is_fresh(row["fetched_at"], CDM_CACHE_HOURS):
                rows = conn.execute("SELECT raw_json FROM cdm_cache").fetchall()
                cdms = [json.loads(r["raw_json"]) for r in rows]
                logger.info("CDM cache hit — %d records", len(cdms))
                _log_fetch(conn, "cdm", len(cdms), cache_hit=True)
                return cdms

            # Fetch from network
            logger.info("Fetching CDMs from Space-Track…")
            data = await self._authed_get(CDM_URL)
            if data is None:
                # Return stale cache if available
                rows = conn.execute("SELECT raw_json FROM cdm_cache").fetchall()
                return [json.loads(r["raw_json"]) for r in rows]

            now = _utcnow_iso()
            conn.execute("DELETE FROM cdm_cache")
            for cdm in data:
                cdm_id = cdm.get("CDM_ID", cdm.get("MESSAGE_ID", ""))
                conn.execute(
                    "INSERT OR REPLACE INTO cdm_cache (cdm_id, raw_json, fetched_at) "
                    "VALUES (?, ?, ?)",
                    (str(cdm_id), json.dumps(cdm), now),
                )
            conn.commit()
            logger.info("Cached %d CDMs at %s", len(data), now)
            _log_fetch(conn, "cdm", len(data), cache_hit=False)
            return data

        finally:
            conn.close()

    # -- TLEs ----------------------------------------------------------------

    async def fetch_tles(self, norad_ids: list[int]) -> list[dict]:
        """Fetch GP (TLE) data for given NORAD IDs, cached for 1 hour."""
        if not norad_ids:
            return []

        conn = _init_db(self.db_path)
        try:
            results = []
            ids_to_fetch = []

            for nid in norad_ids:
                row = conn.execute(
                    "SELECT * FROM tle_cache WHERE norad_id = ?", (nid,)
                ).fetchone()
                if row and _is_fresh(row["fetched_at"], TLE_CACHE_HOURS):
                    results.append({
                        "NORAD_CAT_ID": str(nid),
                        "TLE_LINE1": row["line1"],
                        "TLE_LINE2": row["line2"],
                        "EPOCH": row["epoch"],
                    })
                else:
                    ids_to_fetch.append(nid)

            if ids_to_fetch:
                ids_str = ",".join(str(i) for i in ids_to_fetch)
                url = GP_URL_TEMPLATE.replace("{{ids}}", ids_str)
                logger.info("Fetching TLEs for NORAD IDs: %s", ids_str)
                data = await self._authed_get(url)

                if data:
                    now = _utcnow_iso()
                    for gp in data:
                        nid = int(gp.get("NORAD_CAT_ID", 0))
                        line1 = gp.get("TLE_LINE1", "")
                        line2 = gp.get("TLE_LINE2", "")
                        epoch = gp.get("EPOCH", "")
                        conn.execute(
                            "INSERT OR REPLACE INTO tle_cache "
                            "(norad_id, line1, line2, epoch, fetched_at) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (nid, line1, line2, epoch, now),
                        )
                        results.append({
                            "NORAD_CAT_ID": str(nid),
                            "TLE_LINE1": line1,
                            "TLE_LINE2": line2,
                            "EPOCH": epoch,
                        })
                    conn.commit()
                    _log_fetch(conn, "tle", len(data), cache_hit=False)
                else:
                    # Return whatever was in stale cache
                    for nid in ids_to_fetch:
                        row = conn.execute(
                            "SELECT * FROM tle_cache WHERE norad_id = ?", (nid,)
                        ).fetchone()
                        if row:
                            results.append({
                                "NORAD_CAT_ID": str(nid),
                                "TLE_LINE1": row["line1"],
                                "TLE_LINE2": row["line2"],
                                "EPOCH": row["epoch"],
                            })
            else:
                _log_fetch(conn, "tle", len(results), cache_hit=True)

            return results
        finally:
            conn.close()

    # -- SATCAT --------------------------------------------------------------

    async def fetch_satcat(self, norad_ids: list[int]) -> list[dict]:
        """Fetch SATCAT metadata, cached for 24 hours."""
        if not norad_ids:
            return []

        conn = _init_db(self.db_path)
        try:
            results = []
            ids_to_fetch = []

            for nid in norad_ids:
                row = conn.execute(
                    "SELECT * FROM satcat_cache WHERE norad_id = ?", (nid,)
                ).fetchone()
                if row and _is_fresh(row["fetched_at"], SATCAT_CACHE_HOURS):
                    results.append({
                        "NORAD_CAT_ID": str(nid),
                        "OBJECT_NAME": row["object_name"],
                        "OBJECT_TYPE": row["object_type"],
                        "RCS_SIZE": row["rcs_size"],
                        "LAUNCH": row["launch_date"],
                        "COUNTRY": row["country"],
                    })
                else:
                    ids_to_fetch.append(nid)

            if ids_to_fetch:
                ids_str = ",".join(str(i) for i in ids_to_fetch)
                url = SATCAT_URL_TEMPLATE.replace("{{ids}}", ids_str)
                logger.info("Fetching SATCAT for NORAD IDs: %s", ids_str)
                data = await self._authed_get(url)

                if data:
                    now = _utcnow_iso()
                    for sat in data:
                        nid = int(sat.get("NORAD_CAT_ID", 0))
                        conn.execute(
                            "INSERT OR REPLACE INTO satcat_cache "
                            "(norad_id, object_name, object_type, rcs_size, "
                            " launch_date, country, fetched_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                nid,
                                sat.get("OBJECT_NAME", ""),
                                sat.get("OBJECT_TYPE", ""),
                                sat.get("RCS_SIZE", ""),
                                sat.get("LAUNCH", ""),
                                sat.get("COUNTRY", ""),
                                now,
                            ),
                        )
                        results.append(sat)
                    conn.commit()
                    _log_fetch(conn, "satcat", len(data), cache_hit=False)
                else:
                    for nid in ids_to_fetch:
                        row = conn.execute(
                            "SELECT * FROM satcat_cache WHERE norad_id = ?",
                            (nid,),
                        ).fetchone()
                        if row:
                            results.append({
                                "NORAD_CAT_ID": str(nid),
                                "OBJECT_NAME": row["object_name"],
                                "OBJECT_TYPE": row["object_type"],
                                "RCS_SIZE": row["rcs_size"],
                                "LAUNCH": row["launch_date"],
                                "COUNTRY": row["country"],
                            })
            else:
                _log_fetch(conn, "satcat", len(results), cache_hit=True)

            return results
        finally:
            conn.close()

    # -- cache stats ---------------------------------------------------------

    def get_cache_stats(self) -> dict:
        """Return cache hit/miss stats and last fetch timestamps."""
        conn = _init_db(self.db_path)
        try:
            stats = {}
            for endpoint in ("cdm", "tle", "satcat"):
                rows = conn.execute(
                    "SELECT fetched_at, cache_hit FROM fetch_log "
                    "WHERE endpoint = ? ORDER BY fetched_at DESC LIMIT 20",
                    (endpoint,),
                ).fetchall()
                total = len(rows)
                hits = sum(1 for r in rows if r["cache_hit"])
                last = rows[0]["fetched_at"] if rows else None
                stats[endpoint] = {
                    "last_fetch": last,
                    "recent_requests": total,
                    "cache_hits": hits,
                    "hit_rate": f"{hits / total * 100:.0f}%" if total else "N/A",
                }
            return stats
        finally:
            conn.close()

    # -- load single CDM from cache ------------------------------------------

    def get_cached_cdm(self, cdm_id: str) -> Optional[dict]:
        """Load a single CDM from the cache by ID."""
        conn = _init_db(self.db_path)
        try:
            row = conn.execute(
                "SELECT raw_json FROM cdm_cache WHERE cdm_id = ?", (cdm_id,)
            ).fetchone()
            if row:
                return json.loads(row["raw_json"])
            return None
        finally:
            conn.close()
