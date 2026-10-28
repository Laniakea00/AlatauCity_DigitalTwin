"""KAIST Kazakhstan from its QTwin monitoring page (QTwin_AlatauCity_Monitoring.html, the campus's geometry block): the BIM model of
the campus (6 buildings: 1 B1, 2 the main hall, 3 the laboratories, 4 the north block, 5 the sports core, 6 the park), the trees of
its park and the spots of its tower cranes. The page's geometry is in the Unity export format, i.e. already the local frame of the
KAIST landmark of the twin (x, y, z as LandmarkData's parts and TowerProfile.Kaist), so it is written as it is. Surface tags get +40,
so they never meet the tags of Iconic Complex in the shader (AlatauQTwin.cginc, KaistSurface).
Writes Resources/Landmarks/kaist_bim.bytes: "QKB1", mesh (positions, normals, facade u, tag, building, indices), trees (x, y, z,
size, kind) inside the plot, crane spots (x, y, z).
usage: python3 build_kaist.py kgeo.bin out_dir   (kgeo.bin: the gunzipped base64 block of the page)"""
import sys, struct
import numpy as np

src, out = sys.argv[1], sys.argv[2]
buf = open(src, 'rb').read(); o = 0
def i32():
    global o; v = struct.unpack_from('<i', buf, o)[0]; o += 4; return v
def take(dt, n):
    global o; a = np.frombuffer(buf, dtype=dt, count=n, offset=o).copy(); o += n * np.dtype(dt).itemsize; return a
def mesh():
    n = i32(); ni = i32()
    pos = take('<f4', n * 3).reshape(-1, 3); nrm = take('i1', n * 3).reshape(-1, 3)
    u = take('<f4', n); part = take('u1', n); tag = take('u1', n)
    nw = i32(); take('<f4', nw * 4); take('<u2', n); idx = take('<u4', ni)
    return dict(pos=pos, nrm=nrm, u=u, part=part, tag=tag, idx=idx)
ms = [mesh() for _ in range(4)]                  # the campus, the hoarding, a crane mast, a crane head (the twin has its own site)
ns = i32(); spots = take('<f4', ns * 3).reshape(-1, 3)
assert buf[o:o + 4] == b'GATE'; o += 4
mesh()                                           # the page's ground round the plot (the twin has its own city)
nt = i32(); trees = take('<f4', nt * 5).reshape(-1, 5)

m = ms[0]
tag = np.where(m['tag'] > 0, m['tag'].astype(np.int32) + 40, 0).astype(np.uint8)
inside = (np.abs(trees[:, 0]) < 206) & (np.abs(trees[:, 2]) < 176)
trees = trees[inside]
b = bytearray(b'QKB1')
b += struct.pack('<ii', len(m['pos']), len(m['idx']))
b += m['pos'].astype('<f4').tobytes() + m['nrm'].astype('i1').tobytes() + m['u'].astype('<f4').tobytes()
b += tag.tobytes() + m['part'].astype('u1').tobytes() + m['idx'].astype('<u4').tobytes()
b += struct.pack('<i', len(trees)) + trees.astype('<f4').tobytes()
b += struct.pack('<i', len(spots)) + spots.astype('<f4').tobytes()
open(out.rstrip('/') + '/kaist_bim.bytes', 'wb').write(b)
print('vertices', len(m['pos']), 'triangles', len(m['idx']) // 3, 'trees', len(trees), 'cranes', len(spots), 'bytes', len(b))
