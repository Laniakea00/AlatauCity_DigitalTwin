import json, numpy as np
from collections import defaultdict
from scipy.spatial import cKDTree
def zones(E):
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
    big=[k for k,e in enumerate(E) if e['c'] in ('main','highway','ring') and len(G[k])>=2]
    bmid=np.array([G[k].mean(0) for k in big]); btr=cKDTree(bmid)
    def segs_of(ks):
        P=[];V=[];W=[];F=[]
        for k in ks:
            g=G[k]
            for p,q in zip(g[:-1],g[1:]):
                l=np.hypot(*(q-p))
                if l>1: P.append((p+q)/2); V.append((q-p)/l); W.append(l); F.append(E[k]['c'] in FAST)
        return np.array(P),np.array(V),np.array(W),np.array(F)
    out=[]
    for mem in cl.values():
        if len(mem)<6: continue
        pts=np.concatenate([G[k] for k in mem]); lo=pts.min(0)-80; hi=pts.max(0)+80
        cen=(lo+hi)/2; rad=float(np.hypot(*(hi-lo))/2)
        ks=[big[i] for i in btr.query_ball_point(cen, rad)]
        ks=[k for k in ks if np.all((G[k].mean(0)>=lo)&(G[k].mean(0)<=hi))]
        P,V,W,F=segs_of(ks)
        if len(P)<4: continue
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
            fsel=sel&F; mot = fsel.sum()>=2 and W[fsel].sum()>200
            if mot: sel=fsel
            off=P[sel]@nrm; w=W[sel]
            o=np.argsort(off); cw=np.cumsum(w[o]); c=float(off[o][np.searchsorted(cw,cw[-1]/2)])
            lines.append(dict(u=u,n=nrm,c=c,mot=bool(mot)))
        yrs=[min(E[k]['y'][i] if E[k]['y'] else 2025 for k in mem) for i in range(4)]
        z=dict(lo=lo,hi=hi,cen=cen,rad=rad,lines=lines,y=yrs,members=mem,pts=pts)
        if len(lines)>=2:
            A=np.array([lines[0]['n'],lines[1]['n']]); C=np.linalg.solve(A,np.array([lines[0]['c'],lines[1]['c']]))
            z['C']=C
            arms=[]
            for ln in lines:
                sel=np.abs(P@ln['n']-ln['c'])<30; along=(P[sel]-C)@ln['u']
                if (along>120).any(): arms.append((ln['u'],float(along.max()),ln['mot']))
                if (along<-120).any(): arms.append((-ln['u'],float(-along.min()),ln['mot']))
            arms.sort(key=lambda a: np.arctan2(a[0][1],a[0][0])); z['arms']=arms
            z['R']=float(np.percentile(np.hypot(*(pts-C).T),95))
        out.append(z)
    return out
