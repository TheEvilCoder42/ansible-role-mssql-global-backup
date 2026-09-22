# Repo Context — ansible-role-mssql-global-backup

Assembled 2026-09-22 from agent memory, all local Claude Code transcripts, git history and the
working tree. Intended as standing context for future sessions in this repo.

---

## 1. What was actually found (be honest about this)

**Agent memory for this repo: empty.** `~/.claude/projects/-home-fabiane-repos-ansible-role-mssql-global-backup/memory/`
contains no files. Nothing has ever been written down.

**Prior conversation history for this repo: none.** This directory holds exactly one transcript —
the session that produced this file. Across all 30 local sessions (2026-08-03 → 2026-09-22,
~255 typed prompts, six project directories) this role is mentioned **zero** times. The
2026-06-18 modernization commits were not made through Claude Code, or were made before the
retained history begins.

**So everything below is reconstructed from the code and the commit history, not recalled.**
Treat it as a reading of the repo, not as remembered decisions. Where intent is unclear, that is
flagged rather than guessed.

**Relevant memory does exist in a sibling repo** (`on-and-offboarding-automation`) and it
generalises — see §6.

---

## 2. What the role is

An Ansible role that creates and maintains **SQL Server Agent backup jobs on SQL Server for
Linux**. It exists because on Linux there is no `xp_cmdshell` and no Maintenance Plan UI, so the
job, its step, its schedule and the schedule attachment all have to be built by hand through
`sp_add_job` / `sp_add_jobstep` / `sp_add_schedule` / `sp_attach_schedule`.

Upstream is David Lundgren's `ansible-role-mssql-backup` (2020, MIT). This is a long-lived fork:
every commit since 2022-02 is Fabian Eichenberger's, and the fork has diverged substantially in
behaviour. `meta/main.yml` and the README still credit the original author.

**Shape:**

```
tasks/main.yml            3 tasks: create backup dir, full-backup job, transaction-log job
library/mssql_global_backup.py   698-line custom module — all the real logic
defaults/main.yml         connection + schedule + retention knobs
molecule/default/         one converge scenario (stale — see §5)
```

The role calls the module twice with the same connection parameters, differing only in
`type: full` vs `type: logs` and which `mssql_*_schedule_*` variables feed it.

---

## 3. How the module works

`sqlcmd` is the only transport — no Python DB driver.

* `resolve_cli_path()` probes `/opt/mssql-tools18/bin/sqlcmd`, then `/opt/mssql-tools/bin/sqlcmd`,
  then `shutil.which('sqlcmd')`. Fails cleanly with an actionable message if none is found.
* The password goes through the **`SQLCMDPASSWORD` environment variable**, never `-P` on the
  command line — so it does not land in the process table. `login_password` is `no_log=True`.
* Every invocation targets `-d msdb -b` (the `-b` makes `sqlcmd` exit non-zero on SQL errors, so
  `subprocess.check_call` actually catches failures).
* `quoteName()` does real SQL identifier/literal quoting with doubling of the closing quote char,
  and `path` is escaped (`'` → `''`) before interpolation.
* `cli_args` exists mainly so mssql-tools18 users can pass `-C` (trust server certificate).

**The generated job step** is a T-SQL cursor over `master.sys.databases`, filtered to
`state = 0` (online) and `is_in_standby = 0` (not a log-shipping secondary), issuing
`BACKUP DATABASE|LOG … WITH COMPRESSION, NOFORMAT, NOINIT, SKIP, NOREWIND, NOUNLOAD, STATS=10`.
The `\r` line endings in the template are deliberate — they make the step render readably in SSMS.

**Semantics worth remembering:**

| Thing | Behaviour |
|---|---|
| `rotate` | **Days, not generations.** `> 0` appends `_YYYYMMDD_HHMMSS` to filenames and adds `xp_delete_file` + `sp_delete_backuphistory` pruning older than N days. `0` disables pruning entirely and drops the date suffix. The role passes `mssql_backup_count` (default 14) into it. |
| system DBs | `master`, `model`, `msdb`, `tempdb` are unioned into `exclude` in `main()` unconditionally. The only way to back them up is to name them in `include` — `include` and `exclude` are mutually exclusive (if `include` is non-empty, `exclude` is ignored). |
| `per_database` | Default `true`; writes to `<path>/<dbname>/…` instead of flat. |
| extensions | `.bak` for full, `.trn` for logs. |
| `state` | **Only `present` is implemented.** `absent`, `enabled` and `disabled` are accepted by the argspec and then `fail_json("… not implemented")`. |

---

## 4. The 2026-06-18 modernization (the only substantial recent work)

Four commits on one day, all by Fabian, rewriting ~350 of the module's lines. Reconstructed
intent, in order:

1. **`9485598`** — ansible-core 2.20 compatibility groundwork: condition checks, YAML hygiene,
   FQCN/module usage.
2. **`dfac74e`** — the big one, "Modernize … and harden security":
   * dropped the shipped insecure default for `mssql_admin_password` — it is now the caller's job
     to supply it (Vault). README says so explicitly.
   * moved the password to `SQLCMDPASSWORD`.
   * added `cli_path` auto-detection and `cli_args` for mssql-tools18 / `-C`.
   * added `supports_check_mode=True` with a real `diff` list — every managed object (job, step,
     schedule, attachment, jobserver) contributes a before/after entry.
   * made `rotate: 0` mean "no pruning" rather than an undefined state.
3. **`1e4a856`** — two idempotency fixes that are easy to reintroduce by accident:
   * `mssql_server` now derives from `ansible_facts['default_ipv4']['address']` with a fallback to
     `ansible_facts['all_ipv4_addresses'][0]`, instead of the bare `ansible_default_ipv4` magic var.
   * **diff normalization.** `result_filter()` strips and rejoins the SQL it reads back from
     `sysjobsteps`, so `backup_step_exists()` compares a likewise-normalised copy of the desired
     SQL (`self.step_desired`). `schedule_exists()` does the same for schedules: SQL Server stores
     `freq_interval` as `0` when `freq_type = 1` (once), `freq_subday_interval` as `0` when
     subday type is `specific`, and `active_start_time` with leading zeros stripped — all three are
     normalised on the requested side before comparing. **Without this the role reports `changed`
     on every run.** If you touch either comparison, re-check idempotency against a real instance.
4. **`2da7540`** — `.gitignore` gained `library/__pycache__/`.

---

## 5. Open threads and rough edges

None of these are broken in production; they are the gaps a future session will trip over.

* **Molecule scenario is thoroughly stale.** It targets CentOS 7 and Ubuntu 16.04 images, installs
  SQL Server 2017 via `robertdebock.mssql` with hardcoded xenial repos, and its verification
  command hardcodes `/opt/mssql-tools/bin/sqlcmd` and `-P` — i.e. it exercises neither the
  mssql-tools18 path nor the `SQLCMDPASSWORD` change from `dfac74e`. `molecule/requirements.txt`
  pins nothing. The testing story did not get modernized along with the module.
* **Version metadata contradicts the work.** `meta/main.yml` says `min_ansible_version: "2.14"` and
  lists Ubuntu **xenial** as the only platform, while the commits say "for ansible-core 2.20".
  The module docstring still says `version_added: "2.2"`.
* **`state` is half-implemented** (see §3). The argspec advertises four states and delivers one.
  The dead `backup.job_enabled()` / `job_disabled()` calls are still there, commented out.
* **`converge.yml` references the role as `ansible-role-mssql-global-backup`** while
  `meta/main.yml` declares `role_name: mssql_global_backup`.
* **`.vscode/settings.json` is untracked** (pins the Ansible extension's interpreter to
  `/usr/bin/python`). Either commit it or add `.vscode/` to `.gitignore` — right now it shows up
  as noise in every `git status`.
* **A stale `library/__pycache__/*.pyc` exists on disk.** It is gitignored and untracked, but it
  is a compiled copy of the module; harmless, just don't be confused by it.
* **`results` in the return payload** leaks raw `sysjobsteps` / `sysschedules` rows into the task
  output on every run. Useful while debugging idempotency, noisy otherwise — worth a decision.

---

## 6. Conventions carried over from the sibling repos

These are not documented in this repo but hold consistently across all six project directories in
the local history, and one is recorded memory:

* **Commit messages:** Conventional-Commit prefix (`feat:` / `fix:` / `refactor:` / `chore:`),
  one line, occasionally two. Asked for at the end of nearly every session. This repo's own last
  four commits follow it.
* **Comments stay short.** One to two lines, dropped when redundant. Requested repeatedly and in
  every repo.
* **Pragmatic scope** — recorded memory (`feedback-pragmatic-scope`, from
  `on-and-offboarding-automation`): when a change exists only to make two things symmetrical
  rather than to fix a real gap, surface it as an optional follow-up instead of building it.
  Directly relevant here: the unimplemented `state` values are a real gap; the stale
  `version_added` string is not.
* **`.yml` over `.yaml`** in Ansible content — holds in this repo already.
* **Verify against reality, not against the diff.** The 2026-06-18 idempotency fixes are exactly
  the class of bug a `--check -D` run catches and code reading does not.

---

## 7. If you pick this repo up again

The highest-value next steps, roughly in order:

1. Decide what `molecule/` should be. Either update it (modern base images, SQL Server 2022,
   mssql-tools18, `SQLCMDPASSWORD`, pinned requirements) or delete the scenario and say in the
   README that testing is manual. A test suite that cannot exercise the current code path is worse
   than none.
2. Reconcile `meta/main.yml` with reality: `min_ansible_version`, supported platforms.
3. Decide on `state: absent` — implement `sp_delete_job` or remove the choice from the argspec so
   the module stops advertising something it refuses to do.
4. Resolve `.vscode/` one way or the other.
5. Write memories as you go — this file exists because there were none.
