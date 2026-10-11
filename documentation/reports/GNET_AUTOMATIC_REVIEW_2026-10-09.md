# Automatic source review — implementation status

The installed v28 form mixed human confirmations with machine checks and required
calendar JSON per source. Separate candidate v29/v31 implements broker preflight
and automatic identifiers, reviewed calendar selection, result tables and fresh
server checks before drafting. Original installed releases and controls are retained.

## Implemented

- Source timestamps: strict timezone/DST localization, ordering, calendar scope
  and time-bar alignment. The timezone declaration is not inferred from prices.
- Export coverage: observed row count and endpoints versus immutable source/scope.
- Session completeness: scheduled sessions/bar-close slots versus observed bars.
  Missing slots, missing whole sessions and partial boundaries produce failures.
- No manual timestamp/coverage/completeness checkboxes; draft results cannot be
  overridden by submitted booleans. Source rows remain inside the broker.
- Calendar/policy metadata generated. Browser/agent use calendar IDs, avoiding
  large daily schedules in public responses or request payloads.
- Real calendar profiles bind exact chart session/asset/scope and require a local
  administrator commit. Installation grants no dataset/research permissions.

## Verification and boundaries

33 focused synthetic and legacy review/model/replay tests passed in 33.05 seconds.
Two broader socket/contained-worker tests were not run in this source check.
Sandbox tests substitute exclusive file creation for NTFS hard-link publication
only in the test process; shipping transport is unchanged. Changed modules import,
top-level definitions are retained, inline JavaScript parses and closed package
hashes/fresh stdio MCP discovery are checked separately.

This is a candidate, not installed acceptance. Current port 9040 remains v28 until
local deployment/client update. No real exports were inspected or trained here.
The actual chart's reviewed calendar profile still needs configuration once.
Event/tick continuity, additional intraday-break profiles and partial-session
acceptance are separate work; a gap is never assumed to mean no trading.

## Delivery

Directory: `.artifacts/GNET-Command-Center-v29-AutomaticReview-Candidate`.

| Identity | SHA256 |
|---|---|
| Delivery manifest | `df0e115d5d532d3b718c0a2da35d97d84ed9571b4bcc66644e6b9f7ac18c1647` |
| Broker v29 manifest | `bb9fc05be68a9b7eb99c86e325f8c6e60e474833f9f5a96b64b41132322f8590` |
| Client v31 manifest | `23f97b9efd060fd57d077ccebced866462fe0228d657b6e518ba4107b2ea85c3` |

Dependency lock is unchanged. Local administrator deployment retains prior
releases and uses the existing broker credential locally. The matching client is
an ordinary-user update. Calendar installation is a separate reviewed control;
no guessed exchange schedule is shipped. Read the candidate's automatic source
review guide before activation/configuration.
