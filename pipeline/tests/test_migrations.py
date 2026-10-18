from haze import db, migrations, pipeline
from tests.conftest import NOW
from tests.test_events import FIRE_A, FIRE_B, load


def test_new_db_starts_at_the_latest_version(con):
    assert con.execute("SELECT schema_version FROM meta").fetchall() == [(len(migrations.MIGRATIONS),)]


def test_old_db_is_migrated_once(tmp_path, tagger):
    path = tmp_path / "old.duckdb"
    con = db.connect(path)
    load(con, tagger, FIRE_A + FIRE_B)
    pipeline.build_events(con, tagger, [2026], NOW)
    built = con.execute("SELECT id, tier, n_passes, provinsi, kabupaten FROM fire_events ORDER BY id").fetchall()
    # As the production DB was before migrations: no meta table, no tier columns,
    # an event whose kabupaten is not where its detections are.
    con.execute("DROP TABLE meta")
    con.execute("ALTER TABLE fire_events DROP COLUMN n_passes")
    con.execute("ALTER TABLE fire_events DROP COLUMN tier")
    con.execute("UPDATE fire_events SET kabupaten = 'East' WHERE kabupaten = 'West'")
    con.close()

    con = db.connect(path)
    assert con.execute("SELECT schema_version FROM meta").fetchall() == [(len(migrations.MIGRATIONS),)]
    assert (
        con.execute("SELECT id, tier, n_passes, provinsi, kabupaten FROM fire_events ORDER BY id").fetchall() == built
    )
    # Applied once: a later change is not undone on the next connect.
    con.execute("UPDATE fire_events SET tier = NULL")
    assert migrations.apply(con) == len(migrations.MIGRATIONS)
    assert con.execute("SELECT count(*) FROM fire_events WHERE tier IS NULL").fetchone()[0] == len(built)


def test_provinsi_2022_moves_papua_kabupaten():
    from haze.regions import provinsi_2022

    assert provinsi_2022("Papua", "Merauke") == "Papua Selatan"
    assert provinsi_2022("Papua", "Mimika") == "Papua Tengah"
    assert provinsi_2022("Papua", "Jayawijaya") == "Papua Pegunungan"
    assert provinsi_2022("Papua Barat", "Kota Sorong") == "Papua Barat Daya"
    assert provinsi_2022("Papua", "Kota Jayapura") == "Papua"
    assert provinsi_2022("Papua Barat", "Manokwari") == "Papua Barat"
    assert provinsi_2022("Kalimantan Barat", "Ketapang") == "Kalimantan Barat"
