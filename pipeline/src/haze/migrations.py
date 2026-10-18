"""Ordered, one-time changes to an existing DB (the production DB lives on in
the Actions cache). db.SCHEMA creates current tables for a new DB; each
migration brings an older DB up to it, once, and `meta.schema_version`
records how far a DB has got. Append new migrations; never edit old ones."""

from __future__ import annotations

import logging
from collections.abc import Callable

import duckdb

from haze import events, regions

log = logging.getLogger(__name__)


def _columns_added_after_launch(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS near_static BOOLEAN")
    con.execute("ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS tier VARCHAR")
    con.execute("ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS n_passes INTEGER")
    con.execute("ALTER TABLE event_snapshots ADD COLUMN IF NOT EXISTS day_geom BLOB")


def _repair_regions_and_backfill_tier(con: duckdb.DuckDBPyConnection) -> None:
    """Events stored before provinsi and kabupaten were chosen jointly, or
    before the evidence tier existed, get both recomputed from their hotspots."""
    seasons = [r[0] for r in con.execute("SELECT DISTINCT season FROM fire_events ORDER BY 1").fetchall()]
    repaired = sum(events.repair_regions(con, s) for s in seasons)
    log.info("migration: %d region pairs repaired, %d tiers backfilled", repaired, events.backfill_tier(con))


def _provinsi_2022(con: duckdb.DuckDBPyConnection) -> None:
    """38 provinces: reload the admin regions (now regrouped by the 2022 laws)
    and move stored hotspots and fires in the new provinces' kabupaten there.
    Only a DB holding the 2020 map (Papua without Papua Selatan) changes; one
    without regions yet loads the new map on its first run."""
    ids = {r[0] for r in con.execute("SELECT id FROM regions WHERE level = 'provinsi'").fetchall()}
    if "prov:papua" not in ids or "prov:papua-selatan" in ids:
        return
    regions.load_admin(con)
    moves = [(new, old, kab) for (old, kab), new in regions.PROVINSI_2022_BY_KAB.items()]
    for table in ("hotspots", "fire_events"):
        con.executemany(f"UPDATE {table} SET provinsi = ? WHERE provinsi = ? AND kabupaten = ?", moves)
    log.info("migration: regions regrouped into 38 provinces")


# schema_version N = the first N migrations have run.
MIGRATIONS: list[Callable[[duckdb.DuckDBPyConnection], None]] = [
    _columns_added_after_launch,
    _repair_regions_and_backfill_tier,
    _provinsi_2022,
]


def apply(con: duckdb.DuckDBPyConnection) -> int:
    """Run the migrations this DB has not had, each in its own transaction
    with its version bump; returns the schema version."""
    version = con.execute("SELECT coalesce(max(schema_version), 0) FROM meta").fetchone()[0]
    for n, migrate in enumerate(MIGRATIONS[version:], start=version + 1):
        con.begin()
        try:
            migrate(con)
            con.execute("DELETE FROM meta")
            con.execute("INSERT INTO meta VALUES (?)", [n])
            con.commit()
        except Exception:
            con.rollback()
            raise
        log.info("migrated DB to schema version %d (%s)", n, migrate.__name__)
        version = n
    return version
