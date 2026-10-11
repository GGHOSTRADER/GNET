# Received TradeStation source visibility

## Where to find the 30-second export

Open <http://127.0.0.1:9040/research/#receivedSources>.
Choose **Received & raw sources**. The **Received TradeStation exports** section
now shows a persistent **@ES · 30 seconds per bar** card:

- 29,466 verified bars.
- 910 closed primary trades and zero open trades.
- September 21 through October 6,2026, with exact source-clock timestamps.
- Stored in protected custody; temporary export files cleaned up.
- Bar/trade contracts, exact bar parent and MA-crossover checks passed.

The same card appears on <http://127.0.0.1:9040/intake/> under
**Received TradeStation sources**. Expand **Metadata and remaining approval
steps** for IDs,clock,volume/price-basis declarations and review gaps. Fabricated
test deliveries are hidden by default and have an explicit checkbox.

Original files are retained in the protected `C:\GNET_DataVault\custody`
collection. Neither browser screen opens market rows. The agent uses the same
bounded public receipts through `gnet_transfer_status`;registered sources use
`gnet_data_catalog` and `gnet_data_inventory` after admission.

## Visibility is separate from approval

This received source has not been registered as a research dataset. It appears
above the **Registered raw datasets** section,not in **Approved datasets**.
The card preserves that status. Continuous @ES mapping,Local clock with undeclared
IANA timezone,unknown volume/price basis and platform fill/cost review remain
training gates. No source was admitted,relabeled,backtested or trained by this UI
update. No arbitrary path or raw-record access was introduced.

## Delivery and verification

Active client: **gnet-client-v11-received-sources**.
Protected broker retained: **guarded-v15-primary-trades-r2**.
Client manifest SHA256:
`1290d78cbc67b88677120c6790857bad6a3e4cb796b5afaae6d3d7b6404fa4f2`.

Eight synthetic presentation checks and12 client-delivery regression tests passed
(28.80 seconds). Shared JS and both inline page scripts passed Node syntax checks.
Client imports passed and existing top-level definitions were preserved. HEAD
view-server inventory unchanged;client_deploy is untracked with no HEAD baseline.
The verified package contains73 source/document files and no market-data payloads.

Actual browser verification showed the card/counts on both command center and
intake. Prior custody receipts matched before/after activation. Broker release,
exports/exchange/results roots,interpreter and port were preserved. Existing
client server was restarted;old client package/config retained for rollback.
No protected task,account,ACL or runtime changes were needed.

Configured MCP transport points to the same client version;current chat tool
injection refresh remains unverified. Typed CLI fallback remains available.
Screenshot:main `.artifacts/received-30-second-source.jpg`.
Evidence:main `.artifacts/received-source-client-activation.json` and
`received-source-client-package.json`.
