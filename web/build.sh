#!/bin/bash
# Build the single-file page and test it in Edge:  bash build.sh [notest]
#
# Needs Blender 5.x: it is used as Python with an image reader, nothing is rendered. If Blender is installed elsewhere:
#   BLENDER="/path/to/blender.exe" bash build.sh notest
# The Unity project is taken from ../UnityProject (set PROJECT to use another copy).
# The test needs a Python with playwright and the Edge browser: set PY (python) and PYLIBS (folder with playwright) if they differ.
cd "$(dirname "$0")"
HERE="$(pwd -W 2>/dev/null || pwd)"
BLENDER="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
PROJECT="${PROJECT:-$HERE/../UnityProject}"
"$BLENDER" -b --factory-startup --python build_web.py -- "$PROJECT" "$HERE/lib/three.min.js" "$HERE/AlatauCity_Film_3D.html" 2>&1 | grep -E "\.html:|Error|Traceback|line [0-9]|site bridge" | cut -c1-300
[ "$1" = "notest" ] && exit 0
PY="${PY:-/c/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe}"
export PYTHONIOENCODING=utf-8 PYTHONPATH="${PYLIBS:-C:/Users/daniy/Downloads/Alatau_City/_pylibs}"
"$PY" test_page.py AlatauCity_Film_3D.html shots 2>&1 | tail -60 | cut -c1-1200
