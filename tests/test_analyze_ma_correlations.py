from __future__ import annotations

import pandas as pd

from feat_files.canonical_features import FEATURE_NAMES
from training_mlp.analyze_ma_correlations import analyze


def test_analyze_ma_correlations_writes_same_report_contract(tmp_path) -> None:
    rows = 20
    frame = pd.DataFrame(
        {
            name: [float(index + offset) for index in range(rows)]
            for offset, name in enumerate(FEATURE_NAMES)
        }
    )
    frame[FEATURE_NAMES[1]] = frame[FEATURE_NAMES[0]] * 2.0
    input_path = tmp_path / "ma.csv"
    output_path = tmp_path / "report"
    frame.to_csv(input_path, index=False)

    summary = analyze(input_path, output_path)

    assert summary["rows"] == rows
    assert summary["canonical_features"] == 13
    assert summary["severe_pairs"] >= 1
    assert (output_path / "pearson_matrix.csv").is_file()
    assert (output_path / "spearman_matrix.csv").is_file()
    assert (output_path / "high_correlation_pairs.csv").is_file()
    assert (output_path / "summary.json").is_file()
