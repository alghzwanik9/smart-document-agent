"""Root entrypoint for Streamlit Community Cloud and standalone deployments."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"

for p in (str(FRONTEND), str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Change current working directory to frontend so views/ and components/ resolve
os.chdir(str(FRONTEND))

# Load and execute frontend/app.py
app_file = FRONTEND / "app.py"
with open(app_file, "r", encoding="utf-8") as f:
    code = compile(f.read(), str(app_file), "exec")
    exec(code, globals(), locals())
