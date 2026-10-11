# Current Command Center UI audit

The original suite passed 88/88 against installed V64-r2. Coverage review found
that sorting/filtering and Trash tests used the legacy imported-primary page.
The existing unified-inventory test checked a removed wrapper but did not check
the navigation link itself after asynchronous catalog loading.

Three new current-route tests cover sorting, bar/asset/type/import-date filtering,
empty results and in-page hash navigation. Trash tests now enter through the
current Shared research resources and context panel. Legacy primary-inventory
tests remain explicitly marked as bookmark compatibility coverage.

The new navigation test failed on V64: `#importedPrimaryNavigation` was recreated
by `GNETLibrary.update()` after catalog loading, despite having been removed at
initial setup. Its presence violated the unified source inventory design. The
failure trace, screenshot and context are retained in
`.artifacts/v64-current-route-failure/`.

V65 creates the imported-primary navigation link only on the primary workflow
page. Its link points to the filtered unified source inventory. It no longer
appears on the source page after loading or hash changes.

The full suite passed **91/91 in 1.8 minutes**, with retries disabled and existing
screenshot baselines unchanged. V65 was installed and the local server restarted.
Client release: `gnet-client-v65-inventory-navigation-r1`.
Manifest SHA-256:
`a7731585fd1413db5eb7b28cba9a46fa79534c2932f368c8e8be3316a16532f0`.

These tests use fabricated API responses against actual packaged HTML/JS.
They do not exercise protected worker computations or real market data.
