#!/usr/bin/python3

# Copyright (c) 2020 David Lundgren

DOCUMENTATION = '''
---
module: mssql_global_backup
short_description: Manages a global backup job
description:
    - This will create a SQL Agent job that backs up all databases on the server
version_added: "2.2"
author: David Lundgren (@dlundgren)
options:
    name:
        description:
            - Name of the backup job
        type: str
        required: true
    state:
        description:
            - Whether or not the backup job should be absent or present
            - Use I(enabled) to turn the job on if disabled
            - Use I(disabled) to turn the job off if enabled
        type: str
        default: "present"
        choices: [ present, absent, enabled, disabled ]
    path:
        description:
            - Path to use instead of C(/var/opt/mssql/backups)
        type: str
        default: "/var/opt/mssql/backups"
    type:
        description:
            - Use I(full) to do a full backup
            - Use I(logs) to do a transaction log backup
        required: false
        type: str
        default: "full"
        choices: [ full, logs ]
    per_database:
        description:
            - Whether or not to store database backups in their own folders
        required: false
        type: bool
        default: true
    rotate:
        description:
            - Number of backups to keep
            - If I(rotate > 0) then the backup file names will appended with the date
            - If I(rotate = 0) rotation is disabled and old backups are not pruned
        required: false
        type: int
        default: 0
    schedule_type:
        description:
            - Type of schedule to use
        type: str
        required: false
        default: daily
        choices: [ once, daily, weekly, monthly, onstart, idle ]
    schedule_interval:
        description:
            - Interval of the schedule
            - Ignored when I(schedule_type=once)
        required: false
        type: int
        default: 1
    schedule_start_time:
        description:
            - Start time of the backup job
            - Use 24 hour time
            - Use I(HHMMSS) format, include any leading I(0) to pad it out I(003000) for 12:30 am
        required: false
        default: "000000"
    schedule_subday_type:
        description:
            - Type of subday schedule to use
        required: false
        type: str
        default: specific
        choices: [ specific, seconds, minutes, hours ]
    schedule_subday_interval:
        description:
            - Interval of subday type
            - Ignored when I(schedule_subday_type=specific)
            - Should be longer than 10 when I(schedule_subday_type=seconds)
        required: false
        type: int
        default: 0
    include:
        description:
            - List of databases to include
        required: false
        type: list
        elements: str
        default: []
    exclude:
        description:
            - List of databases to exclude
            - I(master), I(model), I(msdb), I(tempdb) are always excluded, use I(include) to include them
        required: false
        type: list
        elements: str
        default: []
    login_server:
        description:
            - The TDS server address or hostname of the instance
        type: str
        required: false
        default: localhost
    login_port:
        description:
            - The TDS port of the instance
        required: false
        type: int
        default: 1433
    login_name:
        description:
            - The name of the user to log in to the instance
        type: str
        required: true
    login_password:
        description:
            - The password of the user to log in to the instance
        type: str
        required: true
    cli_path:
        description:
            - Full path to the C(sqlcmd) executable
            - If not set, common locations are auto-detected (mssql-tools18 then mssql-tools), falling back to C(sqlcmd) on PATH
        required: false
        type: str
    cli_args:
        description:
            - Additional arguments to pass to C(sqlcmd)
            - For mssql-tools18 you typically need C(-C) to trust the server certificate
        required: false
        type: list
        elements: str
        default: []
notes:
    - Requires the mssql-tools or mssql-tools18 package on the remote host.
requirements:
    - python >= 3
    - mssql-tools or mssql-tools18
'''.replace('\t', '  ')

EXAMPLES = '''
# Backup all user databases
- mssql_global_backup:
    name: all user databases
    login_name: sa
    login_password: password
# backup all databases
- mssql_global_backup:
    name: all databases
    login_name: sa
    login_password: password
    include:
      - master
      - model
      - msdb
      - tempdb
# backup all user databases except northwind
- mssql_global_backup:
    name: all user databases except northwind
    exclude:
      - northwind
    login_name: sa
    login_password: password 
# Custom schedule (start the backup at 12:30 am)
- mssql_global_backup:
    name: all user databases on custom schedule
    schedule_type: daily
    schedule_start_time: '003000'
    login_name: sa
    login_password: password
'''.replace('\t', '  ')

RETURN = '''
name:
    description: The name of the backup that was managed
    returned: success
    type: str
    sample: foo
state:
    description: The requested state of the resource
    returned: success
    type: str
    sample: present
changed:
    description: Whether a change was made (or would be made in check mode)
    returned: success
    type: bool
    sample: true
'''.replace('\t', '  ')

from tempfile import NamedTemporaryFile
from ansible.module_utils.basic import AnsibleModule
import subprocess
import os
import shutil

def resolve_cli_path(cli_path):
    if cli_path:
        return cli_path
    for candidate in ('/opt/mssql-tools18/bin/sqlcmd', '/opt/mssql-tools/bin/sqlcmd'):
        if os.path.exists(candidate):
            return candidate
    return shutil.which('sqlcmd')

def _sqlcmd_argv(cli_path, cli_args, login_server, login_port, login_name, tail):
    return [cli_path] + list(cli_args) + [
        '-S',
        "{0},{1}".format(login_server, login_port),
        '-U',
        login_name,
        '-d',
        'msdb',
        '-b',
    ] + tail

def sqlresults(cli_path, cli_args, login_server, login_port, login_name, login_password, command):
    env = dict(os.environ, SQLCMDPASSWORD=login_password)
    argv = _sqlcmd_argv(cli_path, cli_args, login_server, login_port, login_name,
                        ['-s,', '-y0', '-Q', 'SET NOCOUNT ON; %s' % command])
    return subprocess.check_output(argv, env=env).decode()

def sqlfile(cli_path, cli_args, login_server, login_port, login_name, login_password, command):
    env = dict(os.environ, SQLCMDPASSWORD=login_password)
    argv = _sqlcmd_argv(cli_path, cli_args, login_server, login_port, login_name, ['-i', command])
    subprocess.check_call(argv, env=env)

def sqlcmd(cli_path, cli_args, login_server, login_port, login_name, login_password, command):
    env = dict(os.environ, SQLCMDPASSWORD=login_password)
    argv = _sqlcmd_argv(cli_path, cli_args, login_server, login_port, login_name, ['-Q', command])
    subprocess.check_call(argv, env=env)

def quoteName(name, quote_char):
    if quote_char == '[' or quote_char == ']':
        (quote_start_char, quote_end_char) = ('[', ']')
    elif quote_char == "'":
        (quote_start_char, quote_end_char) = ("N'", "'")
    else:
        raise Exception("Unsupported quote_char {0}, must be [ or ] or '".format(quote_char))

    return "{0}{1}{2}".format(quote_start_char, name.replace(quote_end_char, quote_end_char + quote_end_char), quote_end_char)

class BackupJob:
    def __init__(self, server, port, user, password, name, include, exclude, per_database, rotate, cli_path, cli_args):
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.name = name
        self.include = include
        self.exclude = exclude
        self.per_database = per_database
        self.rotate = rotate
        self.cli_path = cli_path
        self.cli_args = cli_args

        self.step_results = None
        self.step_desired = None
        self.schedule_results = None
        self.attach_results = None

        self.job_name = name
        self.schedule_name = 'ansible %s schedule' % self.name.lower()
        self.backup_step_name = 'ansible %s step' % self.name.lower()

    def result_filter(self, sql):
        data = [i.strip() for i in sqlresults(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password, sql).split("\n") if i]

        return data

    def job_exists(self):
        sql = "SELECT name FROM dbo.sysjobs WHERE name=%s" % quoteName(self.job_name, "'")
        return self.job_name in sqlresults(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password, sql).split("\n")

    def job_create(self):
        sql = """
            IF NOT EXISTS (
                SELECT name FROM dbo.sysjobs WHERE name={0}
            )
               EXEC sp_add_job @job_name={0}
            ;
        """.format(
            quoteName(self.job_name, "'")
        )
        sqlcmd(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password, sql)

    def backup_step_sql(self, type, path):
        # excludes: name NOT IN (excludes)
        # includes name IN (includes)
        databases = []
        if len(self.include) > 0:
            databases = [ quoteName(name, "'") for name in sorted(self.include) ]
            where = 'name IN (%s)'
        else:
            databases = [ quoteName(name, "'") for name in sorted(self.exclude) ]
            where = 'name NOT IN (%s)'

        if len(databases) == 0:
            raise Exception("missing databases: %s" % (','.join(databases)))

        safe_path = path.replace("'", "''")
        file_path = "'%s'" % safe_path
        if self.per_database:
            file_path = "'%s/' + @name" % safe_path

        file_name = "@name"
        if self.rotate > 0:
            file_name = "@name + '_' + @fileDate"

        backup_type = {
            'full': {'ext': 'bak', 'type': 'DATABASE'},
            'logs': {'ext': 'trn', 'type': 'LOG'}
        }
        ext = backup_type[type]['ext']

        # rotation by days: only prune when rotate > 0, otherwise rotation is disabled
        delete_decl = ''
        delete_exec = ''
        if self.rotate > 0:
            delete_decl = "DECLARE @deleteDate DATETIME = DATEADD(day, -%d, GETDATE());\r\n" % self.rotate
            delete_exec = (
                "EXEC master.sys.xp_delete_file 0, '%s', '%s', @deleteDate, 1;\r\n"
                "EXEC msdb.dbo.sp_delete_backuphistory @oldest_date = @deleteDate;\r\n"
            ) % (safe_path, ext)

        # the \r makes it nicely formatted in the database
        return """
DECLARE @name VARCHAR(50);\r
DECLARE @fileName VARCHAR(256);\r
DECLARE @fileDate VARCHAR(20);\r
{delete_decl}SET @fileDate = (Select Replace(Convert(nvarchar, GetDate(), 111), '/', '') + '_' + Replace(Convert(nvarchar, GetDate(), 108), ':', ''));\r
DECLARE db_cursor CURSOR READ_ONLY FOR\r
    SELECT name FROM master.sys.databases WHERE {where}\r
    AND state = 0 -- database is online\r
    AND is_in_standby = 0 -- database is not read only for log shipping;\r
OPEN db_cursor;\r
FETCH NEXT FROM db_cursor INTO @name;\r
WHILE @@FETCH_STATUS = 0\r
BEGIN\r
    SET @fileName = {file_path} + '/' + {file_name} + '.{ext}';\r
    BACKUP {btype} @name TO DISK=@fileName WITH COMPRESSION, NOFORMAT, NOINIT, SKIP, NOREWIND, NOUNLOAD, STATS=10;\r
    FETCH NEXT FROM db_cursor INTO @name;\r
END\r
{delete_exec}CLOSE db_cursor;\r
DEALLOCATE db_cursor;\r
GO
        """.format(
            delete_decl=delete_decl,
            where=where % (','.join(databases)),
            file_path=file_path,
            file_name=file_name,
            ext=ext,
            btype=backup_type[type]['type'],
            delete_exec=delete_exec
        )

    def backup_step_exists(self, type, path):
        sql = """
            SELECT command FROM dbo.sysjobsteps sjs JOIN dbo.sysjobs sj ON (sj.job_id = sjs.job_id)
                WHERE sj.name={0} AND sjs.step_name={1}
        """.format(
            quoteName(self.job_name, "'"),
            quoteName(self.backup_step_name, "'")
        )

        self.step_results = "\n".join(self.result_filter(sql))
        # result_filter() strips/joins lines, so compare a likewise-normalised
        # version of the desired SQL to keep the step idempotent
        self.step_desired = "\n".join(line.strip() for line in self.backup_step_sql(type, path).split("\n") if line.strip())
        return self.step_desired in self.step_results

    def backup_step_manage(self, type, path):
        self.step_manage(self.job_name, self.backup_step_name, 1, self.backup_step_sql(type, path))

        return self.backup_step_exists(type, path)

    def step_manage(self, job_name, step_name, step_id, command):
        sql = """
            IF NOT EXISTS (
                SELECT command FROM dbo.sysjobsteps sjs JOIN dbo.sysjobs sj ON (sj.job_id = sjs.job_id)
                WHERE sj.name={0} AND sjs.step_name={1} 
            )
                BEGIN
                    EXEC sp_add_jobstep 
                        @job_name = {0},
                        @step_name = {1},
                        @subsystem=N'TSQL',
                        @command={2},
                        @retry_attempts=5,
                        @retry_interval=1    
                END
            ELSE
                BEGIN
                    EXEC sp_update_jobstep 
                        @job_name = {0},
                        @step_id = {3}, 
                        @subsystem=N'TSQL',
                        @command={2},
                        @retry_attempts=5,
                        @retry_interval=1
                END
            ;
        """.format(
            quoteName(job_name, "'"),
            quoteName(step_name, "'"),
            quoteName(command, "'"),
            step_id
        )

        path = NamedTemporaryFile()
        path.close()
        with open(path.name, 'w+') as file:
            file.write(sql)

        sqlfile(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password, path.name)
        os.unlink(path.name)


    def schedule_exists(self, type, interval, subday_type, subday_interval, start_time):
        sql = "SELECT enabled,freq_type,freq_interval,freq_subday_type,freq_subday_interval,active_start_time FROM dbo.sysschedules WHERE name=%s" % quoteName(self.schedule_name, "'")
        results = self.result_filter(sql)

        # normalise the requested values the same way SQL Server stores them
        if type == '1':
            interval = 0
        if subday_type == '1':
            subday_interval = 0
        if start_time == '000000':
            start_time = '0'
        else:
            start_time = start_time.lstrip('0')

        self.schedule_results = results
        self.schedule_desired = ','.join(['1', type, '%d' % interval, subday_type, '%d' % subday_interval, start_time])

        return self.schedule_desired in results

    def schedule_manage(self, type, interval, subday_type, subday_interval, start_time):
        sql = """
            IF NOT EXISTS (
                SELECT * FROM dbo.sysschedules WHERE name={0}
            )
                BEGIN
                    EXEC dbo.sp_add_schedule
                        @schedule_name = {0},
                        @enabled = 1, 
                        @freq_type = {1},
                        @freq_interval = {2},
                        @freq_subday_type = {3},
                        @freq_subday_interval = {4},
                        @active_start_time = N'{5}'
                END
            ELSE
                BEGIN
                    EXEC dbo.sp_update_schedule
                        @name = {0},
                        @enabled = 1, 
                        @freq_type = {1},
                        @freq_interval = {2},
                        @freq_subday_type = {3},
                        @freq_subday_interval = {4},
                        @active_start_time = N'{5}'                    
                END
            ;
        """.format(
            quoteName(self.schedule_name, "'"),
            type,
            interval,
            subday_type,
            subday_interval,
            start_time
        )
        sqlcmd(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password, sql)

        return self.schedule_exists(type, interval, subday_type, subday_interval, start_time)


    def schedule_attached(self):
        sql = """
            SELECT sjs.job_id FROM dbo.sysjobschedules sjs 
                LEFT JOIN dbo.sysjobs sj ON (sj.job_id = sjs.job_id)
                LEFT JOIN dbo.sysschedules ss ON (ss.schedule_id = sjs.schedule_id)
                WHERE sj.name={0} and ss.name={1}
        """.format(
            quoteName(self.job_name, "'"),
            quoteName(self.schedule_name, "'")
        )

        self.attach_results = self.result_filter(sql)
        return len(self.attach_results) > 0

    def schedule_attach(self):
        sqlcmd(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password,"""
            EXEC sp_attach_schedule @job_name = {0}, @schedule_name = {1};
        """.format(
            quoteName(self.job_name, "'"),
            quoteName(self.schedule_name, "'")
        ))

        return self.schedule_attached()

    def jobserver_added(self):
        sql = """
            SELECT * FROM dbo.sysjobservers sjsrv LEFT JOIN dbo.sysjobs sj ON (sj.job_id = sjsrv.job_id)
            WHERE sj.name={0}
        """.format(
            quoteName(self.job_name, "'"),
        )

        self.attach_results = self.result_filter(sql)
        return len(self.attach_results) > 0

    def jobserver_add(self):
        sqlcmd(self.cli_path, self.cli_args, self.server, self.port, self.user, self.password,"""
            EXEC sp_add_jobserver @job_name = {0}, @server_name=N'(LOCAL)';
        """.format(
            quoteName(self.job_name, "'")
        ))

        return self.jobserver_added()


def main():
    schedule_types = {
        'once' : '1',
        'daily' : '4',
        'weekly' : '8',
        'monthly' : '16',
        'onstart' : '64',
        'idle' : '128'
    }

    schedule_subday_types = {
        'specific' : '1',
        'seconds' : '2',
        'minutes' : '4',
        'hours' : '8'
    }

    module = AnsibleModule(
        argument_spec = dict(
            name = dict(required = True),
            state = dict(default = 'present', choices=['absent','present','enabled','disabled']),
            path = dict(default = '/var/opt/mssql/backups'),
            type = dict(default = 'full', choices=['full','logs']),

            # rotation options
            per_database = dict(type='bool', default = True),
            rotate = dict(type='int', default = 0),

            # schedule
            schedule_type            = dict(default = 'daily', choices=list(schedule_types.keys())),
            schedule_interval        = dict(type='int', default = 1),
            schedule_start_time      = dict(default = '000000'),
            schedule_subday_type     = dict(default = 'specific', choices=list(schedule_subday_types.keys())),
            schedule_subday_interval = dict(type='int', default = 0),

            # database selection
            include = dict(type='list', elements='str', default = []),
            exclude = dict(type='list', elements='str', default = []),

            # login properties
            login_server   = dict(required = False, default = 'localhost'),
            login_port     = dict(type='int', required = False, default = 1433),
            login_name     = dict(required = True),
            login_password = dict(required = True, no_log = True),

            # cli options
            cli_path       = dict(type='str', required = False, default = None),
            cli_args       = dict(type='list', elements='str', required = False, default = [])
        ),
        required_if=[
            ['state', 'present', ['path']]
        ],
        supports_check_mode=True
    )

    cli_path = resolve_cli_path(module.params['cli_path'])
    if not cli_path:
        module.fail_json(msg="sqlcmd executable not found; set 'cli_path' or install mssql-tools/mssql-tools18")

    backup = BackupJob(
        module.params['login_server'],
        module.params['login_port'],
        module.params['login_name'],
        module.params['login_password'],
        module.params['name'],
        module.params['include'],
        set(['master', 'model', 'msdb', 'tempdb']) | set(module.params['exclude']),
        module.params['per_database'],
        module.params['rotate'],
        cli_path,
        module.params['cli_args']
    )

    check_mode = module.check_mode

    changed = False
    diff = []
    state = module.params['state']
    manage = True
    if backup.job_exists():
        if state == 'absent':
            module.fail_json(msg="delete not implemented")
        elif state == 'enabled':
            module.fail_json(msg="enable not implemented")
            # backup.job_enabled()
        elif state == 'disabled':
            module.fail_json(msg="disable not implemented")
            # backup.job_disabled()
    elif state == 'present':
        changed = True
        diff.append({
            'before_header': 'job: %s (absent)' % backup.job_name,
            'after_header': 'job: %s' % backup.job_name,
            'before': '',
            'after': "EXEC sp_add_job @job_name=N'%s';\n" % backup.job_name,
        })
        if not check_mode:
            backup.job_create()

    if manage is True:
        # manage the job step for backup
        type = module.params['type']
        path = module.params['path']
        if not backup.backup_step_exists(type, path):
            changed = True
            diff.append({
                'before_header': 'job step: %s' % backup.backup_step_name,
                'after_header': 'job step: %s' % backup.backup_step_name,
                'before': (backup.step_results or '') + '\n',
                'after': backup.step_desired + '\n',
            })
            if not check_mode:
                backup.backup_step_manage(type, path)

        # manage the schedule
        schedule_type = module.params['schedule_type']
        schedule_interval = module.params['schedule_interval']
        schedule_start_time = module.params['schedule_start_time']
        schedule_subday_type = module.params['schedule_subday_type']
        schedule_subday_interval = module.params['schedule_subday_interval']
        if not backup.schedule_exists(schedule_types[schedule_type], schedule_interval, schedule_subday_types[schedule_subday_type], schedule_subday_interval, schedule_start_time):
            changed = True
            diff.append({
                'before_header': 'schedule: %s' % backup.schedule_name,
                'after_header': 'schedule: %s' % backup.schedule_name,
                'before': '\n'.join(backup.schedule_results or []) + '\n',
                'after': backup.schedule_desired + '\n',
            })
            if not check_mode:
                backup.schedule_manage(schedule_types[schedule_type], schedule_interval, schedule_subday_types[schedule_subday_type], schedule_subday_interval, schedule_start_time)

        if not backup.schedule_attached():
            changed = True
            diff.append({
                'before_header': 'schedule attachment: %s' % backup.schedule_name,
                'after_header': 'schedule attachment: %s' % backup.schedule_name,
                'before': '',
                'after': "EXEC sp_attach_schedule @job_name=N'%s', @schedule_name=N'%s';\n" % (backup.job_name, backup.schedule_name),
            })
            if not check_mode:
                backup.schedule_attach()

        # manage the jobserver
        if not backup.jobserver_added():
            changed = True
            diff.append({
                'before_header': 'jobserver: %s' % backup.job_name,
                'after_header': 'jobserver: %s' % backup.job_name,
                'before': '',
                'after': "EXEC sp_add_jobserver @job_name=N'%s', @server_name=N'(LOCAL)';\n" % backup.job_name,
            })
            if not check_mode:
                backup.jobserver_add()

    results = {
        'changed': changed,
        'name' : module.params['name'],
        'state': state,
        'diff': diff,
        'results': [
            backup.step_results,
            backup.schedule_results,
            backup.attach_results
        ]
    }

    module.exit_json(**results)


if __name__ == '__main__':
    main()