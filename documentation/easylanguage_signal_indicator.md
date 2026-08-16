# EasyLanguage Signal Indicator
> **What:** Pattern for each TradeStation strategy window to retrieve only its own correlated model decisions.

Receives signals from `inference/signal_tcp_server.py` through `SignalBridge.dll` (compiled from `signal_dll.cpp`).

## EasyLanguage Code

```pascal
{ Use the same unique instance ID passed to SendCandidate. }

using elsystem;

Inputs:
    InstanceId("MA-ES-30S-01");

Vars:
    decision_id(""),
    decision_status(""),
    approved(0),
    probability(0.0),
    ok(0);

{ EasyLanguage DLL declarations -- plain value types only, no by-reference
  out-params (EL's External: does not support "int ref" / "double ref") }
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", int, "RecvDecision", Lpstr;
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", int, "GetDecisionApproved", Lpstr;
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", double, "GetDecisionProb", Lpstr;
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", Lpstr, "GetDecisionStatus", Lpstr;
External: "C:\Users\g_med\python_new\GNET\EL_files\SignalBridge.dll", Lpstr, "GetDecisionCandidateId", Lpstr;

{ Poll frequently; the DLL call is non-blocking. }
ok = RecvDecision(InstanceId);

If ok = 1 Then Begin
    approved        = GetDecisionApproved(InstanceId);
    probability     = GetDecisionProb(InstanceId);
    decision_status = GetDecisionStatus(InstanceId);
    decision_id     = GetDecisionCandidateId(InstanceId);

    { First verify decision_id equals the candidate awaiting a reply. }
    If decision_status = "ok" and approved = 1 Then Begin
        { Execute the original strategy's pending direction here. }
    End;
End;

{ Optional: plot the probability for debugging }
plot1(probability, "prob", blue);
plot2(approved, "approved", red);
```

## How It Works

- `RecvDecision(instance_id)` returns only a decision queued for that TradeStation strategy instance
- The DLL maintains a persistent TCP connection to `127.0.0.1:9011` — connects once, stays open
- `1` means ready, `0` means no decision, and `-1` means a connection failure
- Require `status="ok"`, `approved=1`, and the expected candidate ID before executing the original trade

## Notes

- Every strategy window uses a unique stable instance ID but shares one DLL connection
- `signal_tcp_server.py` must be running before TradeStation polls for decisions
- The router accepts only an exact symbol, date, time, and bar-number feature match
- See [[how_to_compile_dll]] to compile `SignalBridge.dll`
- See [[how_to_run_pipeline]] for the full startup order
