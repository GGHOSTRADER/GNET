# GNET preparation installer r6 — human guide

## Existing client: preparation already succeeded

The supplied final client receipts report Python 3.12.7 x64, all 21 pinned
libraries/import checks, a disabled standard GNETDataBroker account, and all
12 folder boundaries verified. Keep them. No repeat installation is needed.
This update changes the installer files, not the installed account or permissions.
Broker activation, tasks, installed-account isolation acceptance and data/training
are separate pending work. Preparation success does not certify isolation.

## Apply the small update

Keep the original preparation folder and its verified downloads. Extract the
update ZIP into a separate ordinary folder. Verify the ZIP against the SHA256
provided separately by the sender. Read `APPLY_UPDATE_COMMAND.txt` in the update.
Run its preview first, then add `-Apply`. Use the old package's actual trusted
manifest hash (`cf834ee...` for the reported client r5), not the update hash.
The updater verifies all retained payloads and downloads, backs up replacements,
and writes a receipt. It rejects unrelated modifications. It needs no elevation.
An interrupted update needs review of its backup before further changes.

## Fresh client

1. Extract the new small online preparation ZIP and verify its external ZIP hash.
2. Open `START_HERE.cmd` to download the 22 exact prerequisites. Correct existing
   downloads are reused. Large binaries are downloaded, not shipped in the ZIP.
3. Read the manifest hash from `CHECKSUMS.txt` after ZIP verification. In ordinary
   64-bit Windows PowerShell run the command below without `-Apply` to preview.
4. Open **64-bit Windows PowerShell as Administrator**, then execute:

```powershell
& '<absolute package>\Install-GNETClientPreparation.ps1' `
  -ManifestSha256 '<preparation manifest hash>' `
  -StateRoot '<ordinary user LocalAppData>\GNETPreparation' `
  -ResearcherIdentity '<COMPUTER\ordinary-user>' `
  -Apply
```

Confirm locally. If the broker account is missing, enter its new password in the
secure local prompt. Keep credentials private. An existing standard account keeps
its password and enabled/disabled state. An administrator broker is rejected.

## Resume a partial installation

Run the same reviewed installer again. It retains correct downloads, reuses exact
Python, skips pip installation when the current private environment passes all
21 version/import checks, preserves an existing account, and verifies existing
matching folder ACLs. The harmless Windows `AI` DACL flag is accepted; changed
owners, permissions, identities and inheritance rules are still rejected.

For an environment from an older revision, add:

```powershell
-PreparedEnvironment 'C:\ProgramData\GNETPreparation\<actual-old-revision>\venv'
```

Use its actual path from the previous administrator prerequisite receipt, then
review it locally. The installer independently checks the whole environment's
ownership/permissions and link metadata before running its interpreter. Ordinary
receipts alone are not trusted. A selected environment that fails verification is
preserved; the installer stops rather than changing its libraries. Do not select
Conda or a user-writable interpreter for the protected runtime.

## Check progress

Bounded receipts in StateRoot: `download-status.json`, `admin-prerequisites.json`,
`online-installation-status.json`. The latter records `current_step`, `failure`,
`dependencies_reused`, `prepared_environment`, and the verified boundary count.
Checkpoint receipts survive a canceled/failed later stage. Update-only completion
does not imply installer execution. Agent progress belongs in `INSTALL_PROGRESS.md`.

The preparation browser (`Start-GNETPreparation.ps1`, port 9043) is a preparation
status helper. It is separate from the full research command center. Read
`THIRD_PARTY_TECHNOLOGY_INVENTORY.md` and `RESEARCH_METHOD_ATTRIBUTION.md`; the
listed software and attributed research methods are not owned by GNET.

## What permissions are prepared

| Folder group | Broker account | Researcher |
|---|---|---|
| Broker root/runtime | Read and execute | No access |
| Broker state and data vault | Modify | No access |
| Exchange root | Read and execute | Read and execute |
| Request/pending/cancel folders | Modify | Modify |
| Status and results | Modify | Read and execute |
| Import root | Read and execute | Read and execute |
| Import incoming | Modify | Create exports; modify their children |

Administrators/SYSTEM retain ownership and full control. Incoming permissions
do not let the researcher delete the incoming root. Existing different owners or
ACLs require review; this installer does not silently repair/adopt them. No account
is enabled and no scheduler, service, batch-logon or live-trading right is granted
by preparation. The optional old venv reuse reads dependency metadata, not trades.
