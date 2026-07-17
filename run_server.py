#!/usr/bin/env python3
import sys
import os

_project_dir = os.path.dirname(os.path.abspath(__file__))

# The app's dependencies (FastAPI, SQLAlchemy, bcrypt, etc.) are installed in
# ./venv, not in the system python3. If this script wasn't launched with that
# venv's interpreter, re-exec with it instead of crashing on the first import —
# otherwise every API call in the browser fails with a generic "Failed to fetch"
# because the server process never actually started.
_venv_dir = os.path.join(_project_dir, "venv")
_venv_python = os.path.join(_venv_dir, "bin", "python3")
# venv/bin/python3 is usually a symlink to the same base interpreter binary as
# the system python3, so comparing realpath(sys.executable) never detects the
# difference — compare sys.prefix instead, which venv activation actually changes.
if os.path.exists(_venv_python) and os.path.realpath(sys.prefix) != os.path.realpath(_venv_dir):
    os.execv(_venv_python, [_venv_python] + sys.argv)

# Add current directory to path
sys.path.insert(0, _project_dir)

# Now import and run uvicorn
import uvicorn
from api.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)