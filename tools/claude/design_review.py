import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini import ask
# usage: design_review.py <task.md> <out.json> before1.jpg ... -- after1.jpg ...
task, out = sys.argv[1], sys.argv[2]; rest = sys.argv[3:]
if '--' in rest: i = rest.index('--'); before, after = rest[:i], rest[i+1:]
else: before, after = [], rest
rules = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'claude', 'DESIGN_RULES.md'), encoding='utf-8').read()
P = f"""You are a senior product designer reviewing an investor demo of a city digital twin (Unity UI Toolkit, dark qTwin style).
The owner said the UI has too much text, is hard to read, and he does not know where to look. The target design rules:
{rules}
Context of the change under review:
{open(task, encoding='utf-8').read()}
BEFORE screenshots (may be empty): {', '.join(os.path.basename(b) for b in before) or 'none'}.
AFTER screenshots: {', '.join(os.path.basename(a) for a in after)}.
Judge the AFTER screens: can a busy investor get the point of each panel in 3 seconds? Is there one clear focal point per block? Is any prose longer than one line visible without a click? Duplicated facts? Jargon labels? Colour used only for status? Clipped/overlapping/touching text, awkward wraps, misalignment, untranslated text on EN/KZ screens, contradictory numbers, missing source/model chips?
Return JSON: {{"verdict":"pass|fail","clarity_before":0-10,"clarity_after":0-10,"issues":[{{"severity":"blocker|major|minor","screenshot":"...","where":"panel/block","problem":"...","fix":"..."}}]}}. Fail if any blocker or major."""
res = ask('gemini-4-argon', P, images=before + after, json_out=True, thinking='high')
open(out, 'w', encoding='utf-8').write(res); print(res[:6000])
