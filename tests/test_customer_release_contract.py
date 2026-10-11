from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ma_el_backup_uses_builtin_same_bar_protection():
    source = (ROOT / "EL_files" / "G_MA_CROSS_NN.els").read_text(encoding="utf-8")
    assert "ProfitTargetPoints" not in source
    assert "StopLossPoints" not in source
    assert "EntryPrice +" not in source
    assert "EntryPrice -" not in source
    assert "SetStopContract;" in source
    assert "SetStopLoss(StopLossAmount);" in source
    assert "SetProfitTarget(ProfitTargetAmount);" in source
    assert "StopLossAmount(50)" in source
    assert "ProfitTargetAmount(50)" in source


def test_ma_el_backup_marks_exact_decisions_on_chart():
    source = (ROOT / "EL_files" / "G_MA_CROSS_NN.els").read_text(encoding="utf-8")
    assert "ShowDecisionMarkers(true)" in source
    assert "using elsystem.drawingobjects;" in source
    assert "TextLabel.Create(" in source
    assert "TrendLine.Create(" in source
    assert "BNPoint.Create(CurrentBar + MaxBarsBack - 1" in source
    assert source.count("decision_label.Persist = true;") == 3
    assert source.count("decision_line.Persist = true;") == 3
    assert source.count("decision_line.ExtLeft = false;") == 3
    assert source.count("decision_line.ExtRight = false;") == 3
    assert "DrawingObjects.Add(decision_label);" in source
    assert "DrawingObjects.Add(decision_line);" in source
    assert "Text_New(" not in source
    assert 'DecisionMarkerOffsetPoints(4.0)' in source
    assert '"YES "' in source
    assert '"NO "' in source
    assert '"ERROR"' in source
    assert '"GNET YES "' not in source
    assert '"GNET NO "' not in source
    assert '"GNET ERROR "' not in source
    assert "decision_label.Color = elsystem.drawing.Color.Green;" in source
    assert "decision_label.Color = elsystem.drawing.Color.Red;" in source
    assert "decision_label.Color = elsystem.drawing.Color.Yellow;" in source
    assert "decision_line.Color = elsystem.drawing.Color.Green;" in source
    assert "decision_line.Color = elsystem.drawing.Color.Red;" in source
    assert "decision_line.Color = elsystem.drawing.Color.Yellow;" in source
    assert '" GNET marker added type=approved"' in source
    assert '" GNET marker added type=rejected"' in source


def test_runtime_lock_is_exactly_pinned():
    lines = (ROOT / "requirements-runtime-lock.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line for line in lines if line and not line.startswith("#")]
    assert requirements
    assert all("==" in requirement for requirement in requirements)


def test_customer_installer_provisions_safe_persistent_redis():
    source = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert 'redis:7.4.2-alpine' in source
    assert '--publish "127.0.0.1:6381:6379"' in source
    assert '--mount "source=gnet-redis-data,target=/data"' in source
    assert '--appendonly yes --appendfsync everysec' in source
    assert 'redis-cli PING' in source
    assert 'will not delete or replace it' in source


def test_customer_installer_uses_python_launcher_and_installs_training_by_default():
    source = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "Get-Command py.exe" in source
    assert "-3.12 -m venv" in source
    assert 'Get-Command $PythonCommand' not in source
    assert '(anaconda|conda|miniconda)' in source
    assert 'if ($RuntimeOnly)' in source
    assert 'Join-Path $projectRoot "requirements-development-lock.txt"' in source
    assert 'training_mlp\\.env' in source
    assert 'IncludeTrainingDependencies' in source


def test_complete_training_lock_includes_legacy_experiment_tracker():
    lines = (ROOT / "requirements-development-lock.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert "wandb==0.29.0" in lines


def test_third_party_inventory_covers_locked_requirements():
    inventory = (ROOT / "documentation" / "legal" / "THIRD_PARTY_COMPONENTS.md").read_text(
        encoding="utf-8"
    ).lower()
    requirement_files = [
        ROOT / "requirements-runtime-lock.txt",
        ROOT / "requirements-development-lock.txt",
    ]
    for requirement_file in requirement_files:
        for raw_line in requirement_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            package, version = line.split("==", maxsplit=1)
            assert package.lower() in inventory
            assert version.lower() in inventory


def test_operational_launchers_pin_repository_virtual_environment():
    launch = (ROOT / "launch.ps1").read_text(encoding="utf-8")
    pane_runner = (ROOT / "automation" / "run_service_terminal.ps1").read_text(
        encoding="utf-8"
    )
    watchdog = (ROOT / "automation" / "gnet_watchdog.ps1").read_text(
        encoding="utf-8"
    )
    verifier = (ROOT / "verify_install.ps1").read_text(encoding="utf-8")

    assert '.venv\\Scripts\\python.exe' in launch
    assert '.venv\\Scripts\\python.exe' in pane_runner
    assert '.venv\\Scripts\\python.exe' in watchdog
    assert '.venv\\Scripts\\python.exe' in verifier
    assert "& python " not in launch
    assert "& python " not in pane_runner
    assert 'Command = "python ' not in watchdog
    assert "Get-Command python" not in verifier


def test_customer_release_builder_brands_zona_and_excludes_environment_files():
    builder = ROOT / "build_customer_release.ps1"
    if not builder.exists():
        return
    source = builder.read_text(encoding="utf-8")
    assert "GNET_Zona-customer-source" in source
    assert '$_ .Name -like ".env*"'.replace("$_ ", "$_") in source
    assert 'Replace("MA2CrossLE", "MA2Cross_Zona")' in source
    assert 'Replace("G_MA_CROSS_NN", "MA2Cross_Zona")' in source
    assert '".csv"' in source
    assert "RELEASE_CONTENT_AUDIT.json" in source
    assert '^training_mlp/(zona_|_inspect_)' in source
    assert '"build_hardened", "deliverables", "tmp"' in source


def test_customer_release_builder_excludes_reference_data_and_model_artifacts():
    builder = ROOT / "build_customer_release.ps1"
    if not builder.exists():
        return
    source = builder.read_text(encoding="utf-8")
    assert "includedBaselineTrainingData" not in source
    assert '(inputs|processed|reports|model)' in source
    assert "Historical and processed training datasets" in source
    assert "Reference-model weights, scalers, predictions, metrics" in source
    assert 'registry.template.json' in source
    assert '$registry.enabled = $false' in source
    assert 'data_supplied_by = "Licensee under its own licenses and permissions"' in source


def test_delivery_documentation_covers_required_customer_guides():
    required_documents = [
        "documentation/INDEX.md",
        "documentation/guides/LIMITATIONS_AND_RESPONSIBILITIES.md",
        "documentation/guides/CUSTOMER_ACCEPTANCE.md",
        "documentation/guides/TRAINING_GUIDE.md",
        "documentation/guides/TROUBLESHOOTING.md",
        "documentation/legal/THIRD_PARTY_COMPONENTS.md",
        "documentation/guides/AGENT_OPERATIONS_PROMPT.md",
        "documentation/guides/QUICK_START.md",
        "documentation/customer_installation_guide.md",
        "documentation/how_to_run_pipeline.md",
        "diagrams/gnet_online_high_level.mmd",
        "diagrams/gnet_offline_training.mmd",
    ]
    for relative_path in required_documents:
        assert (ROOT / relative_path).is_file(), relative_path

    customer_text = "\n".join(
        (ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in required_documents
        if relative_path.endswith(".md")
    )
    assert "install.ps1 -IncludeTraining" not in customer_text
    assert "open-source and third-party dependencies" in customer_text


def test_training_guide_defines_local_input_contract_and_commands():
    guide = (ROOT / "documentation" / "guides" / "TRAINING_GUIDE.md").read_text(encoding="utf-8")
    assert "data_30_master.txt" in guide
    assert "trades_30_master.csv" in guide
    assert "Date,Time,Open,High,Low,Close,Up,Down" in guide
    assert "#,Type,Date/Time,Signal,% Profit" in guide
    assert "No VWAP column is required" in guide
    assert "at least 60" in guide
    assert ".venv\\Scripts\\python.exe -m training_mlp.merge_historical_bars" in guide
    assert ".venv\\Scripts\\python.exe -m training_mlp.build_master_dataset" in guide
    assert '$env:MODEL_DIR = "strategies\\MA2CrossLE\\model\\$candidate"' in guide
    assert "registry.template.json" in guide
