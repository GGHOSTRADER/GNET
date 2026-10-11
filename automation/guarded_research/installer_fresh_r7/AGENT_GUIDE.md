# Agent task: install GNET preparation on this new Windows computer

Execute the authorized preparation work. This is a standalone fresh-install
package; no older ZIP, update ZIP, customer-specific path or prior receipt is
required. Read HUMAN_AGENT_INSTALL_STEPS.md, the third-party inventory and
research-method attribution first.

1. Verify the original ZIP against the independently supplied ZIP SHA256. If
   that trust value is missing, ask for it; continue only read-only inspection.
   Read the preparation manifest hash from CHECKSUMS.txt in the verified ZIP.
2. Use actual absolute extracted-package paths. Check the manifest states
   `download_on_target`, `activation_allowed=false`, `broker_code_included=false`.
3. As the ordinary researcher, run Download-GNETPrerequisites.ps1 with the verified
   -ManifestSha256 and -Plan. Then run it without -Plan. Preserve good downloads;
   reject changed files and substitute versions. Only pinned official hosts are
   allowed. This step needs neither Python nor Administrator privileges.
4. Preview Install-GNETClientPreparation.ps1 without -Apply. Run
   Get-GNETPreparationInstallCommand.ps1 -ManifestSha256 '<verified hash>' -Save
   as the ordinary researcher to generate the complete Administrator handoff.
   Its StateRoot and ResearcherIdentity defaults come from this machine's user.
   If your execution context is different, supply the actual researcher's values
   explicitly. Never substitute a prior customer's machine, username or paths.
5. Hand off the generated command. The human opens 64-bit Windows PowerShell as
   Administrator, approves the action, and enters any new broker password locally
   in the secure prompt. Never collect/log/serialize passwords in chat, tools,
   argv or environment. Do not trigger unattended elevation or bypass approval.
6. Read bounded ordinary receipts after execution. Report Python, all 21 locked
   distributions/import smoke, account state and 12 ACL boundaries separately.
   A failed checkpoint remains unfinished. Resume the same command when already
   authorized, retaining correct dependencies/account/folders. An explicit prior
   private venv needs the installer's independent metadata and version checks.
7. Maintain StateRoot/INSTALL_PROGRESS.md with timestamps, package/hash, commands,
   outcomes, receipt paths and pending handoffs. Report actual results, not plans
   or assumed success. Receipts are not installed-account isolation certification.

Architecture: pinned downloader → reviewed orchestrator/private snapshots → saved
Python identity probe → private locked libraries → missing disabled standard
account → 12 verified folder boundaries → completion receipts. Human and agent
operate the same scripts. Preparation includes no broker code activation, tasks,
batch-logon rights, data migration, research jobs or training. Full deployment and
installed-account synthetic acceptance are later gates. Preserve live services,
existing deployments, data and hotkeys. Do not inspect market-data contents.

The package includes documented fixes for direct/versioned LocalAccounts module
layouts, Windows PowerShell quote removal, the 48-character account-description
limit, and the harmless protected DACL AI flag. Run checks against the actual
installed gates before promising an automatic TS-to-training flow.
