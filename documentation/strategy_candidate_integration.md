# Strategy Candidate Integration

Each TradeStation strategy window uses the same `StrategyBridge.dll`. The DLL
shares one TCP connection to port 9012, so adding strategies does not add Python
ports or Redis streams.

The strategy calls:

```text
SendCandidate(strategy_id, instance_id, symbol, date, time_s, bar_num, direction)
```

EasyLanguage declaration and call pattern:

```pascal
Inputs:
    StrategyId("MA2CrossLE"),
    InstanceId("MA-ES-30S-01");
Vars: candidate_id(""), send_ok(0), direction(1), TimeSpan tod(null);

External: "C:\Users\g_med\python_new\GNET\EL_files\StrategyBridge.dll",
    int, "SendCandidate",
    Lpstr, { strategy_id }
    Lpstr, { unique TradeStation window/strategy instance }
    Lpstr, { symbol }
    int,   { date }
    int,   { seconds since midnight }
    int,   { bar number }
    int;   { direction: 1 long, -1 short }

External: "C:\Users\g_med\python_new\GNET\EL_files\StrategyBridge.dll",
    Lpstr, "GetLastCandidateId", Lpstr;

{ Put this inside the strategy's existing primary-signal condition. }
tod = BarDateTime.TimeOfDay;
send_ok = SendCandidate(
    StrategyId, InstanceId, Symbol, Date,
    IntPortion(tod.TotalSeconds), CurrentBar, direction
);
If send_ok = 1 Then
    candidate_id = GetLastCandidateId(InstanceId);
```

Use a stable `strategy_id` such as `MA2CrossLE` to select the model. Give every
TradeStation strategy window a unique, stable `instance_id`. The DLL generates
a GUID candidate ID, stores it by instance, and sends it with the candidate.
`direction` is `1` for long and `-1` for short.

The router waits up to 250 ms for the feature record with the exact same
symbol, date, and `time_s`. TradeStation `CurrentBar` is local to each study and
can differ between the strategy and bar indicator, so `bar_num` remains in the
payload only for diagnostics. The router then loads the model mapped to the
strategy and publishes an explicit approved, rejected, or error decision.

Each strategy window polls its own queue through `SignalBridge.dll`:

```text
RecvDecision(instance_id)
GetDecisionApproved(instance_id)
GetDecisionProb(instance_id)
GetDecisionStatus(instance_id)
GetDecisionCandidateId(instance_id)
```

Always compare the returned candidate ID with the candidate currently awaiting
a response. A missing feature, unknown strategy, or inference failure returns a
rejection with a non-`ok` status; it never silently approves a trade.
