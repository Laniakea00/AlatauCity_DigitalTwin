# Offline fixes of the base maps and a hide list:
#  1. reclaimed land (master-plan islands/embankments) under planned buildings that the plan raster leaves on water -> map_plan + map_dev
#  2. existing buildings that the wide raster river covers -> a land patch in map_plan and map_nature
#  3. isolated generated buildings on water -> hidden (code 1)
#  4. buildings standing on a road carriageway -> hidden (generated/master plan: always; existing: from the road's year)
import numpy as np, csv, struct, json, shutil
from PIL import Image
from scipy import ndimage as ndi
Image.MAX_IMAGE_PIXELS=None
O='/home/claude/alatau/orig/map/'; R='/home/claude/alatau/UnityProject/Assets/Resources/'; D='/home/claude/alatau/data/'
plan=np.asarray(Image.open(O+'map_plan.png').convert('RGB')).copy(); nat=np.asarray(Image.open(O+'map_nature.png').convert('RGB')).copy()
devI=Image.open(O+'map_dev.png'); dev=np.asarray(devI).copy()
H,W=plan.shape[:2]; dh,dw=dev.shape
def wm(img):
    f=img.astype(np.float32)/255
    return np.clip((f[...,2]-f[...,0]-0.10)*8,0,1)*np.clip((f[...,2]-f[...,1]-0.03)*25,0,1)
pw,nw=wm(plan)>0.5, wm(nat)>0.5
def UV(x,z): return 2.29357798e-5*np.asarray(x)+0.5, 1.62074554e-5*np.asarray(z)+0.491085899
def PX(x,z):
    u,v=UV(x,z); return u*W,(1-v)*H
mpp=1/(2.29357798e-5*W)   # metres per plan pixel (x)
bb=open(R+'Landmarks/bid_bounds.bytes','rb').read(); N=struct.unpack('<i',bb[4:8])[0]; B=np.frombuffer(bb[8:8+N*16],dtype='<f4').reshape(N,4)
rows=list(csv.DictReader(open(D+'buildings.csv')))
info={int(r['bid']):r for r in rows}
roads=json.load(open(D+'roads.json'))['edges']
hide={}
def box_px(bid,pad):
    x0,z0,x1,z1=B[bid]; a0,b1=PX(x0-pad,z0-pad); a1,b0=PX(x1+pad,z1+pad)
    return int(np.floor(b0)),int(np.ceil(b1)),int(np.floor(a0)),int(np.ceil(a1))
# ---- 1+3: planned buildings on water
onw=[]
for bid,r in info.items():
    if bid>=N or B[bid,2]<=B[bid,0] or r['source']=='existing_osm': continue
    px,py=PX(float(r['x']),float(r['z'])); px,py=int(px),int(py)
    if 0<=px<W and 0<=py<H and pw[py,px]: onw.append(bid)
print('planned on water',len(onw))
pts=np.array([[float(info[b]['x']),float(info[b]['z'])] for b in onw])
# clusters within 150 m
from scipy.spatial import cKDTree
t=cKDTree(pts); pairs=t.query_pairs(150)
par=list(range(len(onw)))
def f(i):
    while par[i]!=i: par[i]=par[par[i]]; i=par[i]
    return i
for i,j in pairs: par[f(i)]=f(j)
cl={}
for i in range(len(onw)): cl.setdefault(f(i),[]).append(i)
land=np.zeros((H,W),bool); yearpx=np.full((H,W),9999,np.int32)
for k,mem in cl.items():
    if len(mem)<6:
        for i in mem: hide[onw[i]]=1
        continue
    yr=min(int(info[onw[i]]['year']) for i in mem)
    m=np.zeros((H,W),bool)
    for i in mem:
        r0,r1,c0,c1=box_px(onw[i],22); m[max(r0,0):r1,max(c0,0):c1]=True
    # roads that run over this cluster's water
    cp=pts[mem]; lo=cp.min(0)-300; hi=cp.max(0)+300
    for e in roads:
        g=np.array(e['g'],float).reshape(-1,2)
        if g[:,0].max()<lo[0] or g[:,0].min()>hi[0] or g[:,1].max()<lo[1] or g[:,1].min()>hi[1]: continue
        half={'highway':11,'ring':9,'main':11,'street':7}[e['c']]+10
        for a,b in zip(g[:-1],g[1:]):
            n=max(2,int(np.hypot(*(b-a))/5))
            for s in np.linspace(0,1,n):
                p=a+(b-a)*s; x,y=PX(p[0],p[1]); rr=half/mpp
                m[max(int(y-rr),0):int(y+rr)+1,max(int(x-rr),0):int(x+rr)+1]=True
    # organic outline: close the gaps between the houses, round the corners
    m=ndi.binary_closing(m,structure=np.ones((3,3)),iterations=4)
    m=ndi.gaussian_filter(m.astype(np.float32),2.0)>0.45
    m&=pw
    land|=m; yearpx[m]=np.minimum(yearpx[m],yr)
    print('island',len(mem),'bld from',yr,'px',m.sum())
# land colour: the nearest land pixel of the plan, slightly paler (fresh embankment)
idx=ndi.distance_transform_edt(pw,return_distances=False,return_indices=True)
src=plan[idx[0],idx[1]]
plan[land]=np.array([205,178,124],np.uint8)   # residential/resort land of the plan: lawns between the houses
# map_dev: the reclaimed land appears a year before its first building
uu=np.linspace(0,H-1,dh).astype(int); vv=np.linspace(0,W-1,dw).astype(int)
for r in range(dh):
    row=land[uu[r]]
    if not row.any(): continue
for r in range(dh):
    r0=int(r*H/dh); r1=int((r+1)*H/dh)
    for c in range(dw):
        c0=int(c*W/dw); c1=int((c+1)*W/dw)
        blk=yearpx[r0:r1,c0:c1]; mn=blk.min()
        if mn<9999: dev[r,c]=max(int(mn)-2001,26) if dev[r,c]==0 else min(dev[r,c],max(int(mn)-2001,26))
# ---- 2: existing buildings on the raster river: a patch of land under them in both maps
nidx=ndi.distance_transform_edt(nw,return_distances=False,return_indices=True); nsrc=nat[nidx[0],nidx[1]]
cnt=0
for bid,r in info.items():
    if r['source']!='existing_osm' or bid>=N or B[bid,2]<=B[bid,0]: continue
    px,py=PX(float(r['x']),float(r['z'])); px,py=int(px),int(py)
    if not(0<=px<W and 0<=py<H) or not(pw[py,px] or nw[py,px]): continue
    r0,r1,c0,c1=box_px(bid,10); sl=(slice(max(r0,0),r1),slice(max(c0,0),c1))
    plan[sl]=np.where(pw[sl][...,None],src[sl],plan[sl]); nat[sl]=np.where(nw[sl][...,None],nsrc[sl],nat[sl]); cnt+=1
print('existing patched',cnt)
# ---- 4: buildings on a road carriageway
from collections import defaultdict
grid=defaultdict(list); G=200
for bid in range(N):
    x0,z0,x1,z1=B[bid]
    if x1<=x0: continue
    for gx in range(int(x0//G),int(x1//G)+1):
        for gz in range(int(z0//G),int(z1//G)+1): grid[(gx,gz)].append(bid)
half={'highway':11,'ring':9,'main':7.5,'street':4}
nroad=0
for e in roads:
    g=np.array(e['g'],float).reshape(-1,2); h=half[e['c']]; yr=e['y'][0] if e['y'] else 2025
    for a,b in zip(g[:-1],g[1:]):
        L=np.hypot(*(b-a))
        for s in np.linspace(0,1,max(2,int(L/4)+1)):
            p=a+(b-a)*s
            for bid in grid.get((int(p[0]//G),int(p[1]//G)),()):
                x0,z0,x1,z1=B[bid]; cx,cz=(x0+x1)/2,(z0+z1)/2; hw,hd=(x1-x0)*0.35,(z1-z0)*0.35   # the core of the footprint
                if abs(p[0]-cx)<hw+h*0.8 and abs(p[1]-cz)<hd+h*0.8:
                    r=info.get(bid)
                    if r is None: continue
                    if r['source']=='existing_osm':
                        if yr<=2025: continue
                        code=max(2,min(254,yr-2000))
                    else: code=1
                    if bid not in hide or code<hide[bid]: 
                        if bid not in hide: nroad+=1
                        hide[bid]=code
print('on roads',nroad,'hidden total',len(hide))
Image.fromarray(plan).save(R+'Map/map_plan.png',optimize=False)
Image.fromarray(nat).save(R+'Map/map_nature.png',optimize=False)
Image.fromarray(dev).save(R+'Map/map_dev.png')
with open(R+'Landmarks/hide_extra.bytes','wb') as fo:
    fo.write(b'HID1'); fo.write(struct.pack('<i',len(hide)))
    for k,v in sorted(hide.items()): fo.write(struct.pack('<iI',k,v))
