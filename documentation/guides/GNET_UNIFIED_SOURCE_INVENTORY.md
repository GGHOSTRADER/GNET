# Unified source inventory

Open the Command Center at `/research/`. Source inventory is the common entry
point for received exports and registered datasets. Expand a row to see its
identity, permissions, dates, review, candles, primary trades and research links.

- **All sources** shows received and registered sources together.
- **Awaiting approval** shows received exports with no linked registration.
- **Registered · awaiting approval** shows registered sources without passed admission.
- **Approved for research** shows accepted sources whose validation passed.
- **Transfer / validation failed** shows failed or quarantined receipts.
- **Primary trades available** shows sources with an imported primary ledger.

The Approved sources shortcut applies the approval filter to the same inventory.
Primary-model navigation opens `/research/#primarySources`, which applies the
primary-trades filter to that inventory. Review, candles, trades and research use
the exact export or dataset identity shown inside the expanded row.

Export transfer troubleshooting opens the intake tool for writing exports,
failed transfers and exports not yet received. It is a transport diagnostic view.
It does not grant research permission. Approval permits only the processes listed
inside the source row; choosing a filter does not approve or register a source.

Receipts and catalog sources are merged only when the origin export ID and
nonempty source hash match. Separate exports stay separate, even if they cover
the same dates. Old direct inventory URLs remain available for bookmarks.

Inventory introduced in `gnet-client-v64-unified-inventory-r2`; current installed
client is `gnet-client-v65-inventory-navigation-r1`. The
[current-route audit](../reports/GNET_UI_CURRENT_ROUTE_AUDIT.md) records the
additional regression, correction and 91-test result.
The full fabricated browser suite passed 88/88 in 1.8 minutes with retries
disabled, including inventory linkage, exact action identities, approval/content
filtering, sampling navigation and screenshot comparisons at 1440/768/390 pixels.
Client manifest SHA-256:
`211aad9d05f153e891be6e627435093143906ef21048c59b7b2275580d6ad407`.

The ordinary-user installation restarted the local server on port 9040 and
retained the V42 broker. This UI change did not submit real research jobs.
