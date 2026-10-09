"""Airport access (concept): the genplan street corridor from the Almaty–Konaev highway interchange to the airfield opens with the
airport (2034) and the part outside the city becomes a main road; a new spur leads to the airport plot. The LRT branch to Growing
is extended to an airport station. Writes StreamingAssets/twin/roads.json and Resources/Landmarks/lrt_routes.json.
Run from anywhere: python3 airport_access.py <orig roads.json> <orig lrt_routes.json> <unity project root>"""
import json, sys, heapq, math, numpy as np
src_roads, src_lrt, root = sys.argv[1:4]
r = json.load(open(src_roads)); N = r['nodes']; E = r['edges']
OPEN = 2034
AIR = dict(x=-5900.0, z=8300.0, yaw=30.0, w=1600.0, d=3800.0)
a = math.radians(AIR['yaw']); UX = np.array([math.cos(a), -math.sin(a)]); UZ = np.array([math.sin(a), math.cos(a)]); C0 = np.array([AIR['x'], AIR['z']])
def world(x, z): return C0 + UX * x + UZ * z

# 1. corridor: shortest path from the highway interchange (main road end, node 8113) to the airfield street (node 5074)
adj = {}
for i, e in enumerate(E):
    adj.setdefault(e['a'], []).append((e['b'], i)); adj.setdefault(e['b'], []).append((e['a'], i))
def sp(s, t):
    D = {s: 0}; P = {}; pq = [(0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == t: break
        if d > D[u]: continue
        for v, i in adj.get(u, []):
            nd = d + E[i]['len'] * (50 if E[i]['c'] in ('highway', 'ring') else 1)
            if nd < D.get(v, 1e18): D[v] = nd; P[v] = (u, i); heapq.heappush(pq, (nd, v))
    out = []; u = t
    while u != s: u, i = P[u]; out.append(i)
    return out[::-1]
path = sp(8113, 5074) + [11159]                      # + the airfield street west to its end (node 10095)
for i in path:
    e = E[i]; e['y'] = [min(y, OPEN) for y in e['y']]
    gx = [e['g'][k] for k in range(0, len(e['g']), 2)]
    if max(gx) < -1200: e['c'] = 'main'              # outside the city grid: a main road (inside it the street stays a street)

# 2. spur: on west from node 10095, round a 140 m curve to the north at x = -7240 (west of the business park the plan puts south of
# the airfield in 2045–2050) and straight north into the plot's south-west gate; the model's own road takes over inside the plot
GX = -7240.0; R = 140.0
p0 = np.array(N[10095], float); zc = p0[1]
gate_z = None
c0, c1 = UX * -AIR['w'] / 2 + C0 - UZ * AIR['d'] / 2, UX * AIR['w'] / 2 + C0 - UZ * AIR['d'] / 2       # south edge of the plot (SW, SE corners)
gate_z = c0[1] + (GX - c0[0]) / (c1[0] - c0[0]) * (c1[1] - c0[1])
pts = [p0]
for x in np.arange(p0[0] - 40, GX + R, -40): pts.append(np.array([x, zc]))
for k in range(0, 13):
    f = math.radians(k * 7.5); pts.append(np.array([GX + R - R * math.sin(f), zc + R - R * math.cos(f)]))
for z in np.arange(zc + R + 40, gate_z + 20, 40): pts.append(np.array([GX, z]))
pts.append(np.array([GX, gate_z + 20]))
g = []
for p in pts: g += [round(float(p[0]), 1), round(float(p[1]), 1)]
L = sum(float(np.hypot(*(pts[k] - pts[k - 1]))) for k in range(1, len(pts)))
nid = len(N); N.append([round(GX), round(float(gate_z + 20))])
E.append({'a': 10095, 'b': nid, 'c': 'main', 'len': round(L), 'g': g, 'y': [OPEN] * 4})
q3 = pts[-1]
print('gate local', round(float((np.array([GX, gate_z]) - C0) @ UX)), round(float((np.array([GX, gate_z]) - C0) @ UZ)))
r['version'] += ' · airport access'
json.dump(r, open(root + '/Assets/StreamingAssets/twin/roads.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print('corridor edges', len(path), 'main', sum(1 for i in path if E[i]['c'] == 'main'), 'spur m', round(L), 'end', q3.round())

# 3. LRT: the Growing branch goes on north to the airport station (landside, east of the forecourt)
lrt = json.load(open(src_lrt))
wg = next(x for x in lrt['routes'] if x['name'] == 'west_growing'); P = wg['pts']
end = np.array(P[-2:]); st = world(190, -1000); tip = world(190, -1000) + (st - end) / np.linalg.norm(st - end) * 60
n = int(np.linalg.norm(tip - end) / 72.5)
for k in range(1, n + 1):
    p = end + (tip - end) * k / n; P += [round(float(p[0]), 1), round(float(p[1]), 1)]
lrt['stations'] = [{'name': 'Аэропорт', 'x': round(float(st[0]), 1), 'z': round(float(st[1]), 1), 'phase': 1}]
json.dump(lrt, open(root + '/Assets/Resources/Landmarks/lrt_routes.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print('lrt +', n, 'pts to', tip.round(), 'station', st.round())
