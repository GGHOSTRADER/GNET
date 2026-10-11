# Agent task: GNET preparation installer r6

Read HUMAN_AGENT_INSTALL_STEPS.md, the third-party inventory and research-method
attribution. Use English unless the customer requests another language.

1. Verify the supplied ZIP against the independently supplied ZIP SHA256. A
   manifest hash verifies a manifest; do not confuse it with the ZIP hash.
2. Inspect bounded ordinary receipts. If preparation already reports Python,
   21 libraries, standard disabled account and 12 boundaries, tell the customer
   preparation succeeded. Do not recreate/reset the account or repeat installation.
   Reported receipts do not constitute independent isolation certification.
3. For the update ZIP, preserve the original package and downloads. Run the updater
   preview with actual absolute paths, the trusted current package manifest hash,
   and the update manifest hash. Apply when authorized; retain backup and receipt.
   Unknown local revisions are accepted only if every retained payload/hash matches
   this reviewed release. Never edit verified scripts/manifests ad hoc.
4. For a fresh installation, run Download-GNETPrerequisites.ps1 -Plan with the
   preparation manifest hash, then download. Pin sizes/hashes; no substitutes.
   Preview Install-GNETClientPreparation.ps1 without -Apply. Hand the human the
   complete Administrator command from the human guide with actual paths/identity.
5. The human approves Administrator execution and enters any password securely
   locally. Never put credentials in chat, tools, argv, environment or logs. Do
   not bypass approval or grant broker activation, task registration or batch rights.
6. A retry reuses matching installed libraries. Across installer revisions the
   optional -PreparedEnvironment selects a private prior venv. Obtain the path
   from bounded receipts; the installer must independently verify ACL/owner/link
   metadata and all exact versions/import checks before accepting it. Never run
   arbitrary ordinary-user supplied interpreters as Administrator.
7. Read bounded completion receipts and record action, timestamp, package/hash,
   success/failure and remaining work in StateRoot/INSTALL_PROGRESS.md. A failed
   current_step remains unfinished. Never label update-only work an installation.

Code architecture: the downloader pins 22 artifacts; the orchestrator verifies
payloads and snapshots scripts privately; the prerequisite helper probes Python
via python_identity.py (no quote-sensitive -c), installs/verifies 21 libraries and
prepares a missing disabled account; the boundary helper verifies 12 ACLs and
creates only missing approved folders. Human and agent use the same script APIs.
No Windows modules are patched. Preserve deployments, data, other services and
terminal hotkeys. Use synthetic fixtures, not market-data contents.

Full broker deployment, enabling/batch rights, tasks, MCP connection, installed
isolation acceptance, TS admission, training and live trading remain separate
pending gates. Actual new-client Administrator Apply must be reported as untested
until the customer provides its outcome.
