import ast
from pathlib import Path


TRAINER = Path(__file__).parents[1] / "training_mlp" / "30_training_mlp.py"


def test_ma_trainer_imports_canonical_splitters_and_has_no_local_copies():
    tree = ast.parse(TRAINER.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    source = TRAINER.read_text(encoding="utf-8")

    assert "split_test" not in function_names
    assert "purged_embargo_splits" not in function_names
    assert "PurgedWalkForward" in source
    assert "purged_chronological_holdout" in source


def test_ma_feature_contract_excludes_event_timestamps():
    tree = ast.parse(TRAINER.read_text(encoding="utf-8"))
    feature_names = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "FEATURE_COLS" for target in node.targets):
                feature_names = ast.literal_eval(node.value)
                break

    assert feature_names is not None
    assert "Date/Time" not in feature_names
    assert "t1" not in feature_names
