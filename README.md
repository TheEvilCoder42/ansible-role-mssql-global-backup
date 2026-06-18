# ansible-role-mssql-backup

An Ansible Role that helps manage Microsoft SQL Server Backup jobs

## Dependencies

A Microsoft SQL Server on Linux installation, with the `mssql-tools` or `mssql-tools18` package available on the host (provides `sqlcmd`).

## NOTES

As of SQL Server 2019 on Linux, it is not currently possible to use `xp_cmdshell`, nor utilize the Maintenance Plan features available on a Windows installation of SQL Server.

## Role Variables

Available variables are listed below, along with default values (see `defaults/main.yml`):

    mssql_server: "{{ ansible_facts['default_ipv4']['address'] }}"
    mssql_port: 1433

The address and port to use when connecting to the mssql server

    mssql_admin_user: sa

The administrative user of the mssql server. `mssql_admin_password` must be provided by you (for example via Ansible Vault) — no insecure default is shipped.

    mssql_home: /var/opt/mssql
    mssql_user: mssql
    mssql_group: mssql

The mssql user definition, used for ownership of the backup directory.

    mssql_backup_path: /var/opt/mssql/backups

The path to where the backups should be stored

    mssql_backup_count: 14

How many days of backups to keep. The SQL Agent job prunes backup files older than this many days. Set to `0` to disable pruning and keep all backups.

    mssql_schedule_type: daily
    mssql_schedule_interval: 1
    mssql_schedule_start_time: '003000'

What time to run the schedule at, default is set to 12:30 am

Available Schedule types: `once`, `daily`, `weekly`, `monthly`, `onstart`, `idle`

    mssql_logs_schedule_type: daily
    mssql_logs_schedule_interval: 1
    mssql_logs_schedule_subday_type: hours
    mssql_logs_schedule_subday_interval: 1
    mssql_logs_schedule_start_time: '000000'

Schedule for the transaction-log backup job (defaults to hourly).

    # mssql_backup_cli_args: ['-C']

Extra arguments passed to `sqlcmd`. When using mssql-tools18 you typically need `-C` to trust the server certificate.

## Testing

Testing requires Molecule. 

## License

MIT / BSD

## Author Information

This role was created in 2020s by [David Lundgren](https://www.davidscode.com/).
