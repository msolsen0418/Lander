import sqlite3
import json
import time
from contextlib import contextmanager
from config import DATABASE_PATH, VALUATION_CACHE_TTL

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    city TEXT,
    county TEXT,
    state TEXT DEFAULT 'FL',
    zip TEXT,
    auction_type TEXT,
    opening_bid REAL,
    sale_date TEXT,
    case_number TEXT,
    source_url TEXT,
    source TEXT,
    scraped_at REAL DEFAULT (unixepoch()),
    UNIQUE(case_number, source)
);

CREATE TABLE IF NOT EXISTS valuations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    estimated_value REAL,
    detail_url TEXT,
    raw_data TEXT,
    fetched_at REAL DEFAULT (unixepoch()),
    UNIQUE(property_id, source)
);

CREATE INDEX IF NOT EXISTS idx_properties_county ON properties(county);
CREATE INDEX IF NOT EXISTS idx_properties_sale_date ON properties(sale_date);
CREATE INDEX IF NOT EXISTS idx_valuations_property ON valuations(property_id);
"""


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)


def upsert_property(prop: dict) -> int:
    """Insert or update a property. Returns the row id."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO properties (address, city, county, state, zip,
                auction_type, opening_bid, sale_date, case_number, source_url, source)
            VALUES (:address, :city, :county, :state, :zip,
                :auction_type, :opening_bid, :sale_date, :case_number, :source_url, :source)
            ON CONFLICT(case_number, source) DO UPDATE SET
                address = excluded.address,
                city = excluded.city,
                opening_bid = excluded.opening_bid,
                sale_date = excluded.sale_date,
                source_url = excluded.source_url,
                scraped_at = unixepoch()
            """,
            prop,
        )
        row = conn.execute(
            "SELECT id FROM properties WHERE case_number = ? AND source = ?",
            (prop["case_number"], prop["source"]),
        ).fetchone()
        return row["id"]


def upsert_valuation(property_id: int, source: str, estimated_value, detail_url: str = None, raw_data: dict = None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO valuations (property_id, source, estimated_value, detail_url, raw_data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(property_id, source) DO UPDATE SET
                estimated_value = excluded.estimated_value,
                detail_url = excluded.detail_url,
                raw_data = excluded.raw_data,
                fetched_at = unixepoch()
            """,
            (property_id, source, estimated_value, detail_url, json.dumps(raw_data) if raw_data else None),
        )


def get_stale_valuation_property_ids(source: str) -> list[int]:
    """Return property IDs that have no valuation (or stale valuation) for a source."""
    cutoff = time.time() - VALUATION_CACHE_TTL
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.id FROM properties p
            LEFT JOIN valuations v ON v.property_id = p.id AND v.source = ?
            WHERE v.id IS NULL OR v.fetched_at < ?
            ORDER BY p.scraped_at DESC
            """,
            (source, cutoff),
        ).fetchall()
        return [r["id"] for r in rows]


def get_all_properties_with_valuations() -> list[dict]:
    with get_db() as conn:
        props = conn.execute(
            "SELECT * FROM properties ORDER BY sale_date ASC, county ASC"
        ).fetchall()

        result = []
        for prop in props:
            p = dict(prop)
            vals = conn.execute(
                "SELECT source, estimated_value, detail_url FROM valuations WHERE property_id = ?",
                (p["id"],),
            ).fetchall()
            p["valuations"] = {v["source"]: {"value": v["estimated_value"], "url": v["detail_url"]} for v in vals}

            estimates = [v["estimated_value"] for v in vals if v["estimated_value"]]
            p["best_estimate"] = max(estimates) if estimates else None
            p["equity_gap"] = (p["best_estimate"] - p["opening_bid"]) if (p["best_estimate"] and p["opening_bid"]) else None
            p["equity_gap_pct"] = (p["equity_gap"] / p["opening_bid"] * 100) if (p["equity_gap"] and p["opening_bid"]) else None
            result.append(p)

        return result


def get_property_by_id(property_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
        return dict(row) if row else None


def get_stats() -> dict:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        with_vals = conn.execute(
            "SELECT COUNT(DISTINCT property_id) FROM valuations WHERE estimated_value IS NOT NULL"
        ).fetchone()[0]
        return {"total_properties": total, "with_valuations": with_vals}
