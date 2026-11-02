"""Gemini review of map frames for tester steps 5 and 8 (the owner-approved list). usage: map_review.py <context.md> <out.json> <frames...>"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini import ask
from PIL import Image
ctx, out = sys.argv[1], sys.argv[2]; frames = sys.argv[3:]
tmp = tempfile.mkdtemp(prefix='mr_')
imgs = []
for f in frames:
    p = os.path.join(tmp, os.path.basename(f).rsplit('.', 1)[0] + '.jpg')
    Image.open(f).convert('RGB').resize((1600, 900)).save(p, quality=88); imgs.append(p)
P = f"""You are the strict acceptance inspector of an urban plan rendered in a city digital twin (Unity, 1920x1080 frames; UI panels on the left/right are not under review, only the 3D city).
Context:
{open(ctx, encoding='utf-8').read()}
Frames in order: {', '.join(os.path.basename(i) for i in imgs)}.
STEP 5. On every frame look for exactly these defects: an object inside another object; a road running into a wall or into lawn; a tree, lamp, pole or stop standing on asphalt; a car not on a lane; a person not on a pavement; a floating or sunken object; identical houses side by side; empty grey ground; a car park hiding a facade; a bridge that rests on nothing; a window or facade repeating without a break longer than 60 m; a texture with a seam or stretch. For each defect give the frame name and the place on the frame (quarter of the frame and a landmark). If unsure, report it.
STEP 8. Write three sentences: what a resident sees stepping out of a house in a random block; what an investor sees from the main view; what a child sees on the way to school. Any "but" in a sentence is itself a defect.
Return JSON: {{"step5":[{{"frame":"...","where":"...","defect":"...","severity":"blocker|error|cosmetic"}}],"step8":["...","...","..."],"verdict":"accept|reject"}}. Reject if any blocker or error."""
res = ask('gemini-4-argon', P, images=imgs, json_out=True, thinking='high')
open(out, 'w', encoding='utf-8').write(res); print(res[:8000])
