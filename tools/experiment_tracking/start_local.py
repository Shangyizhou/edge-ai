"""Start only local tracking/view servers; no model subprocesses."""
import json
import socket
import subprocess
from pathlib import Path

from paths import DEFAULT_HOME
HOME = DEFAULT_HOME
commands = {
    5001: [str(HOME / 'venv/bin/mlflow'), 'server', '--backend-store-uri', 'sqlite:///' + str(HOME / 'mlflow.db'), '--host', '127.0.0.1', '--port', '5001', '--workers', '1'],
    5002: [str(HOME / 'venv/bin/python'), '-m', 'http.server', '5002', '--bind', '127.0.0.1', '--directory', str(HOME / 'view')],
}
started = {}
for port, command in commands.items():
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} occupied; inspect existing service before starting')
for port, command in commands.items():
    with (HOME / f'server-{port}.log').open('a') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    started[str(port)] = proc.pid
(HOME / 'server-pids.json').write_text(json.dumps(started, indent=2))
print(json.dumps(started))
