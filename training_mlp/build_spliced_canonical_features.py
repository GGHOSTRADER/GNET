"""Build 13 canonical features from the selected, session-matched bar splice."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.study_pipeline import engineer_features, load_bars


def build_features(bars_path: Path, splice_manifest_path: Path, output_path: Path) -> dict:
    manifest = json.loads(splice_manifest_path.read_text(encoding="utf-8"))
    if Path(manifest["output_bar_path"]).resolve() != bars_path.resolve():
        raise ValueError("splice manifest does not identify the selected bar file")
    bars = load_bars(bars_path)
    first_new_session = manifest["first_new_session"]
    session_start = pd.Timestamp(first_new_session) - pd.Timedelta(hours=6)
    new_bars = bars.loc[bars["Date/Time"] >= session_start]
    if new_bars.empty:
        raise ValueError("no new-vintage bars at handoff")
    reset_at = new_bars.iloc[0]["Date/Time"]
    features = engineer_features(bars, vwap_mode="canonical", reset_at=reset_at)
    boundary_index = int(new_bars.index[0])
    if not features.loc[boundary_index:boundary_index + 58, list(FEATURE_NAMES)].isna().all().all():
        raise ValueError("handoff did not clear the 60-bar feature window")
    if features.loc[boundary_index + 59, list(FEATURE_NAMES)].isna().any():
        raise ValueError("features did not resume after the 60th new-vintage bar")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)
    result = {
        "source_bars": str(bars_path.resolve()),
        "source_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "splice_manifest": str(splice_manifest_path.resolve()),
        "first_new_session": first_new_session,
        "reset_at": str(reset_at),
        "vwap_mode": "canonical",
        "feature_warmup_bars_after_handoff": 59,
        "rows": len(features),
        "labeled": False,
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_bars = Path(__file__).parent / "strategies/MA2CrossLE/inputs/data_30_spliced_2026-09-21.txt"
    parser.add_argument("--bars", type=Path, default=default_bars)
    parser.add_argument("--manifest", type=Path, default=default_bars.with_suffix(".manifest.json"))
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).parent / "strategies/MA2CrossLE/processed/features_spliced_canonical_2026-09-21.parquet",
    )
    args = parser.parse_args()
    print(json.dumps(build_features(args.bars, args.manifest, args.output), indent=2))


if __name__ == "__main__":
    main()
