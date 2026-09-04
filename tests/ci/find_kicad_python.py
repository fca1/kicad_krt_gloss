"""Find and probe KiCad's bundled Python, never substitute the runner Python."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
sites = sorted({str(p.parent) for p in root.rglob("pcbnew.py")})
candidates = sorted({str(p) for p in root.rglob("python3*")
                     if p.parent.name == "bin" and p.is_file()
                     and os.access(p, os.X_OK)})
print("KiCad Python candidates:", candidates, flush=True)
print("KiCad module directories:", sites, flush=True)
env = dict(os.environ, PYTHONPATH=os.pathsep.join(sites))
for candidate in candidates:
    probe = subprocess.run([candidate, "-c",
        "import pcbnew,wx,sys,platform; print(sys.version); "
        "print(platform.machine()); print(pcbnew.GetBuildVersion())"],
        env=env, text=True, capture_output=True)
    print(candidate, probe.returncode, probe.stdout, probe.stderr, flush=True)
    if probe.returncode == 0:
        with open(os.environ["GITHUB_ENV"], "a") as output:
            output.write(f"KICAD_PYTHON={candidate}\nKICAD_SITE={os.pathsep.join(sites)}\n")
        break
else:
    raise SystemExit("No working KiCad-bundled Python with pcbnew and wx")
