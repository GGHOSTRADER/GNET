# Install GNET preparation on a new Windows computer

This is a standalone package. Extract this ZIP only; no older package or update
is needed. Internet access is required to download the reviewed prerequisites.

## What it installs

- Official Python 3.12.7 x64 in `C:\Program Files\Python312`.
- 21 pinned third-party Python libraries in a private preparation environment.
- A missing standard **GNETDataBroker** Windows account, initially disabled.
- Twelve GNET folder permission boundaries separating the researcher and broker.

Large Python/wheel binaries are downloaded on the destination computer rather
than included in this ZIP. Existing matching Python/dependencies are reused.
Conda and the researcher's Python remain separate from the protected runtime.

## Steps for a human

1. Save and fully extract the ZIP into a normal local folder. Verify the ZIP SHA256
   against the value supplied separately by the sender, before running its files.
2. As your ordinary Windows user, double-click **START_HERE.cmd**. It downloads
   Python and the 21 library wheels, verifying each size and SHA256. Do not run
   this first step under a different Administrator identity.
3. After downloads succeed, the launcher prints a complete installation command
   with this machine's paths and your researcher identity. It also saves it at
   `%LOCALAPPDATA%\GNETPreparation\ADMIN_INSTALL_COMMAND.txt`.
4. Open **Windows PowerShell** using **Run as administrator**. Use its 64-bit
   Windows version. Paste the generated command. Confirm the preparation action.
5. If the account is missing, choose its password in the secure local prompt.
   Keep it private. The agent must never receive the password. Existing standard
   broker accounts retain their password and current enabled/disabled state.
6. Read the completion output. Success requires Python ready, libraries ready,
   no failure, and **12 boundaries verified**. Keep the receipts for deployment.

`CHECKSUMS.txt` inside the verified ZIP contains the **preparation manifest hash**.
It is different from the **ZIP hash** provided by the sender. No update manifest
is involved in this standalone installation.

## Steps with the customer's agent

Give the extracted **START_INSTALL_WITH_AGENT.md** to the agent and ask it to
prepare this computer. Provide the independent ZIP checksum. The agent can
verify the package, download prerequisites, preview the plan, generate your
Administrator command, and inspect bounded progress receipts. You approve
Administrator execution and enter credentials locally. Both routes use the same
installer scripts and verification rules.

## If interrupted

Run START_HERE.cmd again to reuse verified downloads. Rerun the same reviewed
Administrator command to resume. Exact verified libraries are reused before pip;
existing matching folders and account are preserved. A failed later stage does
not mean Python or previously completed stages failed.

The installer accepts Windows' harmless protected DACL `AI` flag but rejects
changed owners, rights, identities and inheritance rules. It preserves deployed
brokers, unrelated contents and differing ACLs for review.

For a previously prepared private environment from another revision, a human may
add `-PreparedEnvironment 'C:\ProgramData\GNETPreparation\<actual-revision>\venv'`.
The installer checks capped owner/ACL/link metadata and all 21 versions/imports
before reusing it. A failed selected environment is preserved without repair.

## Progress and permissions

Ordinary-user receipts are in `%LOCALAPPDATA%\GNETPreparation`:

| File | Evidence |
|---|---|
| `download-status.json` | Verified prerequisite downloads |
| `admin-prerequisites.json` | Python, libraries, account and current step |
| `online-installation-status.json` | Prepared environment, reuse, 12 boundaries and failure |
| `INSTALL_PROGRESS.md` | Agent's actions, outcomes and remaining gates |

| Folder group | Broker | Researcher |
|---|---|---|
| Broker root/runtime | Read and execute | No access |
| Broker state and data vault | Modify | No access |
| Exchange root | Read and execute | Read and execute |
| Request/pending/cancel folders | Modify | Modify |
| Status/results | Modify | Read and execute |
| Import root | Read and execute | Read and execute |
| Import incoming | Modify | Create export folders; modify their children |

Administrators/SYSTEM retain ownership and full control. The researcher cannot
delete the incoming root. Receipts describe progress; they do not certify isolation.

## What comes later

This package prepares the computer. Broker activation, account enabling/batch
rights, scheduled tasks, full research command center, MCP connection and
installed-account acceptance are separate deployment steps. Data admission,
training and live trading are not performed. The optional preparation status
browser on port 9043 is separate from the research command center.

Read THIRD_PARTY_TECHNOLOGY_INVENTORY.md and RESEARCH_METHOD_ATTRIBUTION.md.
The listed libraries, platforms and attributed research methods are not owned by
GNET. All four previously reported installer defects are incorporated in this
revision. Fresh-computer Administrator installation remains pending verification
on the destination machine; do not assume it passed because local tests passed.
