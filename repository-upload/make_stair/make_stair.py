# SPDX-License-Identifier: GPL-3.0-or-later
"""Stair Maker V1.1 — parametric stairs for IngeTrazo.

Install this file in the user plugins folder; restart IngeTrazo.
Stored lengths are millimetres; the geometry API uses metres.
"""
from __future__ import annotations

import copy
import math
import base64

from PySide6.QtCore import QUrl, Qt, QPointF, QTimer, QSize, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QMatrix4x4, QVector3D, QPixmap, QIcon, QImage, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget, QToolBar, QTabWidget,
)
from core.group import Group
from core.mesh import Mesh
from core.history import Command

KEY = "make_stair"
VERSION = "1.1.1"
DISPLAY_NAME = "Stair Maker V1.1"
DEVELOPER = "aashishzharbade-arch"
PRO_URL = "https://ingetrazotutorials.gumroad.com/l/stairmaker_1"
TOOLBAR_NAME = "ingetrazo_stair_maker_toolbar"
TYPES = ("Straight", "Straight with landing", "L-shaped", "U-shaped")
DEFAULTS = dict(
    kind="Straight", height=3000.0, width=1000.0, going=280.0,
    count_mode="Target riser", target_riser=175.0, risers=18,
    landing_after=0, landing_depth=1000.0, gap=100.0, turn="Left",
    nosing=25.0, thickness=40.0, closed=True, riser_thickness=20.0,
    top_landing=False, top_depth=1000.0,
    origin_x=0.0, origin_y=0.0, origin_z=0.0, rotation=0.0,
    railing="None", rail_sides="Both", rail_height=900.0,
    rail_inset=40.0, post_size=40.0, post_spacing=1000.0,
    handrail_size=40.0, glass_thickness=12.0, glass_opacity=30.0,
    bottom_gap=80.0, baluster_size=16.0, baluster_spacing=120.0,
    landing_rails=True,
)


UNIT_FACTORS_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
UNIT_DECIMALS = {"mm": 1, "cm": 2, "m": 4, "in": 2, "ft": 4}
UNIT_STEPS = {"mm": 5.0, "cm": 0.5, "m": 0.005, "in": 0.25, "ft": 0.01}
DIMENSION_FIELDS = frozenset(key for key, value in DEFAULTS.items()
                             if isinstance(value, float) and key not in ("glass_opacity", "rotation"))

def to_mm(value, unit):
    """Convert a user-entered length to the millimetre geometry unit."""
    return float(value) * UNIT_FACTORS_TO_MM[unit]

def from_mm(value, unit):
    """Convert a millimetre geometry length to the selected display unit."""
    return float(value) / UNIT_FACTORS_TO_MM[unit]

def resolve(values):
    """Validate dimensions and resolve an integer riser count (all in mm)."""
    p = dict(DEFAULTS)
    p.update(values)
    if p["kind"] not in TYPES or p["count_mode"] not in ("Target riser", "Riser count"):
        raise ValueError("Unknown stair type or riser mode.")
    if p["turn"] not in ("Left", "Right"):
        raise ValueError("Turn must be Left or Right.")
    for key, default in DEFAULTS.items():
        if isinstance(default, (float, int)) and not isinstance(default, bool):
            if not isinstance(p[key], (int, float)) or not math.isfinite(p[key]):
                raise ValueError(f"Invalid number: {key}.")
    for key in ("height", "width", "going", "target_riser", "thickness",
                "riser_thickness", "landing_depth", "top_depth"):
        if p[key] <= 0:
            raise ValueError(f"{key.replace('_', ' ').capitalize()} must be positive.")
    if p["nosing"] < 0 or p["gap"] < 0:
        raise ValueError("Nosing and flight gap cannot be negative.")
    if p["risers"] != int(p["risers"]) or p["landing_after"] != int(p["landing_after"]):
        raise ValueError("Riser counts must be whole numbers.")
    n = (math.ceil(p["height"] / p["target_riser"] - 1e-10)
         if p["count_mode"] == "Target riser" else int(p["risers"]))
    if not 2 <= n <= 200:
        raise ValueError("Use between 2 and 200 risers. Adjust height or target riser.")
    r = p["height"] / n
    if p["thickness"] >= r:
        raise ValueError("Tread thickness must be less than the actual riser height.")
    if p["nosing"] >= p["going"]:
        raise ValueError("Nosing must be less than the tread going.")
    if p["riser_thickness"] >= p["going"]:
        raise ValueError("Riser board thickness must be less than the tread going.")
    split = p["kind"] != "Straight"
    first = int(p["landing_after"]) or n // 2
    if split and not 2 <= first <= n - 2:
        raise ValueError("Each flight needs at least 2 risers; adjust landing after or riser count.")
    if p["kind"] in ("L-shaped", "U-shaped") and p["landing_depth"] < p["width"]:
        raise ValueError("For turning stairs, landing depth must be at least the stair width.")
    if p["railing"] not in ("None", "Glass", "Steel") or p["rail_sides"] not in ("Both", "Left", "Right"):
        raise ValueError("Choose a valid railing type and side.")
    if p["railing"] != "None":
        for key in ("rail_height", "post_size", "post_spacing", "handrail_size", "glass_thickness", "baluster_size", "baluster_spacing"):
            if p[key] <= 0:
                raise ValueError(f"{key.replace('_',' ').capitalize()} must be positive.")
        envelope = max(p["post_size"],p["handrail_size"],p["glass_thickness"] if p["railing"] == "Glass" else p["baluster_size"])
        if p["rail_inset"] < envelope/2 or p["width"] <= 2*p["rail_inset"]+envelope:
            raise ValueError("Keep rail centres at least half the member width inside each edge, with space between sides.")
        if p["post_size"] >= p["going"] or p["post_spacing"] < p["going"]:
            raise ValueError("Posts must be narrower than the going; post spacing must be at least one going.")
        if p["bottom_gap"] < 0 or p["rail_height"] <= p["bottom_gap"]+2*p["handrail_size"]:
            raise ValueError("Railing height must leave room for infill above the bottom gap.")
        if not 5 <= p["glass_opacity"] <= 100:
            raise ValueError("Glass opacity must be between 5 and 100 percent.")
        if p["railing"] == "Steel" and p["baluster_spacing"] <= p["baluster_size"]:
            raise ValueError("Baluster spacing must exceed the baluster width.")
        if p["railing"] == "Steel" and p["bottom_gap"]+p["baluster_size"] >= p["rail_height"]-p["handrail_size"]:
            raise ValueError("Reduce the bottom gap or steel member size to leave room for balusters.")
        if split and p["landing_rails"] and p["landing_depth"] < p["going"]+2*p["rail_inset"]:
            raise ValueError("Increase landing depth to accommodate the railing transition.")
        if p["kind"] == "L-shaped" and p["landing_rails"] and p["width"] <= p["going"]+2*p["rail_inset"]:
            raise ValueError("Increase stair width to accommodate the L-shaped railing turn.")
        if p["top_landing"] and p["landing_rails"] and p["top_depth"] <= p["rail_inset"]+p["post_size"]:
            raise ValueError("Increase upper landing depth to fit its railing posts.")
    return p, n, r, first


def stair_parts(values):
    """Return isolated rectangular solids as (name, bounds_mm, role).

    N risers end exactly at floor height. Each flight has n-1 treads;
    its destination is the intermediate landing or the upper floor.
    """
    p, n, r, first = resolve(values)
    w, t, nose, th = (p[k] for k in ("width", "going", "nosing", "thickness"))
    parts = []

    def box(name, x0, y0, z0, x1, y1, z1, role):
        if p["turn"] == "Right" and p["kind"] in ("L-shaped", "U-shaped"):
            y0, y1 = -y1, -y0
        parts.append((name, (x0, y0, z0, x1, y1, z1), role))

    def local_box(name, start, direction, a, b, c, d, z0, z1, role):
        dx, dy = direction
        pts = [(start[0] + dx*u - dy*v, start[1] + dy*u + dx*v)
               for u, v in ((a, b), (c, b), (c, d), (a, d))]
        box(name, min(q[0] for q in pts), min(q[1] for q in pts), z0,
            max(q[0] for q in pts), max(q[1] for q in pts), z1, role)

    def flight(start, direction, count, offset, destination):
        for j in range(1, count + 1):
            z = (offset + j) * r
            u = (j - 1) * t
            if j < count:
                local_box(f"Tread {offset+j}", start, direction,
                          u-nose, 0, u+t, w, z-th, z, "tread")
            if p["closed"]:
                # Final riser meets a supplied landing slab, or the upper floor.
                top = z - th if j < count or destination else z
                local_box(f"Riser {offset+j}", start, direction,
                          u, 0, u+p["riser_thickness"], w,
                          z-r, top, "riser")
        return (start[0] + direction[0]*(count-1)*t,
                start[1] + direction[1]*(count-1)*t)

    if p["kind"] == "Straight":
        end = flight((0, 0), (1, 0), n, 0, p["top_landing"])
        direction = (1, 0)
    else:
        end1 = flight((0, 0), (1, 0), first, 0, True)
        x, depth, z = end1[0], p["landing_depth"], first*r
        landing_w = 2*w+p["gap"] if p["kind"] == "U-shaped" else w
        box("Intermediate landing", x-nose, 0, z-th,
            x+depth, landing_w, z, "landing")
        if p["kind"] == "Straight with landing":
            start, direction = (x+depth, 0), (1, 0)
        elif p["kind"] == "L-shaped":
            start, direction = (x+depth, w), (0, 1)
        else:
            start, direction = (x, 2*w+p["gap"]), (-1, 0)
        end = flight(start, direction, n-first, first, p["top_landing"])
    if p["top_landing"]:
        local_box("Top landing", end, direction, -nose, 0, p["top_depth"], w,
                  p["height"]-th, p["height"], "landing")
    return parts


def corners(bounds):
    x, y, z, X, Y, Z = bounds
    return [(x,y,z), (X,y,z), (X,Y,z), (x,Y,z),
            (x,y,Z), (X,y,Z), (X,Y,Z), (x,Y,Z)]


FACES = ((3,2,1,0), (4,5,6,7), (0,1,5,4),
         (1,2,6,5), (2,3,7,6), (3,0,4,7))
COLORS = {"tread": (0.64, 0.70, 0.77), "riser": (0.42, 0.48, 0.55),
          "landing": (0.29, 0.59, 0.77), "steel": (0.35,0.39,0.44),
          "glass": (0.40,0.76,0.89)}


def railing_routes(values):
    """Continuous centre-line routes, measured from tread/landing surfaces.

    Left/right are as viewed ascending each flight. Route corners on landings
    run around their perimeter; upper-floor exits are deliberately left open.
    Each route point is also a supported post location.
    """
    p,n,r,first = resolve(values)
    if p["railing"] == "None":
        return []
    w,t,depth,ins = p["width"],p["going"],p["landing_depth"],p["rail_inset"]
    half = p["post_size"]/2
    step = max(1,int(p["post_spacing"]//t))
    mirror = p["turn"] == "Right" and p["kind"] in ("L-shaped","U-shaped")
    sides = ("Left","Right") if p["rail_sides"] == "Both" else (p["rail_sides"],)
    routes = []
    def flight(start,direction,count,offset,v):
        indices = list(range(0,count,step))
        if indices[-1] != count-1:
            indices.append(count-1)
        dx,dy = direction
        return [(start[0]+dx*(half+i*t)-dy*v,
                 start[1]+dy*(half+i*t)+dx*v,(offset+i+1)*r) for i in indices]
    def connect(points,corners):
        for q in corners:
            a = points[-1]
            length = math.hypot(q[0]-a[0],q[1]-a[1])
            if length < 1e-7:
                continue
            segments = max(1,math.ceil(length/p["post_spacing"]))
            points.extend(tuple(a[j]+(q[j]-a[j])*i/segments for j in range(3))
                          for i in range(1,segments+1))
    for side in sides:
        canonical_left = (side == "Left") != mirror
        v = w-ins if canonical_left else ins
        if p["kind"] == "Straight":
            points = flight((0,0),(1,0),n,0,v)
            direction = (1,0)
        else:
            points = flight((0,0),(1,0),first,0,v)
            x,z = (first-1)*t,first*r
            if p["kind"] == "Straight with landing":
                start,direction = (x+depth,0),(1,0)
            elif p["kind"] == "L-shaped":
                start,direction = (x+depth,w),(0,1)
            else:
                start,direction = (x,2*w+p["gap"]),(-1,0)
            upper = flight(start,direction,n-first,first,v)
            # The upper flight's slope starts one going back on the landing.
            q = upper[0]
            pre = (q[0]-direction[0]*t,q[1]-direction[1]*t,z)
            if p["landing_rails"]:
                if p["kind"] == "Straight with landing":
                    bends = [pre]
                elif p["kind"] == "L-shaped":
                    bends = [(pre[0],v,z),pre]
                elif canonical_left:
                    bends = [(pre[0],v,z),pre]
                else:
                    bends = [(x+depth-ins,v,z),(x+depth-ins,pre[1],z),pre]
                connect(points,bends)
                points.extend(upper)
            else:
                routes.append((side+" lower",points))
                points = upper
        if p["top_landing"] and p["landing_rails"]:
            a = points[-1]
            distance = p["top_depth"]-ins-half
            connect(points,[(a[0]+direction[0]*distance,a[1]+direction[1]*distance,a[2])])
        routes.append((side,points))
    if mirror:
        routes = [(name,[(x,-y,z) for x,y,z in pts]) for name,pts in routes]
    return routes


def railing_parts(values):
    """Rectangular steel members and sloped, closed glass panel solids."""
    p,_,_,_ = resolve(values)
    parts = []
    ps,hs,height = p["post_size"],p["handrail_size"],p["rail_height"]
    def member(name,a,b,width,low,high,role):
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy)
        if length < 1e-6:
            return
        nx,ny = -dy/length*width/2,dx/length*width/2
        pts = [(a[0]-nx,a[1]-ny,a[2]+low),(b[0]-nx,b[1]-ny,b[2]+low),
               (b[0]+nx,b[1]+ny,b[2]+low),(a[0]+nx,a[1]+ny,a[2]+low),
               (a[0]-nx,a[1]-ny,a[2]+high),(b[0]-nx,b[1]-ny,b[2]+high),
               (b[0]+nx,b[1]+ny,b[2]+high),(a[0]+nx,a[1]+ny,a[2]+high)]
        parts.append((name,pts,role))
    for side,points in railing_routes(p):
        for i,(x,y,z) in enumerate(points):
            parts.append((f"{side} post {i+1}",
                          corners((x-ps/2,y-ps/2,z,x+ps/2,y+ps/2,z+height-hs)),"steel"))
        for i,(a,b) in enumerate(zip(points,points[1:])):
            prefix = f"{side} bay {i+1}"
            member(prefix+" handrail",a,b,hs,height-hs,height,"steel")
            length = math.hypot(b[0]-a[0],b[1]-a[1])
            # Clear the square posts at arbitrary turn angles.
            clearance = ps/math.sqrt(2)+5
            if length <= 2*clearance:
                continue
            def at(distance):
                return tuple(a[j]+(b[j]-a[j])*distance/length for j in range(3))
            start,end = at(clearance),at(length-clearance)
            if p["railing"] == "Glass":
                member(prefix+" glass",start,end,p["glass_thickness"],
                       p["bottom_gap"],height-hs-10,"glass")
            else:
                bs = p["baluster_size"]
                member(prefix+" bottom rail",a,b,bs,p["bottom_gap"],p["bottom_gap"]+bs,"steel")
                bays = max(1,math.ceil((length-2*clearance)/p["baluster_spacing"]))
                if len(parts)+bays > 12000:
                    raise ValueError("Too many railing parts. Increase baluster spacing.")
                for j in range(bays+1):
                    x,y,z = at(clearance+(length-2*clearance)*j/bays)
                    parts.append((prefix+f" baluster {j+1}",
                        corners((x-bs/2,y-bs/2,z+p["bottom_gap"]+bs,
                                 x+bs/2,y+bs/2,z+height-hs)),"steel"))
    if len(parts) > 12000:
        raise ValueError("Too many railing parts. Increase post or baluster spacing.")
    return parts


def geometry_parts(values):
    return [(name,corners(bounds),role) for name,bounds,role in stair_parts(values)] + railing_parts(values)


def build_children(values):
    out = []
    p,_,_,_ = resolve(values)
    for name, vertices, role in geometry_parts(p):
        points = [QVector3D(x/1000, y/1000, z/1000) for x,y,z in vertices]
        mesh = Mesh()
        for face in FACES:
            f = mesh.add_face([points[i] for i in face])
            f.attrs["color"] = COLORS[role]
            if role == "glass":
                f.attrs["opacity"] = p["glass_opacity"]/100
        out.append(Group(mesh, name=name))
    return out


def make_group(values):
    p, n, r, first = resolve(values)
    group = Group(name=f"IngeTrazo Stair maker — {p['kind']}")
    group.adopt(build_children(p))
    group.component = False
    group.xform.translate(p["origin_x"]/1000, p["origin_y"]/1000, p["origin_z"]/1000)
    group.xform.rotate(p["rotation"], 0, 0, 1)
    group.ext = {KEY: {"version": VERSION, "parameters": p}}
    group.ifc = {"class": "IfcStair", "name": group.name}
    return group


class StairCommand(Command):
    """Swap prepared parts atomically; preserve group identity and placement."""
    def __init__(self, group, new_children=None, params=None):
        self.group = group
        self.new_children = new_children
        self.params = copy.deepcopy(params)
        self.before = None

    def do(self, scene):
        g = self.group
        if self.new_children is None:
            if g in scene.groups:
                raise ValueError("This stair is already in the document.")
            scene.groups.append(g)
        else:
            if g not in scene.groups:
                raise ValueError("The stair is no longer in this document.")
            if self.before is None:
                self.before = (g.children, copy.deepcopy(g.ext))
            ext = copy.deepcopy(g.ext or {})
            ext[KEY] = {"version": VERSION, "parameters": self.params}
            g.children = self.new_children
            g.ext = ext
        scene.selection.clear()
        scene.selection.add(g)
        scene.version += 1

    def undo(self, scene):
        if self.new_children is None:
            scene.groups.remove(self.group)
            scene.selection.discard(self.group)
        else:
            self.group.children, ext = self.before
            self.group.ext = copy.deepcopy(ext)
        scene.version += 1


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.colors = COLORS
        self.glass_opacity = 0.30
        self.yaw = -45.0
        self.pitch = 26.0
        self.zoom = 1.0
        self._last_pos = None
        self.setMinimumSize(300, 250)
        self.setToolTip("Left-click + drag to orbit 3D preview · Scroll wheel to zoom")

    def set_side_view(self):
        self.yaw, self.pitch, self.zoom = 0.0, 0.0, 1.0
        self.update()

    def set_top_view(self):
        self.yaw, self.pitch, self.zoom = 0.0, 90.0, 1.0
        self.update()

    def set_iso_view(self):
        self.yaw, self.pitch, self.zoom = -45.0, 26.0, 1.0
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._last_pos = event.position()

    def mouseMoveEvent(self, event):
        if self._last_pos is not None:
            delta = event.position() - self._last_pos
            self.yaw += delta.x() * 0.6
            self.pitch = max(-80.0, min(80.0, self.pitch + delta.y() * 0.5))
            self._last_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        self._last_pos = None

    def wheelEvent(self, event):
        factor = 1.12 if event.angleDelta().y() > 0 else 0.89
        self.zoom = max(0.4, min(3.5, self.zoom * factor))
        self.update()

    def set_parts(self,parts):
        import numpy as np
        self.parts = parts
        vertices = np.asarray([points for _, points, _ in parts], dtype=float).reshape(-1, 8, 3)
        faces = [tri for a, b, c, d in FACES for tri in ((a, b, c), (a, c, d))]
        self.triangles = vertices[:, faces].reshape(-1, 3, 3)
        self.materials = np.repeat([role for _, _, role in parts], len(faces))
        self._image_key = None

    def render_geometry(self):
        """Rasterise opaque surfaces with a depth buffer, then blend visible glass."""
        import numpy as np
        triangles=self.triangles
        width,height=max(1,self.width()),max(1,self.height())
        yaw,pitch=map(math.radians,(self.yaw,self.pitch))
        cy,sy,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        camera=np.array([[cy,-sy,0],[sy*sp,cy*sp,-cp],[sy*cp,cy*cp,sp]])
        projected=triangles@camera.T
        flat=projected.reshape((-1,3))
        lo,hi=flat.min(0),flat.max(0)
        scale=min((width-32)/max(1,hi[0]-lo[0]),(height-44)/max(1,hi[1]-lo[1]))*self.zoom
        projected[:,:,:2]=(projected[:,:,:2]-(lo+hi)[:2]/2)*scale+[width/2,height/2+5]
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        normals/=np.maximum(1e-12,np.linalg.norm(normals,axis=1))[:,None]
        light=camera.T@np.array([-.35,-.65,.68])
        shade=.72+.28*np.maximum(0,normals@light)
        colors=np.array([self.colors.get(role,COLORS["steel"]) for role in self.materials])*shade[:,None]*255
        pixels=np.empty((height,width,3),dtype=np.uint8)
        pixels[:]=(19,34,54)
        depth=np.full((height,width),-np.inf)
        glass=self.materials=="glass"
        glass_depth=np.full_like(depth,-np.inf)
        for i in np.r_[np.flatnonzero(~glass),np.flatnonzero(glass)]:
            tri=projected[i]
            low=np.maximum(np.floor(tri[:,:2].min(0)).astype(int),0)
            high=np.minimum(np.ceil(tri[:,:2].max(0)).astype(int),[width-1,height-1])
            if np.any(high<low):
                continue
            x0,y0=low
            x1,y1=high+1
            a,b,c=tri
            ab,ac=b-a,c-a
            det=ab[0]*ac[1]-ab[1]*ac[0]
            if abs(det)<1e-8:
                continue
            yy,xx=np.ogrid[y0:y1,x0:x1]
            xx=xx+.5-a[0]
            yy=yy+.5-a[1]
            u=(xx*ac[1]-yy*ac[0])/det
            v=(ab[0]*yy-ab[1]*xx)/det
            z=a[2]+u*ab[2]+v*ac[2]
            buffer=depth[y0:y1,x0:x1]
            inside=(u>=0)&(v>=0)&(u+v<=1)&(z>buffer)
            if glass[i]:
                # Composite a pane once per pixel. Its two faces share one tint.
                pane=glass_depth[y0:y1,x0:x1]
                np.maximum(pane,z,out=pane,where=inside)
            else:
                buffer[inside]=z[inside]
                pixels[y0:y1,x0:x1][inside]=colors[i]
        visible=np.isfinite(glass_depth)
        alpha=self.glass_opacity
        pixels[visible]=pixels[visible]*(1-alpha)+np.array(self.colors["glass"])*255*alpha
        return QImage(pixels.data,width,height,pixels.strides[0],QImage.Format_RGB888).copy()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor("#132236"))
        if not self.parts:
            painter.setPen(QColor("#d7e3ee"))
            painter.drawText(self.rect(),Qt.AlignCenter,"Adjust dimensions to preview")
            return
        key=(self.width(),self.height(),self.yaw,self.pitch,self.zoom,self.glass_opacity)
        if self._image_key!=key:
            self._cached_image=self.render_geometry()
            self._image_key=key
        painter.drawImage(0,0,self._cached_image)
        painter.setPen(QColor("#8fa8c2"))
        painter.drawText(QRectF(10,6,260,18),Qt.AlignLeft|Qt.AlignVCenter,"Drag to orbit · Scroll to zoom")


class StairDialog(QDialog):
    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.target = None
        self.edit_scene = None
        self.fields = {}
        self.unit_widgets = {}
        self.length_mm = {}
        self.current_units = "mm"
        self.setWindowTitle(DISPLAY_NAME)
        self.setWindowIcon(QIcon(logo_pixmap()))
        self.resize(1100, 740)
        outer = QVBoxLayout(self)
        heading = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap().scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        heading.addWidget(logo)
        title = QLabel(f"<h2>{DISPLAY_NAME}</h2>Developed by {DEVELOPER}")
        heading.addWidget(title, 1)
        heading.addWidget(QLabel("Units"))
        self.units_combo = QComboBox()
        self.units_combo.addItems(UNIT_FACTORS_TO_MM.keys())
        self.units_combo.currentTextChanged.connect(self.change_units)
        heading.addWidget(self.units_combo)
        upgrade = QPushButton("Upgrade to Pro Version")
        upgrade.setToolTip(PRO_URL)
        upgrade.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PRO_URL)))
        heading.addWidget(upgrade)
        outer.addLayout(heading)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(form_widget)
        self.tabs = QTabWidget()
        self.tabs.addTab(scroll, "Stair")
        body.addWidget(self.tabs, 1)
        def combo(key, label, items):
            widget = QComboBox()
            widget.addItems(items)
            self.fields[key] = widget
            form.addRow(label, widget)
            widget.currentIndexChanged.connect(self.refresh)
        def number( key, label, minimum, maximum, decimals=1):
            widget = QDoubleSpinBox() if decimals else QSpinBox()
            widget.setKeyboardTracking(False)
            if key in DIMENSION_FIELDS:
                self.unit_widgets[key] = (widget, minimum, maximum)
                self._format_unit_widget(key)
            else:
                widget.setRange(minimum, maximum)
                if decimals:
                    widget.setDecimals(decimals)
                    widget.setSingleStep(5)
            self.fields[key] = widget
            form.addRow(label, widget)
            if key in self.unit_widgets:
                widget.valueChanged.connect(lambda value,k=key: self.set_length(k,value))
            widget.valueChanged.connect(self.refresh)

        def check(key, label):
            widget = QCheckBox(label)
            self.fields[key] = widget
            form.addRow(widget)
            widget.toggled.connect(self.refresh)
        def section(label):
            form.addRow(QLabel(f"<b>{label}</b>"))
        section("Layout")
        combo("kind", "Stair type", TYPES)
        number("height", "Total height", 1, 100000)
        number("width", "Stair width", 1, 20000)
        number("going", "Tread going", 1, 5000)
        self.fields["going"].setToolTip("Horizontal distance between risers, excluding the nosing projection.")
        combo("count_mode", "Calculate using", ("Target riser", "Riser count"))
        number("target_riser", "Target maximum riser", 1, 5000)
        number("risers", "Number of risers", 2, 200, 0)
        section("Landings and turn")
        number("landing_after", "Landing after riser", 0, 198, 0)
        self.fields["landing_after"].setSpecialValueText("Auto / halfway")
        number("landing_depth", "Landing depth", 1, 20000)
        combo("turn", "Turn direction", ("Left", "Right"))
        number("gap", "U-shaped flight gap", 0, 10000)
        check("top_landing", "Add upper-floor landing")
        number("top_depth", "Upper landing depth", 1, 20000)
        section("Treads and risers")
        number("nosing", "Nosing projection", 0, 1000)
        number("thickness", "Tread thickness", 0.1, 2000)
        self.fields["thickness"].setToolTip("Thickness of both treads and landing slabs.")
        check("closed", "Closed risers (vertical boards)")
        number("riser_thickness", "Riser board thickness", 0.1, 1000)
        section("Placement — new stairs only")
        for axis in "xyz":
            number("origin_"+axis, "Origin "+axis.upper(), -10000000, 10000000)
        number("rotation", "Rotation about Z (degrees)", -360, 360)
        rail_scroll = QScrollArea()
        rail_scroll.setWidgetResizable(True)
        rail_widget = QWidget()
        form = QFormLayout(rail_widget)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        rail_scroll.setWidget(rail_widget)
        self.tabs.addTab(rail_scroll, "Railings")
        combo("railing", "Railing style", ("None", "Glass", "Steel"))
        combo("rail_sides", "Sides when walking up", ("Both", "Left", "Right"))
        number("rail_height", "Height to handrail top", 100, 3000)
        number("rail_inset", "Centre inset from edge", 1, 1000)
        section("Posts and handrail")
        number("post_size", "Square post width", 5, 200)
        number("post_spacing", "Maximum post spacing", 50, 5000)
        number("handrail_size", "Square handrail size", 5, 200)
        check("landing_rails", "Continue around landings")
        number("bottom_gap", "Infill bottom gap", 0, 1000)
        section("Glass")
        number("glass_thickness", "Glass thickness", 1, 100)
        number("glass_opacity", "Glass opacity (%)", 5, 100)
        section("Steel")
        number("baluster_size", "Square baluster width", 5, 100)
        number("baluster_spacing", "Max. baluster centres", 10, 1000)
        rail_note = QLabel("Post spacing is fitted to whole treads. Left/right follows the direction of ascent. The upper landing exit stays open.")
        rail_note.setWordWrap(True)
        form.addRow(rail_note)
        right = QVBoxLayout()
        body.addLayout(right, 1)
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        camera = QHBoxLayout()
        iso_button = QPushButton("3D Iso View")
        iso_button.clicked.connect(self.preview.set_iso_view)
        top_button = QPushButton("2D Plan View")
        top_button.clicked.connect(self.preview.set_top_view)
        camera.addWidget(iso_button)
        camera.addWidget(top_button)
        section_button = QPushButton("Side elevation")
        section_button.clicked.connect(self.preview.set_side_view)
        camera.addWidget(section_button)
        right.addLayout(camera)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.summary)
        self.message = QLabel()
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Create stair")
        self.apply_button.clicked.connect(self.apply)
        self.apply_button.setDefault(True)
        reset = QPushButton("Reset defaults")
        reset.clicked.connect(lambda: self.load(DEFAULTS))
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(reset)
        buttons.addStretch()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(close)
        outer.addLayout(buttons)
        self.load(DEFAULTS)

    def set_length(self,key,value):
        self.length_mm[key] = to_mm(value,self.current_units)

    def _format_unit_widget(self, key):
        widget, minimum, maximum = self.unit_widgets[key]
        scale = UNIT_FACTORS_TO_MM[self.current_units]
        widget.setDecimals(max(3, UNIT_DECIMALS[self.current_units]+2))
        widget.setRange(minimum / scale, maximum / scale)
        widget.setSingleStep(UNIT_STEPS[self.current_units])

    def change_units(self, new_units):
        if new_units not in UNIT_FACTORS_TO_MM or new_units == self.current_units:
            return
        mm_values = self.length_mm.copy()
        self.current_units = new_units
        for key, (widget, _, _) in self.unit_widgets.items():
            widget.blockSignals(True)
            self._format_unit_widget(key)
            widget.setValue(from_mm(mm_values[key], new_units))
            widget.blockSignals(False)
        self.refresh()

    def load(self, params):
        p = dict(DEFAULTS)
        p.update(params)
        requested_units = p.get("display_unit", self.current_units)
        if requested_units not in UNIT_FACTORS_TO_MM:
            requested_units = "mm"
        if requested_units != self.current_units:
            self.units_combo.blockSignals(True)
            self.units_combo.setCurrentText(requested_units)
            self.units_combo.blockSignals(False)
            self.current_units = requested_units
            for key,(field,_,_) in self.unit_widgets.items():
                field.blockSignals(True)
                self._format_unit_widget(key)
                field.blockSignals(False)
        for key, widget in self.fields.items():
            if key not in p:
                continue
            widget.blockSignals(True)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(str(p[key]))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(p[key]))
            else:
                value = from_mm(p[key], self.current_units) if key in DIMENSION_FIELDS else p[key]
                widget.setValue(value)
                if key in self.unit_widgets:
                    _,low,high=self.unit_widgets[key]
                    self.length_mm[key]=min(high,max(low,p[key]))
            widget.blockSignals(False)
        self.refresh()

    def values(self):
        result = {
            key: (w.currentText() if isinstance(w, QComboBox) else
                  w.isChecked() if isinstance(w, QCheckBox) else w.value())
            for key, w in self.fields.items()
        }
        for key in DIMENSION_FIELDS:
            if key in result:
                result[key] = self.length_mm.get(key,to_mm(result[key],self.current_units))
        result["display_unit"] = self.current_units
        return result

    def refresh(self, *args):
        if not hasattr(self, "apply_button"):
            return
        p = self.values()
        split = p["kind"] != "Straight"
        for key in ("landing_after", "landing_depth"):
            self.fields[key].setEnabled(split)
        self.fields["turn"].setEnabled(p["kind"] in ("L-shaped", "U-shaped"))
        self.fields["gap"].setEnabled(p["kind"] == "U-shaped")
        self.fields["target_riser"].setEnabled(p["count_mode"] == "Target riser")
        self.fields["risers"].setEnabled(p["count_mode"] == "Riser count")
        self.fields["top_depth"].setEnabled(p["top_landing"])
        self.fields["riser_thickness"].setEnabled(p["closed"])
        has_rails = p["railing"] != "None"
        for key in ("rail_sides","rail_height","rail_inset","post_size","post_spacing",
                    "handrail_size","landing_rails","bottom_gap"):
            self.fields[key].setEnabled(has_rails)
        for key in ("glass_thickness","glass_opacity"):
            self.fields[key].setEnabled(p["railing"] == "Glass")
        for key in ("baluster_size","baluster_spacing"):
            self.fields[key].setEnabled(p["railing"] == "Steel")
        for key in ("origin_x", "origin_y", "origin_z", "rotation"):
            self.fields[key].setEnabled(self.target is None)
        try:
            p, n, r, first = resolve(p)
            parts = stair_parts(p)
            bounds = [pt for _, b, _ in parts for pt in corners(b)]
            sx = max(q[0] for q in bounds)-min(q[0] for q in bounds)
            sy = max(q[1] for q in bounds)-min(q[1] for q in bounds)
            unit = self.current_units
            def length(mm):
                return f"{from_mm(mm, unit):.{UNIT_DECIMALS[unit]}f}"
            pitch = math.degrees(math.atan2(r, p["going"]))
            stride = 2 * r + p["going"]
            typical = 600 <= stride <= 640 and r <= 190
            proportion = "Typical proportions" if typical else "Review proportions"
            area = sum((b[3]-b[0]) * (b[4]-b[1]) for _, b, role in parts
                       if role in ("tread", "landing")) / 1e6
            rail = sum(math.dist(a, b) for _, points in railing_routes(p)
                       for a, b in zip(points, points[1:])) / 1000 if has_rails else 0
            self.summary.setText(
                f"<b>Geometry:</b> {n} risers × {length(r)} {unit} = {length(p['height'])} {unit} · Pitch: {pitch:.1f}°<br>"
                f"<b>Overall plan bounds:</b> {length(sx)} × {length(sy)} {unit} · "
                f"<b>2R + G:</b> {length(stride)} {unit} ({proportion})<br>"
                f"<b>BOQ Estimate:</b> Finish area: {area:.2f} m² · RCC vol: 0.00 m³ · Railing: {rail:.2f} m")
            self.summary.setToolTip("Finish area counts tread and landing tops. V1.1 models no reinforced concrete. Railing measures handrail routes.")
            warnings = []
            if not has_rails:
                warnings.append("No guard selected. Check exposed edges or adjoining walls.")
            if not typical:
                warnings.append("Review the rise and going for walking comfort.")
            if has_rails and p["rail_height"] < 900:
                warnings.append("Handrail height is below the 900 mm design guideline.")
            self.message.setText("<b>General design warnings</b><br>" + "<br>".join(warnings or ["None flagged."]))
            self.preview.glass_opacity = p["glass_opacity"] / 100
            self.preview.set_parts(geometry_parts(p))
            self.apply_button.setEnabled(True)
        except ValueError as exc:
            self.preview.set_parts([])
            self.summary.setText("")
            self.message.setText(str(exc))
            self.apply_button.setEnabled(False)
        self.preview.update()

    def open_new(self):
        self.target = None
        self.edit_scene = None
        self.apply_button.setText("Create stair")
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def open_edit(self, group):
        self.target = group
        self.edit_scene = self.app.scene
        self.apply_button.setText("Update stair")
        self.load(group.ext[KEY]["parameters"])
        self.show()
        self.raise_()
        self.activateWindow()

    def apply(self):
        scene = self.app.scene
        vp = self.app.viewport
        try:
            if getattr(scene, "edit_group", None) is not None:
                raise ValueError("Close the group you are editing before making or updating stairs.")
            p, _, _, _ = resolve(self.values())
            if self.target is not None:
                if scene is not self.edit_scene or self.target not in scene.groups:
                    raise ValueError("This stair is no longer in the active document. Close this dialog and select a stair again.")
                if self.target.xform is None or not self.target.children:
                    raise ValueError("This stair has been exploded or restructured. Create a new stair instead.")
                cmd = StairCommand(self.target, build_children(p), p)
            else:
                cmd = StairCommand(make_group(p))
            vp.history.execute(cmd)
            if vp.history.last_error:
                raise ValueError(vp.history.last_error)
            vp.notify_scene_changed()
            vp.update()
            vp.flash_status(f"{DISPLAY_NAME}: stair updated." if self.target else f"{DISPLAY_NAME}: stair created. F2 fits the model.", 5000)
            self.close()
        except Exception as exc:
            QMessageBox.warning(self, DISPLAY_NAME, str(exc))


def selected_stairs(scene):
    result = []
    for item in scene.selection:
        g = getattr(item, "owner", None) or item
        if (g in scene.groups and isinstance(getattr(g, "ext", None), dict)
                and isinstance(g.ext.get(KEY), dict)
                and "parameters" in g.ext[KEY] and g not in result):
            result.append(g)
    return result


_ICON_STRIPS = {
    20: (
        "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"
        "vEk5iP8AAAAASUVORK5CYII="
    ),
    28: (
        "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"
    ),
    48: (
        "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"
    ),
    64: (
        "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"
    ),
    96: (
        "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"
    ),
}

_icon_pixmaps = {}

def stair_symbol(kind, size):
    if size not in _icon_pixmaps:
        strip = QPixmap()
        if not strip.loadFromData(base64.b64decode(_ICON_STRIPS[size]), "PNG"):
            raise ValueError("Could not load Stair Maker toolbar artwork")
        _icon_pixmaps[size] = strip
    column = 0 if kind == "Brand" else (TYPES + ("Edit",)).index(kind)
    return _icon_pixmaps[size].copy(column * size, 0, size, size)


def logo_pixmap():
    return stair_symbol("Brand",96)


def toolbar_icon(kind):
    icon=QIcon()
    for size in (20,28,48,64):
        icon.addPixmap(stair_symbol(kind,size))
    return icon




def setup(app):
    # Resolve app.scene on every action: New/Open may replace the document.
    dialog = StairDialog(app)
    def edit():
        groups = selected_stairs(app.scene)
        if len(groups) != 1:
            QMessageBox.information(app.window, DISPLAY_NAME, "Select exactly one stair created with this plugin (including older Make Stair versions).")
            return
        dialog.open_edit(groups[0])
    menu = app.add_menu(DISPLAY_NAME)
    menu.addAction("Create stair…", dialog.open_new)
    menu.addAction("Edit selected stair…", edit)
    toolbar = QToolBar(DISPLAY_NAME, app.window)
    toolbar.setObjectName(TOOLBAR_NAME)
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    toolbar.setIconSize(QSize(28,28))
    toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    toolbar.setToolTip("Drag the dotted grip to float or dock this toolbar.")
    app.window.addToolBar(Qt.TopToolBarArea, toolbar)
    def preset(kind):
        dialog.open_new()
        dialog.fields["kind"].setCurrentText(kind)
    for kind in TYPES:
        action = toolbar.addAction(toolbar_icon(kind),f"Create {kind.lower()} stair")
        action.setToolTip(f"{DISPLAY_NAME}\nCreate {kind.lower()} stair")
        action.setStatusTip(f"Open the stair maker with the {kind.lower()} layout.")
        action.triggered.connect(lambda checked=False, chosen=kind:preset(chosen))
    toolbar.addSeparator()
    action = toolbar.addAction(toolbar_icon("Edit"),"Edit selected stair")
    action.setToolTip("Edit dimensions of the selected stair")
    action.triggered.connect(lambda checked=False:edit())
    menu.addSeparator()
    toggle = toolbar.toggleViewAction()
    toggle.setText("Show stair toolbar")
    menu.addAction(toggle)
    def context(menu, selection):
        if len(selected_stairs(app.scene)) == 1:
            menu.addAction("Edit stair…", lambda: QTimer.singleShot(0, edit))
    app.add_context_menu(context)
