import json
from pathlib import Path

from training_mlp.profile_vp_cost import select_activity_sessions


def test_select_activity_sessions_returns_low_median_high_without_duplicates(
    tmp_path: Path,
):
    manifest = {
        "partitions": [
            {"session_date": "middle", "input_rows": 20},
            {"session_date": "high", "input_rows": 30},
            {"session_date": "low", "input_rows": 10},
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert select_activity_sessions(path) == ["low", "middle", "high"]
