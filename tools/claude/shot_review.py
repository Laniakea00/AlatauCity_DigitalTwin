import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini import ask
task, out = sys.argv[1], sys.argv[2]; imgs = sys.argv[3:]
P = f"""You are a strict UI/UX and data-presentation reviewer for an investor demo of a city digital twin (Unity UI Toolkit, dark qTwin style, 1920x1080 screenshots).
Context of the change under review:
{open(task, encoding='utf-8').read()}
Screenshots (in order): {', '.join(os.path.basename(i) for i in imgs)}.
Find concrete VISIBLE problems only: clipped/overlapping/touching text, titles running into subtitles, untranslated Russian text on EN/KZ screens, wrong or contradictory numbers/sentences (e.g. "X instead of X"), awkward wraps, inconsistent alignment, clutter, missing source/model tags on numbers, anything that would embarrass the seller in front of an investor. Ignore 3D graphics quality.
Return JSON: {{"verdict":"pass|fail","issues":[{{"severity":"blocker|major|minor","screenshot":"...","where":"panel/block","problem":"...","fix":"..."}}]}}. Fail if any blocker or major."""
res = ask('gemini-4-argon', P, images=imgs, json_out=True, thinking='high')
open(out, 'w', encoding='utf-8').write(res); print(res[:6000])
