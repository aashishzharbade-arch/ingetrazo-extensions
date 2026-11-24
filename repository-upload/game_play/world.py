"""Spatial queries over the visible, transformed triangles of the open model."""
import numpy as np

class Node:
    def __init__(self, lo, hi, ids):
        self.lo=lo[ids].min(0)
        self.hi=hi[ids].max(0)
        self.children=()
        self.ids=ids
        if len(ids)>48:
            axis=(self.hi-self.lo).argmax()
            centres=lo[ids,axis]+hi[ids,axis]
            mid=len(ids)//2
            order=ids[np.argpartition(centres,mid)]
            self.children=(Node(lo,hi,order[:mid]),Node(lo,hi,order[mid:]))
            self.ids=None

    def query(self,lo,hi,result):
        if (self.hi<lo).any() or (self.lo>hi).any(): return
        if self.children:
            for child in self.children: child.query(lo,hi,result)
        else: result.append(self.ids)

class World:
    def __init__(self,scene):
        tris=[]
        for face,matrix in scene.iter_world_faces():
            for tri in face.triangulate():
                tris.append([(matrix.map(p) if matrix is not None else p).toTuple() for p in tri])
        self.tri=np.asarray(tris,dtype=float).reshape(-1,3,3)
        self.tri=self.tri[np.isfinite(self.tri).all(axis=(1,2))]
        self.root=None
        if len(self.tri):
            self.lo=self.tri.min(1)
            self.hi=self.tri.max(1)
            self.root=Node(self.lo,self.hi,np.arange(len(self.tri)))
        self.e1=self.tri[:,1]-self.tri[:,0]
        self.e2=self.tri[:,2]-self.tri[:,0]
        normal=np.cross(self.e1,self.e2)
        self.slope=np.abs(normal[:,2])/np.maximum(1.e-12,np.linalg.norm(normal,axis=1))

    def box(self,lo,hi):
        hits=[]
        if self.root: self.root.query(lo,hi,hits)
        if not hits:return np.empty(0,dtype=int)
        ids=np.concatenate(hits)
        return ids[((self.hi[ids]>=lo)&(self.lo[ids]<=hi)).all(1)]

    def ray(self,p,d,reach,walkable=False):
        p=np.asarray(p); d=np.asarray(d)
        end=p+d*reach
        ids=self.box(np.minimum(p,end)-1e-8,np.maximum(p,end)+1e-8)
        if walkable: ids=ids[self.slope[ids]>.68]
        if not len(ids):return None
        a,b=self.e1[ids],self.e2[ids]
        h=np.cross(d,b)
        det=(a*h).sum(1)
        inv=np.divide(1.,det,out=np.zeros_like(det),where=abs(det)>1e-10)
        s=p-self.tri[ids,0]
        u=inv*(s*h).sum(1)
        q=np.cross(s,a)
        v=inv*(q*d).sum(1)
        t=inv*(q*b).sum(1)
        ok=(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>1e-5)&(t<=reach)
        return float(t[ok].min()) if ok.any() else None

    def advance(self,p,step):
        distance=np.linalg.norm(step)
        if distance<1e-8:return p.copy()
        direction=step/distance
        side=np.array([-direction[1],direction[0],0])
        for height in (.34,1.,1.68):
            for offset in (-.19,0,.19):
                if self.ray(p+[0,0,height]+side*offset,direction,distance+.19) is not None:return p.copy()
        dest=p+step
        hit=self.ray(dest+[0,0,.31],(0,0,-1),1.05,True)
        if hit is not None:dest[2]+=.31-hit
        elif abs(dest[2])<.035:dest[2]=0
        else:return p.copy()
        return dest

    def inside(self,p):
        eye=p+[0,0,1.25]
        # Test enclosure at the player's elevation as well as ceiling coverage.
        walls=sum(self.ray(eye,(np.cos(a),np.sin(a),0),30) is not None for a in np.arange(8)*np.pi/4)
        covered=self.ray(eye,(0,0,1),35) is not None
        return walls>=7 or (covered and walls>=3)

    def section(self,p,span):
        z=p[2]+1.1
        ids=self.box(p+[-span,-span,1.1],p+[span,span,1.1])
        t=self.tri[ids]
        ends=[]
        for a,b in ((0,1),(1,2),(2,0)):
            cross=(t[:,a,2]>z)!=(t[:,b,2]>z)
            delta=t[:,b]-t[:,a]
            ratio=np.divide(z-t[:,a,2],delta[:,2],out=np.zeros(len(t)),where=cross)
            ends.append(np.where(cross[:,None],t[:,a,:2]+ratio[:,None]*delta[:,:2],np.nan))
        coords=np.stack(ends,axis=1)
        return coords[np.isfinite(coords).all(2)].reshape(-1,2,2)
