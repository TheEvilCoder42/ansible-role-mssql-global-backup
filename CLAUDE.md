# CLAUDE.md

Ansible role managing SQL Server Agent backup jobs on **SQL Server for Linux** (no
`xp_cmdshell`, no Maintenance Plans). All real logic lives in the custom module
`library/mssql_global_backup.py`, which shells out to `sqlcmd`. `tasks/main.yml` just calls it
twice — once `type: full`, once `type: logs`.

## Before touching the module

**Idempotency is fragile and cannot be verified by reading the diff.**
`backup_step_exists()` and `schedule_exists()` compare the desired state against values read back
from `msdb`, normalised on *both* sides: `result_filter()` strips and rejoins the stored SQL, and
SQL Server stores `freq_interval` as `0` when `freq_type=1`, `freq_subday_interval` as `0` when
the subday type is `specific`, and `active_start_time` with leading zeros stripped. Break either
comparison and the role silently reports `changed` on every run. **Verify with a real
`--check -D` run against an instance, not by inspecting the code.**

**`molecule/` cannot validate current behaviour.** The scenario targets CentOS 7 / Ubuntu 16.04
and SQL Server 2017, and its check hardcodes `/opt/mssql-tools/bin/sqlcmd` and `-P` — so it
exercises neither the mssql-tools18 path nor `SQLCMDPASSWORD`. "Molecule passes" is not evidence
here. Say so rather than implying the change is tested.

## Semantics that are easy to get wrong

- `rotate` is **days, not generations**. `0` means *no pruning at all* (and drops the date suffix
  from filenames), not *keep none*.
- `master`, `model`, `msdb`, `tempdb` are unioned into `exclude` unconditionally in `main()`. The
  only way to back one up is to name it in `include`.
- `include` and `exclude` are **mutually exclusive** — a non-empty `include` makes `exclude` dead.
- Only `state: present` is implemented. `absent` / `enabled` / `disabled` are in the argspec and
  then `fail_json`. Don't assume an argspec choice works.

## Constraints

- `sqlcmd` is the only transport. Do not introduce `pymssql` / `pyodbc`.
- The password goes through the `SQLCMDPASSWORD` env var, never `-P` on the command line, and
  `login_password` is `no_log`. **Never reintroduce a default password** — it was deliberately
  removed; callers supply it via Vault.
- The `\r` line endings in the generated T-SQL are deliberate: they make the job step render
  readably in SSMS.
- `.yml`, not `.yaml`.

See `REPO-CONTEXT.md` for history, reconstructed design intent and open threads.
