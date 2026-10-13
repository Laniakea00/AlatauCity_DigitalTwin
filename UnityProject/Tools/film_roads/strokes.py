# Python port of the plan-graph part of FilmRoads.Strokes(), used by build_film_roads.py
import json, numpy as np, math
from collections import defaultdict
U='/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/'
def load(roads=U+'Assets/StreamingAssets/twin/roads.json', ic=U+'Assets/Resources/Landmarks/interchanges.json'):
    E=json.load(open(roads))['edges']; IC=json.load(open(ic)) if ic else None
    return E,IC
def Y(e,s): y=e.get('y'); return y[min(s,len(y)-1)] if y else 2025
def resample(p,step):
    o=[p[0]]; acc=0
    for i in range(1,len(p)):
        a=np.array(p[i-1]);b=np.array(p[i]); d=np.hypot(*(b-a))
        if d<1e-4: continue
        t=step-acc
        while t<=d: o.append(a+(b-a)*t/d); t+=step
        acc=d-(t-step)
    if np.hypot(*(np.array(o[-1])-np.array(p[-1])))>0.5: o.append(np.array(p[-1]))
    else: o[-1]=np.array(p[-1])
    return [np.array(q,float) for q in o]
def smooth(p,passes):
    a=np.array(p,float)
    for _ in range(passes):
        if len(a)<3: break
        b=a.copy(); b[1:-1]=(a[:-2]+2*a[1:-1]+a[2:])*0.25; a=b
    return a
def strokes(E,IC):
    n=len(E); G=[np.array(e['g'],float).reshape(-1,2) for e in E]
    adj=defaultdict(list)
    for i,e in enumerate(E):
        if len(G[i])<2: continue
        adj[e['a']].append(i); adj[e['b']].append(i)
    def same(a,b): return E[a]['c']==E[b]['c'] and all(Y(E[a],s)==Y(E[b],s) for s in range(4))
    def out(i,node):
        g=G[i]; v=g[1]-g[0] if E[i]['a']==node else g[-2]-g[-1]; m=np.hypot(*v); return v/m if m>1e-4 else v
    used=[False]*n; res=[]
    if IC:
        for k in IC['edges']: used[k]=True
    bd=math.cos(math.radians(30))
    def nxt(cur,node):
        best=-1; din=-out(cur,node); bv=-9
        for j in adj.get(node,[]):
            if used[j] or not same(cur,j): continue
            lim=0.42 if E[cur]['len']<90 and E[j]['len']<90 else bd
            d=float(din@out(j,node))
            if d>lim and d>bv: best=j; bv=d
        return best
    for i in range(n):
        if used[i] or len(G[i])<2: continue
        used[i]=True; pts=list(G[i]); head=E[i]['a']; tail=E[i]['b']; eh=et=i
        for side in range(2):
            guard=0
            while guard<100000:
                guard+=1
                node=tail if side==0 else head
                cur=nxt(et if side==0 else eh,node)
                if cur<0: break
                used[cur]=True; g=G[cur]; fwd=E[cur]['a']==node
                if side==0:
                    pts+= list(g[1:]) if fwd else list(g[-2::-1]); tail=E[cur]['b'] if fwd else E[cur]['a']; et=cur
                else:
                    pre=list(g[:0:-1]) if fwd else list(g[:-1]); pts=pre+pts; head=E[cur]['b'] if fwd else E[cur]['a']; eh=cur
                if head==tail: break
        if head==tail and len(pts)>4:
            P=np.array(pts); cc=P.mean(0); rr=np.hypot(*(P-cc).T).mean()
            if rr<110:
                ns=max(16,math.ceil(2*math.pi*rr/8)); a0=math.atan2(*(P[0]-cc)[::-1])
                pts=[cc+rr*np.array([math.cos(a0+k*2*math.pi/ns),math.sin(a0+k*2*math.pi/ns)]) for k in range(ns+1)]
        rs=resample(pts,8)
        if len(rs)<2: continue
        L=sum(np.hypot(*(rs[k]-rs[k-1])) for k in range(1,len(rs)))
        st=dict(cls=E[i]['c'],y=[Y(E[i],s) for s in range(4)],A=head,B=tail,P=np.array(rs),L=L,ramp=False,oneway=False,fixed=False,edges=None)
        fast=st['cls'] in ('highway','ring')
        if L<30 and (len(adj[head])==1 or len(adj[tail])==1): continue
        if fast and L<35:
            dd=rs[-1]-rs[0]; dd/=max(np.hypot(*dd),1e-6)
            def al(node): return any(j!=eh and j!=et and abs(out(j,node)@dd)>0.7 for j in adj[node])
            if not al(head) and not al(tail): continue
        res.append(st)
    if IC:
        for p in IC['paths']:
            g=np.array(p['g']).reshape(-1,2); rs=smooth(resample(list(g),8),2)
            res.append(dict(cls='highway',y=p['y'],A=-1,B=-1,P=rs,L=np.hypot(*np.diff(rs,axis=0).T).sum(),ramp=True,oneway=False,fixed=True))
    # dual carriageway detection
    from scipy.spatial import cKDTree
    segm=[];segd=[];segs=[]
    for k,st in enumerate(res):
        p=st['P']; d=np.diff(p,axis=0); l=np.hypot(*d.T); ok=l>=1
        segm.append(((p[1:]+p[:-1])/2)[ok]); segd.append((d[ok].T/l[ok]).T); segs.append(np.full(ok.sum(),k))
    M=np.concatenate(segm);Dd=np.concatenate(segd);S=np.concatenate(segs); tr=cKDTree(M)
    for k,st in enumerate(res):
        if st['fixed']: continue
        p=st['P']; maxD=30 if st['cls']=='highway' else 22; tw=cnt=0
        for i in range(1,len(p),2):
            m=(p[i]+p[i-1])/2; d=p[i]-p[i-1]; l=np.hypot(*d)
            if l<1: continue
            d/=l; cnt+=1; hit=False
            for q in tr.query_ball_point(m,maxD+12):
                if S[q]==k or res[S[q]]['cls']!=st['cls'] or abs(Dd[q]@d)<0.96: continue
                v=M[q]-m; perp=abs(v[0]*d[1]-v[1]*d[0]); par=abs(v@d)
                if 3<perp<maxD and par<12: hit=True;break
            tw+=hit
        st['oneway']=cnt>0 and tw>cnt*0.5
        sm=smooth(p,3); d=np.diff(sm,axis=0); a=np.arctan2(d[:,1],d[:,0]); turn=np.degrees(np.abs(np.angle(np.exp(1j*np.diff(a))))).sum() if len(a)>1 else 0
        fast=st['cls'] in ('highway','ring')
        st['ramp']=fast and ((st['L']<2500 and turn>35 and turn/max(st['L'],1)>0.03) or (st['L']<600 and not st['oneway']))
        st['P']=smooth(p,6 if st['ramp'] else 10 if fast else 6 if st['cls']=='main' else 3)
    return res
def half(st):
    c=st['cls']
    if st['ramp']: return 4
    if st['oneway']: return {'highway':6,'ring':5.5,'main':3.8}.get(c,3.2)
    return {'highway':11,'ring':9,'main':7.5}.get(c,4)
