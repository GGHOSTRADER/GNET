# GNET Delivery Documentation Index

Use this page as the authoritative map for the customer delivery. Where older technical
notes overlap these guides, the files listed here control installation and acceptance for
the delivered release.

## Repository layout

- The repository root contains source modules, launch/install scripts, dependency locks, `README.md`, and agent instructions.
- `documentation/guides/` contains human and agent runbooks; `documentation/legal/` contains licenses and legal drafts.
- `documentation/internal/` and `documentation/reports/` retain working notes and reference reports, separate from delivery guides.
- Generated local material—including temporary test/finalizer output—belongs under `.artifacts/`, not at the repository root.
- Raw market-data exports are not opened or scanned unless the task explicitly authorizes use of that dataset.

| Delivery requirement | Authoritative document |
|---|---|
| System requirements | `customer_installation_guide.md`, sections 1–3 |
| Installation guide | `customer_installation_guide.md` |
| TradeStation and EasyLanguage setup | `customer_installation_guide.md`, section 5; `../EL_files/README.md` |
| Startup, shutdown, restart, and hard reset | `guides/QUICK_START.md`; `how_to_run_pipeline.md` |
| Operations and monitoring | `guides/QUICK_START.md`; `how_to_run_pipeline.md` |
| Training and financial validation | `guides/TRAINING_GUIDE.md`; `financial_validation.md` |
| Troubleshooting | `guides/TROUBLESHOOTING.md` |
| Architecture diagrams | `../diagrams/gnet_online_high_level.mmd`, `../diagrams/gnet_offline_training.mmd`, and `../diagrams/system_overview.mmd` |
| Proposed guarded data/research runtime | `guarded_research_runtime_architecture.md` |
| Research validation, revision naming and provenance | [Requirements](research_validation_and_provenance_requirements.md) |
| Guarded runtime/backtester integration audit | [October 2 audit](reports/guarded_backtester_integration_audit_2026-10-02.md) |
| Research interfaces and trade viewer | [Specification](research_interfaces_and_trade_viewer.md) |
| Guarded research implementation phases | [Roadmap](guarded_research_implementation_phases.md) |
| Guarded research builder handoff | [Builder prompt](guides/GUARDED_RESEARCH_BUILDER_PROMPT.md) |
| Acceptance checklist | `guides/CUSTOMER_ACCEPTANCE.md` |
| Third-party components and licenses | `legal/THIRD_PARTY_COMPONENTS.md` |
| Known limitations, exclusions, and responsibilities | `guides/LIMITATIONS_AND_RESPONSIBILITIES.md`; `guides/RELEASE_NOTES.md` |
| Prompt for Codex, Claude Code, or another coding agent | `guides/AGENT_OPERATIONS_PROMPT.md` |
| Exact release contents and hashes | `RELEASE_CONTENT_AUDIT.json`; `RELEASE_MANIFEST.sha256` |

The source package does not contain `.env`, credentials, a portable virtual environment,
third-party installers, or customer account information. `install.ps1` creates the local
non-secret environment configuration and project-owned `.venv` on the destination machine.
