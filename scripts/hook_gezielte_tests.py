"""PostToolUse-Hook: nach einem Edit nur die Tests zum geaenderten Modul laufen lassen.

Die ganze Suite (3000+ Tests) dauert weit laenger als das Hook-Timeout und
laeuft in CI. Hier: bearbeiteter Test -> genau diese Datei; bearbeitetes
src/.../modul.py -> tests/test_modul*.py; sonst nichts.
"""
import glob
import json
import os
import subprocess
import sys

try:
    pfad = json.load(sys.stdin).get("tool_input", {}).get("file_path", "") or ""
except Exception:
    sys.exit(0)

name = os.path.splitext(os.path.basename(pfad))[0]
if "/tests/test_" in pfad and pfad.endswith(".py"):
    ziele = [pfad]
elif "/src/" in pfad and pfad.endswith(".py"):
    ziele = sorted(glob.glob(f"tests/test_{name}*.py"))
else:
    ziele = []
if not ziele:
    sys.exit(0)
env = {**os.environ, "PYTHONPATH": "src"}
lauf = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", *ziele],
                      env=env, capture_output=True, text=True)
print("\n".join((lauf.stdout + lauf.stderr).strip().splitlines()[-15:]))
sys.exit(0)
