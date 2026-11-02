"""One district end to end (w43): network → LRT → land (w44, when its tools are here) → validator.

    python3 tools/map/run.py <district | path/to/spec.json> [--out OUT] [--no-land] [--no-png]

One line per step (what ran, how long, exit code). A generator that fails stops the run (the steps after it would read
stale files); the validator's exit code is the run's exit code (0 only without errors).
"""
import argparse
import os
import subprocess
import sys
import time

MAP = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(MAP, "gen")
STEPS = [("сеть дорог", "gen/gen_network.py"), ("ЛРТ", "gen/gen_lrt.py"),
         ("кварталы и участки (w44)", "gen/gen_blocks_lots.py"), ("здания (w44)", "gen/gen_buildings.py"),
         ("маски (w44)", "gen/gen_masks.py")]
LAND = {"gen/gen_blocks_lots.py", "gen/gen_buildings.py", "gen/gen_masks.py"}


def step(title, script, args, quiet=False):
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(MAP, script)] + args, capture_output=True, text=True)
    dt = time.time() - t0
    tail = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
    head = tail[0] if tail else ""
    print(f"[{'ok' if p.returncode == 0 else 'код ' + str(p.returncode)}] {title}: {dt:.1f} с — {head}")
    for ln in tail[1:] if not quiet else []:
        print("      " + ln)
    if p.returncode != 0 and p.stderr:
        for ln in p.stderr.strip().splitlines()[-8:]:
            print("      ! " + ln)
    return p.returncode, dt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("district")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-land", action="store_true", help="skip the w44 land steps")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args(argv)
    args = [a.district] + (["--out", a.out] if a.out else [])
    # w44's land tools take the district id and the spec file as --spec
    if a.district.endswith(".json"):
        land_args = [os.path.basename(a.district)[:-5], "--spec", os.path.abspath(a.district)] + (["--out", a.out] if a.out else [])
    else:
        land_args = args
    t0 = time.time()
    for title, script in STEPS:
        if script in LAND and (a.no_land or not os.path.exists(os.path.join(MAP, script))):
            print(f"[--] {title}: пропущено ({'--no-land' if a.no_land else 'нет ' + script})")
            continue
        rc, _ = step(title, script, land_args if script in LAND else args)
        if rc != 0:
            print(f"остановлено на шаге «{title}» (код {rc}); всего {time.time() - t0:.1f} с")
            return rc
    rc, _ = step("проверка (validate_map)", "validate/validate_map.py", args + (["--no-png"] if a.no_png else []))
    print(f"всего {time.time() - t0:.1f} с; проверка {'без ошибок' if rc == 0 else 'нашла ошибки (report.md)'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
