# SPDX-License-Identifier: GPL-3.0-or-later
"""Document data, deterministic phase evaluation and isolated preview state.

All distances inside the scene are metres. No SketchUp/RP API or code is used.
"""
import copy
import math
import uuid
from PySide6.QtGui import QMatrix4x4, QMatrix3x3, QQuaternion, QVector3D as V
from core.scene import Scene
from core.group import Group
from core.mesh import Mesh
from core.layers import layer_of, DEFAULT_LAYER
from core.materials import effective_attrs
from core.history import Command

KEY = 'phasing_animator'
TITLE = 'Phasing Animator V1.0'
VERSION = '1.0.0'
FPS = (24, 25, 30, 50, 60)
SIZES = {'16:9': ((1280,720),(1920,1080),(2560,1440),(3840,2160)),
         '9:16': ((720,1280),(1080,1920),(1440,2560),(2160,3840)),
         '1:1': ((1080,1080),(2160,2160)), '4:3': ((1440,1080),(1920,1440))}


def empty_data():
    return dict(schema=1, duration=12., fps=30, phases=[],
                objects={}, camera=[], export=dict(ratio='16:9', size=[1920,1080],
                fps=30, format='PNG sequence'))


def validated(raw):
    d = copy.deepcopy(raw) if raw is not None else empty_data()
    if not isinstance(d,dict):raise ValueError('Animation data must be a document object.')
    if d.get('schema') != 1:
        raise ValueError('Unsupported Phasing Animator document version.')
    d.pop('edition', None)  # Migrate previously saved edition metadata.
    if not isinstance(d.get('duration'), (float,int)) or not math.isfinite(d['duration']) or not .1 <= d['duration'] <= 3600:
        raise ValueError('Duration must be 0.1–3600 seconds.')
    if d.get('fps') not in FPS:
        raise ValueError('Unsupported frame rate.')
    phases = d.get('phases', [])
    if not isinstance(phases,list):raise ValueError('Invalid phase list.')
    ids, layers = set(), set()
    for p in phases:
        if not isinstance(p,dict) or not isinstance(p.get('name'),str):raise ValueError('Invalid phase name.')
        if not isinstance(p.get('id'),str) or p['id'] in ids:
            raise ValueError('Phase IDs must be unique.')
        ids.add(p['id'])
        if not isinstance(p.get('layer'),str) or not p['layer'] or p['layer'] in layers:
            raise ValueError('Use one phase track per model layer to avoid conflicting visibility.')
        layers.add(p['layer'])
        if not all(isinstance(p.get(k),(float,int)) and math.isfinite(p[k]) for k in ('start','end','rise')):
            raise ValueError('Phase timing and rise distance must be finite numbers.')
        if not 0 <= p['start'] < p['end'] <= d['duration']:
            raise ValueError('Phase start must be before its end and within the clip.')
        if abs(p['rise']) > 10000 or p.get('effect') not in ('show','fade','rise') or p.get('after') not in ('keep','hide'):
            raise ValueError('Invalid phase effect.')
    if not isinstance(d.get('objects',{}),dict):raise ValueError('Invalid object tracks.')
    for track in list(d.get('objects',{}).values()) + [{'keys': d.get('camera',[])}]:
        if not isinstance(track,dict) or not isinstance(track.get('keys'),list):raise ValueError('Invalid keyframes.')
        times = [k['t'] for k in track['keys']]
        if any(not math.isfinite(t) or not 0 <= t <= d['duration'] for t in times) or times != sorted(set(times)):
            raise ValueError('Keyframes must have unique ordered times within the clip.')
    def vector(v,n):
        return isinstance(v,(list,tuple)) and len(v)==n and all(isinstance(x,(float,int)) and math.isfinite(x) for x in v)
    for track in d.get('objects',{}).values():
        if not isinstance(track.get('name'),str):raise ValueError('Invalid object track name.')
        for key in track['keys']:
            v=key['value']
            if not all(vector(v.get(k),n) for k,n in [('p',3),('s',3),('q',4)]) or min(v['s'])<=0 or sum(x*x for x in v['q'])<1e-12:
                raise ValueError('Invalid object transform key.')
    for key in d.get('camera',[]):
        v=key['value']
        if not vector(v.get('target'),3) or not vector(v.get('up'),3) or not all(isinstance(v.get(k),(int,float)) and math.isfinite(v[k]) for k in ('yaw','pitch','distance','fov_deg')) or v['distance']<=0 or not 0<v['fov_deg']<180:
            raise ValueError('Invalid camera key.')
    d.setdefault('phases',[]); d.setdefault('objects',{}); d.setdefault('camera',[])
    d.setdefault('export',empty_data()['export'])
    cfg=d['export']
    if not isinstance(cfg,dict) or cfg.get('ratio') not in SIZES or tuple(cfg.get('size',())) not in SIZES[cfg['ratio']] or cfg.get('fps') not in FPS or cfg.get('format') not in ('PNG sequence','MP4 · H.264','WebM · VP9'):
        raise ValueError('Invalid export settings.')
    return d


def new_phase(layer, start, duration):
    start = min(max(0.,start), duration-.1)
    return dict(id=uuid.uuid4().hex, name=layer, layer=layer, start=start,
                end=min(duration,start+3), effect='show', after='keep', rise=3., enabled=True)


def add_phase(d, layer, t):
    if any(p['layer']==layer for p in d['phases']):
        raise ValueError('This layer already has a phase track. Select it to edit.')
    p=new_phase(layer,t,d['duration']);d['phases'].append(p)
    return p


def phase_value(p, t):
    """Return visibility, alpha multiplier, world-Z rise offset at exact time."""
    if not p.get('enabled',True): return True,1.,0.
    if t < p['start'] or (p['after']=='hide' and t >= p['end']): return False,0.,0.
    u=max(0.,min(1.,(t-p['start'])/(p['end']-p['start'])))
    return True, (u if p['effect']=='fade' else 1.), ((u-1)*p['rise'] if p['effect']=='rise' else 0.)


def xyz(v): return [v.x(),v.y(),v.z()]


def pose(m):
    m=m if m is not None else QMatrix4x4()
    cols=[V(m[0,i],m[1,i],m[2,i]) for i in range(3)]
    scales=[v.length() for v in cols]
    if any(not math.isfinite(s) or s<1e-7 for s in scales): raise ValueError('Zero or invalid scale cannot be recorded.')
    axes=[v/s for v,s in zip(cols,scales)]
    if any(abs(V.dotProduct(axes[i],axes[j]))>1e-4 for i,j in ((0,1),(0,2),(1,2))): raise ValueError('Sheared transforms cannot be recorded.')
    if V.dotProduct(V.crossProduct(axes[0],axes[1]),axes[2])<0: raise ValueError('Mirrored transforms cannot be recorded.')
    q=QQuaternion.fromRotationMatrix(QMatrix3x3([xyz(axes[c])[r] for r in range(3) for c in range(3)])).normalized()
    return dict(p=[m[0,3],m[1,3],m[2,3]],s=scales,q=[q.scalar(),q.x(),q.y(),q.z()])


def matrix_of(v):
    m=QMatrix4x4();m.translate(V(*v['p']));m.rotate(QQuaternion(*v['q']));m.scale(V(*v['s']));return m


def mix(a,b,u): return [x+(y-x)*u for x,y in zip(a,b)]


def interpolate(a,b,u):
    q=QQuaternion.slerp(QQuaternion(*a['q']),QQuaternion(*b['q']),u)
    return dict(p=mix(a['p'],b['p'],u),s=mix(a['s'],b['s'],u),q=[q.scalar(),q.x(),q.y(),q.z()])


def segment(keys,t):
    if t<=keys[0]['t']:return keys[0]['value'],keys[0]['value'],0.
    for a,b in zip(keys,keys[1:]):
        if t<=b['t']:return a['value'],b['value'],(t-a['t'])/(b['t']-a['t'])
    return keys[-1]['value'],keys[-1]['value'],0.


def put_key(keys,t,value):
    keys[:]=[k for k in keys if abs(k['t']-t)>.0001]
    keys.append(dict(t=t,value=value));keys.sort(key=lambda k:k['t'])


def camera_data(cam):
    return dict(target=xyz(cam.target),up=xyz(cam.up),yaw=cam.yaw,pitch=cam.pitch,
                distance=cam.distance,fov_deg=cam.fov_deg,perspective=cam.perspective,two_point=cam.two_point)


def camera_mix(a,b,u):
    v=copy.deepcopy(a)
    for k in ('target','up'):v[k]=mix(a[k],b[k],u)
    for k in ('pitch','distance','fov_deg'):v[k]=a[k]+(b[k]-a[k])*u
    v['yaw']=a['yaw']+((b['yaw']-a['yaw']+math.pi)%(2*math.pi)-math.pi)*u
    if u>=1:
        v['perspective']=b['perspective'];v['two_point']=b['two_point']
    return v


def set_camera(cam,value):
    for k,v in value.items():setattr(cam,k,V(*v) if k in ('target','up') else v)


class EditAnimation(Command):
    def __init__(self,data,prepare=()):self.data=validated(data);self.prepare=list(prepare)
    def do(self,scene):
        self.before=copy.deepcopy(scene.plugin_data.get(KEY))
        self.transforms=[(g,None if g.xform is None else QMatrix4x4(g.xform),g.component) for g in self.prepare]
        for g in self.prepare:
            if g.xform is None:g.xform=QMatrix4x4();g.component=False
        scene.plugin_data[KEY]=copy.deepcopy(self.data);scene.version+=1
    def undo(self,scene):
        for g,m,component in self.transforms:g.xform=m;g.component=component
        if self.before is None:scene.plugin_data.pop(KEY,None)
        else:scene.plugin_data[KEY]=copy.deepcopy(self.before)
        scene.version+=1


def clone_group(g, inherited_material=None):
    # Copy each placement separately: instance materials may fade independently.
    out=Group(copy.deepcopy(g.mesh),g.name)
    for field in ('uid','layer','hidden','billboard','component','material','axes','ifc','text3d','ext'):
        setattr(out,field,copy.deepcopy(getattr(g,field,None)))
    out.xform=QMatrix4x4(g.xform) if g.xform is not None else None
    material=g.material or inherited_material
    for f in out.mesh.faces:f.attrs=copy.deepcopy(effective_attrs(f.attrs,material))
    out.material=None
    out.mesh._chunk_dirty=True
    out.children=[clone_group(c,material) for c in g.children]
    # Tagged faces inside a container need their own temporary placements for
    # rise effects, otherwise only container-assigned tags would move.
    if any(layer_of(f)!=DEFAULT_LAYER for f in out.mesh.faces):
        parts=split_loose(out.mesh)
        for part in parts:
            if part.layer==DEFAULT_LAYER:part.layer=None
        out.mesh=Mesh();out.children=parts+out.children
    return out


def split_loose(mesh):
    """Separate temporary layer meshes so a rise never tears shared source faces."""
    parts={}
    for f in mesh.faces:
        dst=parts.setdefault(layer_of(f),Mesh())
        nf=dst.add_face(f.vertices, f.holes or None)
        nf.attrs=copy.deepcopy(f.attrs);nf.interior=f.interior
    for e in mesh.edges:
        names={layer_of(f) for f in e.faces} or {layer_of(e)}
        for name in names:
            dst=parts.setdefault(name,Mesh());ne=dst.add_edge(e.a,e.b)
            for attr in ('soft','curve','hidden','layer'):setattr(ne,attr,getattr(e,attr))
    groups=[]
    for name,part in parts.items():
        g=Group(part,'Loose geometry · '+name);g.layer=name;groups.append(g)
    return groups


class Snapshot:
    """Independent meshes, transforms and materials; source is never scrubbed."""
    def __init__(self,source):
        if source.edit_group is not None:raise ValueError('Exit group editing before opening the animator.')
        self.scene=Scene()
        for field in ('layers','display_style','shadows','back_face_color','section_planes','show_section_cuts','materials'):
            setattr(self.scene,field,copy.deepcopy(getattr(source,field)))
        self.scene.groups=[clone_group(g) for g in source.groups]+split_loose(source.loose_mesh)
        self.baseline={};self.face_attrs={};self.edge_hidden={};self.applied_alpha={}
        def remember(g):
            self.baseline[id(g)]=(QMatrix4x4(g.xform) if g.xform is not None else QMatrix4x4(),g.hidden,copy.deepcopy(g.material))
            self.face_attrs[id(g)]=[copy.deepcopy(f.attrs) for f in g.mesh.faces]
            self.edge_hidden[id(g)]=[e.hidden for e in g.mesh.edges]
            for c in g.children:remember(c)
        for g in self.scene.groups:remember(g)
        self.layer_visible={ly.name:ly.visible for ly in self.scene.layers}

    def apply(self,data,t):
        phases={p['layer']:p for p in data['phases'] if p.get('enabled',True)}
        values={name:phase_value(p,t) for name,p in phases.items()}
        for ly in self.scene.layers:
            ly.visible=self.layer_visible[ly.name] and values.get(ly.name,(True,1,0))[0]
        def walk(g, inherited=DEFAULT_LAYER, parents=(), parent_world=None):
            base,hidden,material=self.baseline[id(g)]
            effective=g.layer or inherited
            lineage=tuple(dict.fromkeys((*parents,effective)))
            visible=all(values.get(k,(True,1,0))[0] for k in lineage)
            alpha=math.prod(values.get(k,(True,1,0))[1] for k in lineage)
            g.hidden=hidden or not visible or alpha<=0
            keys=data['objects'].get(g.uid,{}).get('keys',[]) if parent_world is None else []
            m=matrix_of(interpolate(*segment(keys,t))) if keys else QMatrix4x4(base)
            offset=values.get(effective,(True,1,0))[2] if effective not in parents else 0
            if offset:
                delta=V(0,0,offset)
                if parent_world is not None:
                    inv,ok=parent_world.inverted()
                    if ok:delta=inv.mapVector(delta)
                move=QMatrix4x4();move.translate(delta);m=move*m
            g.xform=m;g.material=copy.deepcopy(material)
            changed=False
            update_alpha=self.applied_alpha.get(id(g))!=alpha
            for f,attrs in (zip(g.mesh.faces,self.face_attrs[id(g)]) if update_alpha else ()):
                result=copy.deepcopy(attrs)
                face_layer=attrs.get('layer') or effective
                a=alpha*(values.get(face_layer,(True,1,0))[1] if face_layer not in lineage else 1)
                if a<1:
                    result['opacity']=float(attrs.get('opacity',(material or {}).get('opacity',1)) or 0)*a
                    if 'back' in result and isinstance(result['back'],dict):
                        result['back']['opacity']=float(result['back'].get('opacity',1))*a
                if result!=f.attrs:f.attrs=result;changed=True
            # Avoid opaque wire outlines floating over fading surfaces.
            for e,h in (zip(g.mesh.edges,self.edge_hidden[id(g)]) if update_alpha else ()):
                value=h or alpha<.999
                if e.hidden!=value:e.hidden=value;changed=True
            if changed:g.mesh._mut_serial+=1;g.mesh._chunk_dirty=True
            self.applied_alpha[id(g)]=alpha
            world=m if parent_world is None else parent_world*m
            for child in g.children:walk(child,effective,lineage,world)
        for g in self.scene.groups:walk(g)
        self.scene.version+=1


def frame_count(duration,fps):
    return max(1,math.ceil(duration*fps-1e-9))


def frame_time(index,duration,fps):
    # Include both visual endpoints while retaining the requested output FPS.
    count=frame_count(duration,fps)
    return 0. if count==1 else index*duration/(count-1)
