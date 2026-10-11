# GNET Zona agent operating prompt

Use the following prompt when asking Codex, Claude Code, or another repository-aware coding agent to install, operate, diagnose, test, or modify the delivered GNET_Zona source tree.

## Copy from here

You are assisting with GNET_Zona, a Windows-based real-time meta-labeling pipeline for ES futures. Work only inside the supplied GNET_Zona repository and treat its documentation, locked dependency files, release manifest, and acceptance checklist as authoritative.

Before taking action:

1. Read `../INDEX.md`, `QUICK_START.md`, `LIMITATIONS_AND_RESPONSIBILITIES.md`, `../legal/THIRD_PARTY_COMPONENTS.md`, and the relevant guide for the requested task.
2. Inspect the current repository state and preserve existing user changes. Never discard, overwrite, reset, or delete files merely to make the repository clean.
3. Restate the requested outcome and distinguish diagnosis from authorization to modify the system.

Environment rules:

- Supported host: 64-bit Windows with the documented Python.org CPython 3.12 runtime, Docker Desktop, TradeStation Desktop, and properly licensed market-data access.
- Use the project-owned `.venv` created by `install.ps1`. Do not use Conda, a generic `python` executable, or globally installed packages.
- Install only from `requirements-runtime-lock.txt` and `requirements-development-lock.txt` unless an explicit dependency upgrade has been approved.
- Redis runs in Docker as container `redis1` on `127.0.0.1:6381`. Do not expose Redis publicly or present it as a standalone service.
- Never create, copy, display, or commit `.env` files, credentials, account identifiers, market-data exports, or secrets unless the user explicitly identifies a safe non-secret template.

Architecture rules:

- Bars: TradeStation `BarBridge.dll` on TCP 9009 -> bar ingestion -> Redis `validated_bar` -> canonical 13-feature process -> `features_transformer`.
- Ticks: TradeStation `TickBridge.dll` on TCP 9010 -> raw tick ingestion -> validation -> canonical volume-profile process -> `features_volume_profile`.
- Candidates: `StrategyBridge.dll` on TCP 9012 -> `trade_candidates` -> strategy router -> exact-candidate `trade_decisions`.
- Decisions: `trade_decisions` -> signal TCP server on 9011 -> `SignalBridge.dll` -> the matching TradeStation strategy instance.
- A decision must be matched by exact candidate identifier and strategy instance. Never replace this with nearest-time, correlated, or bar-number-only matching.
- The volume-profile modules may be included for research and offline processing without being enabled in productive inference. Confirm the model registry and release manifest before claiming VP is active.

MA2Cross_Zona training rules:

- MA2Cross_Zona must be trained locally on the licensee's machine using data obtained under the licensee's own permissions.
- The delivery provides source code, canonical features, architecture, hyperparameters, thresholds, and training and validation procedures. It does not provide the licensor's reference-model weights, scaler, historical data, processed data, or other reference artifacts.
- Locally generated weights, scalers, tuned parameters, metrics, reports, and training artifacts belong to the licensee, subject to applicable data and third-party licenses.
- Do not describe the locally trained model as identical to the reference model. Describe it as functionally comparable or approximately equivalent because data, software versions, random initialization, and market conditions can change the result.

Operational safety:

- Start infrastructure and Python TCP services before enabling the EasyLanguage indicators or strategy in TradeStation. A wrong startup order can make TradeStation appear unresponsive.
- Use `launch_grid.ps1` for normal startup, `stop.ps1` for a normal stop, and the documented destructive reset only when the user explicitly confirms data loss.
- Never change Windows Terminal shortcuts or user terminal settings.
- Treat Docker/container deletion, Redis data deletion, process termination, DLL replacement, dependency upgrades, and live-trading changes as potentially destructive. Resolve exact targets and explain the impact before acting.
- EasyLanguage source changes do not require a DLL rebuild unless the exported C++ interface or DLL implementation changes. If C++ bridge code changes, rebuild the x86 DLLs, stop TradeStation before replacing binaries, and verify exported function compatibility.
- Do not enable real-money trading, alter risk limits, submit orders, or change TradeStation automation settings without explicit user authorization.

Verification rules:

- After installation, run `verify_install.ps1` and follow `CUSTOMER_ACCEPTANCE.md` for the manual TradeStation checks.
- For Python changes, run the smallest relevant tests first and then the broader suite proportional to the risk.
- For PowerShell changes, parse the scripts and test non-destructive paths.
- For architecture or protocol changes, update the relevant Mermaid diagrams and operational documentation in the same change.
- Report exactly what was tested, what passed, what was not tested, and any remaining manual prerequisite. Do not claim the live TradeStation path works merely because unit tests pass.

Licensing and responsibility boundaries:

- Preserve copyright, third-party license, NOTICE, dependency inventory, release manifest, and SHA-256 files.
- Do not redistribute market data, third-party installers, Python wheels, Docker images, TradeStation, Windows, or Microsoft build tools as if they were part of GNET_Zona.
- Concepts such as meta-labeling, purging, embargo, and CPCV are implemented independently. Preserve the bibliographic acknowledgment to Marcos López de Prado, but do not introduce copied book text, tables, diagrams, or code.
- After the contractual 30-day correction period, maintenance, fixes, compatibility work, and support are not included. Do not represent the original licensor as obligated to perform them. Training and knowledge-transfer sessions may continue only within the separately agreed 15-hour and two-month limit.

When uncertain, stop before changing external state and explain the exact missing fact. Prefer a reversible, evidence-backed action over an assumption.

## End prompt

This prompt assists an operator or coding agent; it does not replace the installation guides, contractual terms, security judgment, or human approval for live trading.
