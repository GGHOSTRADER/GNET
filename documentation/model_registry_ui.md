# GNET Model Registry UI

The live router discovers strategy models from `model_registry/*/registry.json`.
It no longer contains a hard-coded MA model path.

## Open the local page

From the repository root:

```powershell
python -m gnet_ui.server
```

Open `http://127.0.0.1:9020`. The server binds only to local loopback and is
not part of the inference path.

The page shows every valid strategy directory and allows three validated edits:

- enable or disable the strategy;
- set the approval threshold from 0 through 1;
- select CPU or CUDA.

Restart `inference.strategy_router` after saving a change. The page deliberately
does not hot-swap a model while candidates may be in flight.

## Add a strategy

Create this structure:

```text
model_registry/
└── StrategyName/
    └── registry.json
```

The configuration points to an artifact directory containing:

```text
model_best.pt
scaler_best.pkl
config.json
```

Example:

```json
{
  "schema_version": 1,
  "strategy_id": "MA2CrossLE",
  "display_name": "MA 2 Cross Long Entry",
  "enabled": true,
  "model_type": "pytorch_mlp",
  "artifact_dir": "training_mlp/strategies/MA2CrossLE/model/mlp_baseline",
  "threshold": 0.5,
  "device": "cpu",
  "feature_stream": "features_transformer"
}
```

The directory name must exactly match `strategy_id`. Invalid configurations or
missing artifacts appear as errors on the page and prevent the router from
starting with a partially valid registry.
