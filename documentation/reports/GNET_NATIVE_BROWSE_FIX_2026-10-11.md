# Native primary source browsing correction

Candidate: `guarded-v43-native-browse-fix`, matching client
`gnet-client-v70-native-browse-fix-r1`. Both are now installed. The user-reported
protected deployment audit passed; the matching ordinary client installed and
launched successfully.

## Behavior

- Browse bars starts at source row 1 plus the requested chart offset.
- Explicit trade selection retains the five-bar lead-in around that trade.
- Consecutive source windows keep their bounded point limit and have no gaps.
- An empty trade filter does not hide the source bars.
- No source schema, producer allowlist, account, custody authorization or research
  approval rules are changed by this calculation fix.

The old V42 calculation reproduced exactly 58 points, starting at row 63, from
the fabricated 120-bar fixture. The new browsing calculation returns all 120.

## Tests

Eight Python regressions exercise short sources, bounded 500-point windows,
consecutive windows and the final partial page, explicit focus, empty matches,
and the worker dispatch/report path with fabricated custody boundaries.
All eight passed. The worker test mocks custody and primary validation; it is
not an installed account-isolation acceptance test.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_native_browse_window.py -q --basetemp=.test_artifacts/native-browse-new-run
```

A browser regression verifies that Browse bars removes `selected_trade_id`,
preserves the export identity, resets `chart_offset` to zero, and requests the
500-point window. Browser tests use fabricated responses.

The complete existing 100-test browser suite passed against V70 in 2.0 minutes,
including unchanged screenshot baselines. After adding the Browse bars regression,
all 10 chart tests passed in 5.5 seconds. This covers 101 distinct browser tests
across those two runs; the latest browser report contains the focused chart run.

## Activation

The protected deployment script checks idle work, verifies the immutable release,
activates it with the existing broker credentials locally, and audits deployment.
The matching ordinary client must then be installed. After activation, repeat the
installed synthetic viewer check: `acceptance-generic-primary-v39-r1` must show
120 bars in Browse bars, and selecting a trade must retain trade focus.

```powershell
# Administrator PowerShell
& 'C:\Users\g_med\python_new\GNET\.artifacts\GNET-Command-Center-v43-NativeBrowseFix-r1\Deploy-ReviewedCommandCenter.ps1' -Apply
```

Broker manifest SHA-256:
`f5e2d22340a332babef534b370a86af3eeb8ed96a93ac3e99c58124762809a35`.
Client manifest SHA-256:
`1572b19e30f5b24cf5b8f4a4fafa747c91f514ca83d591527d98dd3d4f3ba2f9`.

## Installed verification

The actual protected worker returned all 120 source bars when Browse bars was
clicked in the synthetic native viewer, preserving the existing Winner filter.
The visible chart showed `120 loaded bars` from 2026-06-15 10:00:30 through
11:00:00. Job: `job-20261011T051323Z-cd2b62d7987b498b8c569cfb92445546`.
This confirms installed browsing starts at the beginning of the fabricated source.
Selecting View for t-2 retained trade focus: 54 loaded bars beginning at 10:33:30.
Focus job: `job-20261011T051337Z-2fad0837bd1b402b8bed210db5d0a70d`.
Screenshot: `.test_artifacts/native-browse-installed.png`.
