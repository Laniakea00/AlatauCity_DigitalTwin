"""Extract centre-line segments of the master-plan transport ribbons + named sites from Alatau_City_3D.blend.
Unity frame: x = blend X (east), z = blend Y (north). Output: JSON with segments per layer and labelled points."""
import bpy, sys, json, math
blend, out = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=blend)

def ribbon_segments(ob):
    m = ob.data; mw = ob.matrix_basis  # hidden collections: matrix_world may be stale; no parents here
    V = [mw @ v.co for v in m.vertices]
    segs = []
    for p in m.polygons:
        vs = list(p.vertices)
        if len(vs) != 4: continue
        e = [(vs[i], vs[(i + 1) % 4]) for i in range(4)]
        L = [(V[a] - V[b]).length for a, b in e]
        # the two cross edges are opposite and shorter: pick the pair (0,2) or (1,3) with smaller sum
        pair = (0, 2) if L[0] + L[2] < L[1] + L[3] else (1, 3)
        mids = [(V[e[i][0]] + V[e[i][1]]) / 2 for i in pair]
        w = (L[pair[0]] + L[pair[1]]) / 2
        segs.append([round(mids[0].x, 1), round(mids[0].y, 1), round(mids[1].x, 1), round(mids[1].y, 1), round(w, 1), round((mids[0].z + mids[1].z) / 2, 1)])
    return segs

res = {"layers": {}, "points": [], "objects": []}
for ob in bpy.data.objects:
    res["objects"].append([ob.name, ob.type, [c.name for c in ob.users_collection]])
for name in ["Planned street axes", "LRT line", "Railways on the plan", "BAKAD ring road axis", "Planned bridges",
             "Highways", "Main roads", "Railways", "Rivers", "Runways"]:
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != 'MESH': print("skip", name); continue
    s = ribbon_segments(ob); res["layers"][name] = s; print(name, len(s), "segments")
for cname in ["Named sites of the plan", "Planned landmark buildings", "Existing settlements"]:
    c = bpy.data.collections.get(cname)
    for ob in c.all_objects:
        if ob.type != 'FONT': continue
        res["points"].append({"set": cname, "name": ob.name, "text": ob.data.body, "x": round(ob.location.x, 1), "z": round(ob.location.y, 1), "y": round(ob.location.z, 1)})
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("points", len(res["points"]))
