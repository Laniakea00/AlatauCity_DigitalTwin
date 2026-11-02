"""Paths of the Stage 7 map pipeline. Override with environment variables when testing."""
import os

LIB = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(LIB)                                   # tools/map
REPO = os.path.dirname(os.path.dirname(MAP))
SPEC = os.path.join(MAP, "spec")
GEO = os.path.join(MAP, "geo")
OUT = os.environ.get("ALATAU_OUT", "/mnt/project-files/alatau_stage7/out")
TWIN = os.environ.get("ALATAU_TWIN", "/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets")
W34 = os.environ.get("ALATAU_W34", "/mnt/project-files/alatau_stage7/level0/w34")
DISTRICTS = ["gate", "golden", "green", "growing_w", "growing_e", "gate_trial"]


def out_dir(district, out=None):
    p = os.path.join(out or OUT, district)
    os.makedirs(p, exist_ok=True)
    return p


def out_file(district, name, out=None):
    return os.path.join(out_dir(district, out), name)


def spec_path(district):
    """spec/<district>.json; a path to a .json file is taken as it is (tests and stubs)."""
    if district.endswith(".json") and os.path.isfile(district):
        return os.path.abspath(district)
    return os.path.join(SPEC, f"{district}.json")


def district_id(district):
    """'tools/map/tests/stub_gate_trial.json' → 'stub_gate_trial'; 'gate' → 'gate'."""
    b = os.path.basename(district)
    return b[:-5] if b.endswith(".json") else b


def w34(*parts):
    return os.path.join(W34, *parts)


def twin(*parts):
    return os.path.join(TWIN, *parts)
