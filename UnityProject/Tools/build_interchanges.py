# Motorway interchanges for the film roads. The plan's road graph draws ramps as hundreds of tiny, doubled, broken edges, so
# ribbons along them look like scribbles. Here each interchange is rebuilt as clean, standard geometry:
#   1. the zone: a cluster of curved / very short motorway edges;
#   2. its motorway axes: the dominant directions of the motorway edges (weighted by length) and the line fitted to each;
#      the crossing point is the centre, an axis that runs on both sides of it gives two arms, otherwise one;
#   3. the graph edges along the axes stay (they are straight), every other motorway edge of the zone is dropped;
#   4. new ramps: in every quadrant between two neighbouring arms a loop (radius 60 m) tangent to both carriageways, when the
#      angle allows it, and an outer connector — a smooth curve from one arm to the other.
# Output Resources/Landmarks/interchanges.json: {"edges": [graph edges dropped], "paths": [{"y": [4 years], "g": [x, z, ...]}],
#   "zones": [[x, z, radius, year]] — the ground inside is a mown verge, not city yards}
import json, numpy as np, warnings
warnings.filterwarnings('ignore')
from collections import defaultdict
from scipy.spatial import cKDTree
D='/home/claude/alatau/data/'; R='/home/claude/alatau/UnityProject/Assets/Resources/'
E=json.load(open(D+'roads.json'))['edges']
G=[np.array(e['g'],float).reshape(-1,2) for e in E]
FAST=('highway','ring')
fast=[k for k,e in enumerate(E) if e['c'] in FAST and len(G[k])>=2]
def L(k): return np.hypot(*np.diff(G[k],axis=0).T).sum()
def turn(k):
    g=G[k]
    if len(g)<3: return 0.0
    d=np.diff(g,axis=0); a=np.arctan2(d[:,1],d[:,0]); return float(np.degrees(np.abs(np.angle(np.exp(1j*np.diff(a))))).sum())
seeds=[k for k in fast if turn(k)>20 or L(k)<25]
mids=np.array([G[k].mean(0) for k in seeds]); tr=cKDTree(mids)
par=list(range(len(seeds)))
def f(i):
    while par[i]!=i: par[i]=par[par[i]]; i=par[i]
    return i
for a,b in tr.query_pairs(150): par[f(a)]=f(b)
cl=defaultdict(list)
for i in range(len(seeds)): cl[f(i)].append(seeds[i])
allmid=np.array([G[k].mean(0) for k in fast]); ftr=cKDTree(allmid)
mains=[k for k,e in enumerate(E) if e['c']=='main' and len(G[k])>=2]
mmid=np.array([G[k].mean(0) for k in mains]); mtr=cKDTree(mmid)
def mainmid_q(lo,hi):
    ids=mtr.query_ball_point((lo+hi)/2, float(np.hypot(*(hi-lo))/2))
    return [mains[i] for i in ids if np.all((mmid[i]>=lo)&(mmid[i]<=hi))]
def segs_of(ks):
    P=[];V=[];W=[]
    for k in ks:
        g=G[k]
        for p,q in zip(g[:-1],g[1:]):
            l=np.hypot(*(q-p))
            if l>1: P.append((p+q)/2); V.append((q-p)/l); W.append(l)
    return np.array(P),np.array(V),np.array(W)
def bez(p0,p1,p2,n):
    t=np.linspace(0,1,n)[:,None]; return (1-t)**2*p0+2*(1-t)*t*p1+t**2*p2
dropped=set(); paths=[]; report=[]; centres=[]; zonesout=[]
for mem in cl.values():
    if len(mem)<6: continue
    pts=np.concatenate([G[k] for k in mem]); lo=pts.min(0)-80; hi=pts.max(0)+80
    zone=[fast[i] for i in ftr.query_ball_point((lo+hi)/2, float(np.hypot(*(hi-lo))/2))]
    zone=[k for k in zone if np.all((G[k].mean(0)>=lo)&(G[k].mean(0)<=hi))]
    if len(zone)<6: continue
    # the axes come from the motorway and the main roads crossing it (a motorway over a city avenue is an interchange too)
    big=[k for k,e in enumerate(E) if e['c'] in ('highway','ring','main') and len(G[k])>=2 and np.all((G[k].mean(0)>=lo)&(G[k].mean(0)<=hi))] if False else None
    mq=mainmid_q(lo,hi)
    P,V,W=segs_of(zone+mq); PF,_,_=segs_of(zone); isF=np.zeros(len(P),bool); isF[:len(PF)]=True
    if len(P)<4: continue
    # dominant orientations (mod 180°), long straight segments weigh most
    ang=np.degrees(np.arctan2(V[:,1],V[:,0]))%180
    h=np.zeros(180)
    for a_,w_ in zip(ang,W*W): h[int(a_)%180]+=w_
    hs=np.convolve(np.r_[h[-6:],h,h[:6]],np.ones(7),'same')[6:-6]
    t1=int(np.argmax(hs)); h2=hs.copy()
    for d_ in range(-30,31): h2[(t1+d_)%180]=0
    t2=int(np.argmax(h2)); axes_deg=[t1]+([t2] if h2[t2]>0.12*hs[t1] else [])
    lines=[]
    for td in axes_deg:
        u=np.array([np.cos(np.radians(td)),np.sin(np.radians(td))]); nrm=np.array([-u[1],u[0]])
        sel=(np.abs(V@u)>np.cos(np.radians(8)))&(W>15)
        if sel.sum()<2: continue
        selF=sel&isF
        if selF.sum()>=2 and W[selF].sum()>200: sel=selF
        off=P[sel]@nrm; w=W[sel]
        o=np.argsort(off); cw=np.cumsum(w[o]); c=float(off[o][np.searchsorted(cw,cw[-1]/2)])
        lines.append((u,nrm,c))
    if not lines: continue
    # graph edges that run along an axis stay; the rest of the zone's motorway edges are replaced
    keep=set()
    for k in zone:
        Pk,Vk,Wk=segs_of([k])
        if len(Pk)==0: continue
        ok=False
        for u,nrm,c in lines:
            if np.all(np.abs(Vk@u)>np.cos(np.radians(10))) and np.all(np.abs(Pk@nrm-c)<30): ok=True
        if ok: keep.add(k)
    drop=[k for k in zone if k not in keep]
    yrs=[min(E[k]['y'][i] if E[k]['y'] else 2025 for k in zone) for i in range(4)]
    zc=(lo+hi)/2
    if len(zone)>=20: zonesout.append([round(float(zc[0]),1),round(float(zc[1]),1),round(float(min(hi-lo)/2*0.8),1),int(yrs[0])])
    if len(lines)<2:
        dropped.update(drop); report.append(('1axis',len(drop))); continue
    (u1,n1,c1),(u2,n2,c2)=lines[0],lines[1]
    # centre: intersection of the two axes
    A=np.array([n1,n2]); C=np.linalg.solve(A,np.array([c1,c2]))
    # arms: an axis direction counts if motorway segments lie on that side beyond 120 m
    arms=[]
    for u,nrm,c in lines:
        sel=np.abs(P@nrm-c)<30
        along=(P[sel]-C)@u
        if (along>120).any(): arms.append((u,float(along.max())))
        if (along<-120).any(): arms.append((-u,float(-along.min())))
    if len(arms)<3:
        dropped.update(drop); report.append(('arms<3',len(drop))); continue
    arms.sort(key=lambda a: np.arctan2(a[0][1],a[0][0]))
    angs=[(np.arctan2(arms[(i+1)%len(arms)][0][1],arms[(i+1)%len(arms)][0][0])-np.arctan2(arms[i][0][1],arms[i][0][0]))%(2*np.pi) for i in range(len(arms))]
    if not (min(angs)>np.radians(25) and min(l for _,l in arms)>140):
        dropped.update(drop); report.append(('plain',len(drop),[int(np.degrees(x)) for x in angs],[int(l) for _,l in arms],[int(C[0]),int(C[1])])); continue
    ext=0.5*float(np.hypot(*(hi-lo)))
    OFF=18.0; RL=70.0
    for i in range(len(arms)):
        (a,la)=arms[i]; (b,lb)=arms[(i+1)%len(arms)]
        phi=(np.arctan2(b[1],b[0])-np.arctan2(a[1],a[0]))%(2*np.pi)
        if phi>np.radians(170): continue                       # no quadrant on the straight-through side of a T
        bis=(a+b); bis/=np.hypot(*bis)
        # loop: a circle tangent to both outer carriageways, entered from arm a, left to arm b (270°-ish)
        dcl=(RL+OFF)/np.sin(phi/2); reach=dcl*np.cos(phi/2)+RL
        if np.radians(62)<phi<np.radians(118) and len(arms)>=3 and min(la,lb)>reach+20:
            dc=dcl; Lc=C+bis*dc
            # tangent points on the carriageway lines
            ta=C+a*(dc*np.cos(phi/2))+np.array([-a[1],a[0]])*0; tb=C+b*(dc*np.cos(phi/2))
            sa=np.arctan2(*(ta-Lc)[::-1]); sb=np.arctan2(*(tb-Lc)[::-1])
            # go the long way round (away from the centre)
            d_=(sb-sa)%(2*np.pi)
            if d_<np.pi: d_-=2*np.pi
            th=sa+np.linspace(0,d_,90); loop=Lc+RL*np.c_[np.cos(th),np.sin(th)]
            # straight run-in and run-out beside the carriageways, so the loop leaves and joins them like a slip lane
            t0=loop[1]-loop[0]; t0/=np.hypot(*t0); t1=loop[-1]-loop[-2]; t1/=np.hypot(*t1)
            lead=np.array([loop[0]-t0*s_ for s_ in np.linspace(90,6,15)]); tail=np.array([loop[-1]+t1*s_ for s_ in np.linspace(6,90,15)])
            loop=np.r_[lead,loop,tail]
            paths.append({'y':yrs,'g':[round(float(v),1) for v in loop.reshape(-1)]})
        # outer connector: leaves arm a beyond the loop, swings round it, joins arm b beyond the loop
        if not (np.radians(55)<phi<np.radians(125)): continue     # a very sharp or very open quadrant: no connector (it would be a huge arc)
        r_o=min(reach+150.0, min(la,lb)+40.0)
        if r_o<reach+70: continue                            # that arm is too short for a connector
        na=np.array([-a[1],a[0]]); na*=np.sign(np.dot(bis,na)) or 1; nb_=np.array([-b[1],b[0]]); nb_*=np.sign(np.dot(bis,nb_)) or 1
        pa=C+a*r_o+na*OFF; pb=C+b*r_o+nb_*OFF
        far=dcl+RL+22.0                                            # the curve's middle passes this far out along the bisector
        mid_need=far; proj=0.5*(np.dot(pa-C,bis)+np.dot(pb-C,bis))
        ctrl=C+bis*max(2*mid_need-proj, proj+20)
        curve=bez(pa,ctrl,pb,70)
        # run-ins along the carriageways
        lead=np.array([pa+a*s_ for s_ in np.linspace(80,6,14)]); tail=np.array([pb+b*s_ for s_ in np.linspace(6,80,14)])
        curve=np.r_[lead,curve,tail]
        paths.append({'y':yrs,'g':[round(float(v),1) for v in curve.reshape(-1)]})
    dropped.update(drop); report.append((len(arms),len(drop))); centres.append([float(C[0]),float(C[1])])
json.dump(centres,open('/tmp/claude-0/air/centres.json','w'))
json.dump({'edges':sorted(int(k) for k in dropped),'paths':paths,'zones':zonesout},open(R+'Landmarks/interchanges.json','w'),separators=(',',':'))
print('zones',len(report),report[:40]); print('paths',len(paths),'dropped',len(dropped))
