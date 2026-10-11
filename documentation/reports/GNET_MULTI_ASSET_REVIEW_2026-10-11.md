# Multi-asset source-review candidate — October 11, 2026

Staged, verified, not installed:
`.artifacts/GNET-MultiAssetReview-v45-r1`.
Broker: `guarded-v45-multi-asset-review`.
Broker manifest SHA256:
`a8ec77bfc70f54fcd8241f44f3105cb6fda357482ff6b0858929cdc49f33c01d`.
Client: `gnet-client-v78-multi-asset-review`.
Client manifest SHA256:
`44586c71ee137912f5e139e7da371c7c47d497dc91f87ed928d304e26be10555`.

## Resulting review behavior

Review resolves an exact symbol and saved source-series type against a reviewed
instrument profile. The profile supplies asset identity, exchange, country,
exchange timezone, price increment, multiplier, volume units and delivery identity
when applicable. Profile installation grants no source or research permission.
No American/non-American symbol heuristic supplies market hours.

Unknown profiles produce a usable pending metadata result listing the missing
facts, preserving source identity and closing approval. Known profiles use their
own asset's dated reference calendar and exported chart-session schedule.
Calendar asset/session and exchange timezone must match. Original holiday,
early-close, chart-grid and source-capture checks remain in place.

ES retains its existing supported-symbol specification. Another asset never
inherits ES economics. Instrument profiles are immutable, exact-symbol documents
bound to administrator-reviewed commit hashes. Changed profiles, missing commits,
changed increments and changed manifest economics fail closed. Printable provider
symbols remain metadata, independent of filesystem-safe registry identifiers.

The client displays series type, asset, exchange, country and exchange timezone
when available. Public viewer metadata uses the manifest asset.

## Profile preparation

The candidate includes `scripts/guarded_instrument_admin.py`. Its plan mode reads
one explicitly selected profile JSON, verifies its digest and the installed package
identity, and displays the document for review. `--apply` requires local Windows
Administrator approval and commits it without registering a dataset. Profile
fields are defined in `gnet_broker/instrument_profiles.py`. Facts require evidence;
no real instrument specification or market calendar was invented or installed.

The existing market-calendar administrator tool can install a reviewed dated
reference for the profile asset. Chart hours intersect that reference, so a US
country value alone cannot authorize a schedule or prove complete coverage.

## Validation and limits

15 focused fabricated tests passed (0.80 seconds), including saved/reused stock
metadata, dollar-sign symbols, tick-size mismatch, immutable profile replacement,
commit tampering, own-calendar selection, wrong-asset calendar rejection, pending
metadata, ES training-artifact parent resolution and public viewer identity.
173 browser checks passed in 53.0 seconds without snapshot updates. Missing-profile
browser coverage asserts the visible explanation, retained metadata and closed
approval. Existing review/calendar publication regression also passes.

Modified modules import. Existing top-level definitions and class methods match
the immutable V44 baseline; the packaged files are not tracked at HEAD.
Broker/client closed package verification, deployment plan hashes and PowerShell
parser checks passed. No installed protected execution acceptance was run for V45.

Non-ES calculation adapters and non-ES continuous-contract ownership remain
unfinished. Their capability badges and computation guards stay closed; generic
source review does not certify universal feature engineering, backtesting or
training. No real source admission, data inspection, training, live changes,
instrument-profile installation or market-reference installation occurred.

## Protected deployment handoff

After explicit Administrator approval, activate the candidate using
`Deploy-ReviewedCommandCenter.ps1 -Apply` in this delivery. It keeps prior releases,
prompts locally for the existing broker password and scans all existing security
checks with a five-million-object bound and the same 1,200-second time bound.
The matching ordinary-user `Install-ReviewedCommandCenterClient.ps1 -Apply`
reruns the complete browser gate before stopping the server.

Native authentication/two-identity isolation acceptance remains separate and must
precede real-data registration. Installed V44/V77 is unchanged until this handoff.
