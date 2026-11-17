"""Run a kit script with local credentials loaded into the child process only.

    .venv/Scripts/python.exe tools/run_tool.py <script> [arguments]

<script> is a .py (run with this Python) or .mjs/.js (run with Node) file inside the repository's tools/ or
.agents/skills/, given relative to the kit root. Variables already set in the environment win over
local/secrets.env; nothing is written or printed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = (ROOT / 'tools', ROOT / '.agents/skills')

def load_env():
    env = os.environ.copy()
    file = ROOT / 'local/secrets.env'
    if file.exists():
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    # Vietnamese output crashes Python under the Windows cp1252 console default.
    env.setdefault('PYTHONUTF8', '1')
    return env

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Usage: run_tool.py <script> [arguments]')
    script = (ROOT / sys.argv[1]).resolve()
    if not script.is_file() or not any(base in script.parents for base in ALLOWED):
        sys.exit('Select a script file inside tools/ or .agents/skills/.')
    if script.suffix == '.py':
        command = [sys.executable, str(script)]
    elif script.suffix in ('.mjs', '.js'):
        node = shutil.which('node')
        if not node:
            sys.exit('Node.js not found. Run setup/setup.ps1 first.')
        command = [node, str(script)]
    else:
        sys.exit('Only .py, .mjs and .js scripts can be run.')
    sys.exit(subprocess.call(command + sys.argv[2:], env=load_env()))
