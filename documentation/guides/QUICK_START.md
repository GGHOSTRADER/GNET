# GNET Quick Start

Use this checklist after completing `documentation\customer_installation_guide.md`
and the first-time installation.

## Start GNET

1. Start **Docker Desktop** and wait until its engine reports that it is running.
2. Open PowerShell.
3. Launch the pipeline. The launcher uses GNET's pinned `.venv` automatically:

```powershell
cd C:\GNET
.\launch_grid.ps1
```

`launch_grid.ps1` starts the persistent `redis1` container, opens the GNET services and a dedicated live health monitor in
a Windows Terminal grid, waits for the required services, and launches TradeStation
last. Do not enable the TradeStation GNET documents before the Python services are ready.

## Confirm the four TradeStation ports

In another PowerShell window, run:

```powershell
cd C:\GNET
.\check_gnet_ports.ps1 -Watch
```

The display refreshes every 10 seconds. Continue only when all four are `LISTENING`:

| Port | Purpose |
|---:|---|
| 9009 | Receives completed 30-second bars |
| 9010 | Receives live ticks |
| 9011 | Delivers exact decisions to TradeStation |
| 9012 | Receives strategy candidates |

## Enable TradeStation components

After all four ports are listening:

- Apply `g_cpp_dll_bar` once to the 30-second ES chart.
- Apply `g_cpp_dll_tick` once to the separate 1-tick ES chart.
- Apply `G_MA_CROSS_NN` to the 30-second ES chart.
- Confirm `StrategyId = MA2CrossLE` and a unique `InstanceId`.
- Confirm one contract with pyramiding disabled.
- Confirm the separate built-in Stop Loss and Profit Target are each **$50 per contract**.
- Confirm the intended simulation or live account before enabling automation.

The MA features require 60 completed bars after a fresh start—approximately 30 minutes
on a 30-second chart. Candidates received during warm-up fail closed.

## Read the decision terminals

- **Terminal 3:** receives the TradeStation candidate.
- **Terminal 2:** selects the model and makes the approve/reject decision.
- **Terminal 1:** delivers the exact decision to the originating TradeStation strategy.

## Stop GNET

Preserve Redis data and leave TradeStation/Docker available:

```powershell
cd C:\GNET
.\stop.ps1
```

Also close TradeStation and Docker Desktop to release memory:

```powershell
.\stop.ps1 -StopTradeStation -StopDockerDesktop
```

Do not use `nuke.ps1 -ConfirmDataLoss` for normal shutdown. It permanently removes the
Redis container and its stored streams, groups, offsets, and readiness state.

## If startup fails

Keep the TradeStation components disabled and run:

```powershell
cd C:\GNET
.\check_gnet_ports.ps1
docker ps -a
docker exec redis1 redis-cli PING
```

Redis must return `PONG`. For detailed recovery procedures, use
`documentation\customer_installation_guide.md` and
`documentation\how_to_run_pipeline.md`.
