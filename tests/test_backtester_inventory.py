import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.backtester_inventory import data_inventory, main, strategy_inventory


def make_catalog(tmp_path, *, missing_volume=False):
    entries = []
    for name in ("old", "new"):
        root = tmp_path / name
        partition = root / "parquet/session_date=2026-06-15"
        partition.mkdir(parents=True)
        values = {"timestamp": [1, 2], "price": [6000.0, 6000.25]}
        if not missing_volume:
            values["volume"] = [1, 2]
        pq.write_table(pa.table(values), partition / "ticks.parquet")
        (root / "manifest.json").write_text(json.dumps({"symbol": "@ES", "source_timezone": "America/New_York"}))
        entries.append({"id": name, "asset": "ES", "symbol": "@ES", "timezone": "America/New_York",
                        "root": name, "status": "test", "notes": "fixture"})
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"schema_version": 1, "datasets": entries}))
    return catalog


def test_strategy_registry_is_source_of_truth():
    rows = strategy_inventory()
    assert [row["name"] for row in rows] == ["ma_cross"]
    assert rows[0]["default_parameters"] == {"fast": 9, "slow": 18, "reset_each_session": False}


def test_metadata_inventory_and_overlap_without_reading_rows(tmp_path, monkeypatch):
    catalog = make_catalog(tmp_path)
    def fail_read(*args, **kwargs):
        raise AssertionError("inventory must not read tick rows")
    monkeypatch.setattr(pq, "read_table", fail_read)
    monkeypatch.setattr(pq.ParquetFile, "iter_batches", fail_read)
    result = data_inventory(catalog)
    assert result["datasets"][0]["tick_rows"] == 2
    assert result["datasets"][0]["session_count"] == 1
    assert len(result["datasets"][0]["manifest_sha256"]) == 64
    assert result["overlaps"][0]["sessions"] == ["2026-06-15"]
    assert not any(row["errors"] for row in result["datasets"])
    assert len(data_inventory(catalog, dataset="new")["datasets"]) == 1
    with pytest.raises(ValueError, match="no datasets"):
        data_inventory(catalog, asset="NQ")


def test_missing_columns_fail_command(tmp_path, capsys):
    catalog = make_catalog(tmp_path, missing_volume=True)
    assert main(["data", "--catalog", str(catalog)]) == 1
    assert "missing columns ['volume']" in capsys.readouterr().out


def test_missing_archive_reported_not_silently_empty(tmp_path):
    catalog = make_catalog(tmp_path)
    document = json.loads(catalog.read_text())
    document["datasets"][0]["root"] = "absent"
    catalog.write_text(json.dumps(document))
    result = data_inventory(catalog)
    assert result["datasets"][0]["errors"] == ["manifest missing", "no prepared session partitions found"]


def test_duplicate_ids_rejected(tmp_path):
    catalog = make_catalog(tmp_path)
    document = json.loads(catalog.read_text())
    document["datasets"][1]["id"] = "old"
    catalog.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="duplicate dataset IDs"):
        data_inventory(catalog)


def test_json_output_and_metadata_only_scope(tmp_path, capsys):
    catalog = make_catalog(tmp_path)
    assert main(["data", "--catalog", str(catalog), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "Metadata only" in result["limitations"]
    assert len(result["datasets"]) == 2


def test_incomplete_archive_flagged_in_catalog(tmp_path):
    catalog = make_catalog(tmp_path)
    (tmp_path / "old/INCOMPLETE.txt").write_text("failed")
    result = data_inventory(catalog)
    assert "archive marked INCOMPLETE; do not use" in result["datasets"][0]["errors"]
