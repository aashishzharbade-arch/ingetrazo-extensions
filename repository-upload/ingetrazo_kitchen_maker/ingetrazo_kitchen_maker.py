# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo Kitchen Maker V.1, native plugin for IngeTrazo 0.5.7.

Native parametric geometry, Qt interface and procedurally drawn toolbar icons.
Recipe dimensions are millimetres, generated model coordinates are metres.
"""
from __future__ import annotations

import copy
import csv
import math
import numpy as np
from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import Qt, QPointF, QTimer, QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF, QVector3D, QMatrix4x4
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QToolBar, QVBoxLayout, QWidget, QHeaderView)
from core.group import Group
from core.mesh import Mesh
from core.history import Command, InsertGroupCommand
from tools.place_group import PlaceGroupTool

KEY = "ingetrazo_kitchen_maker"
VERSION = "1.0.2"
TITLE = "IngeTrazo Kitchen Maker V.1"
FAMILIES = ("Base", "Wall", "Tall", "High", "Base corner", "Wall corner", "Filler")
STYLES = ("Single door", "Double doors", "Drawers", "Drawer + doors", "Open shelves", "Glass doors", "Appliance niche", "Blind left", "Blind right")
FINISHES = {"Warm white": (0.91, 0.90, 0.86), "Graphite": (0.20, 0.24, 0.28),
    "Sand": (0.70, 0.61, 0.47), "Sage": (0.42, 0.53, 0.43),
    "Ocean blue": (0.17, 0.36, 0.52), "Walnut tone": (0.42, 0.27, 0.16)}
TOPS = {"Light stone": (0.77, 0.79, 0.78), "Dark stone": (0.19, 0.20, 0.22),
        "Timber tone": (0.64, 0.45, 0.26)}
QUADS = ((3,2,1,0), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7))
DEFAULT = dict(family="Base", style="Double doors", width=600., depth=600., height=900.,
    thickness=18., gap=2., plinth=100., shelves=1, drawers=3, hinge="Left", opening=0.,
    handles=True, finish="Warm white", top_finish="Light stone", worktop=True,
    top_thickness=30., overhang=20., backsplash=0., price=0., currency="USD", name="Base cabinet")


def preset(family="Base", style="Double doors", width=600.):
    p = dict(DEFAULT, family=family, style=style, width=float(width), name=f"{family} cabinet")
    if family in ("Wall", "Wall corner"):
        p.update(depth=350., height=720., plinth=0., worktop=False, shelves=2)
    elif family in ("Tall", "High"):
        p.update(height=2100. if family == "Tall" else 2400., worktop=False, shelves=4)
    elif family == "Filler":
        p.update(width=100., shelves=0, worktop=False, name="Filler panel")
    if "corner" in family:
        p.update(width=1000., style="Blind left")
    return p


def catalog():
    """Original presets constructed from standard dimensions, not imported data."""
    out = []
    for family in FAMILIES:
        styles = STYLES[:7] if family in ("Base", "Wall") else ("Double doors", "Open shelves", "Appliance niche")
        if "corner" in family:
            styles = ("Blind left", "Blind right")
        if family == "Filler":
            styles = ("Single door",)
        for style in styles:
            widths = (900.,1200.) if "corner" in family else (50.,100.) if family == "Filler" else (600.,900.)
            for width in widths:
                p = preset(family, style, width)
                p.update(width=width, style=style)
                if family == "Wall" and style == "Appliance niche":
                    continue
                p["name"] = f"{family} {style.lower()} {int(width)}"
                out.append(p)
    return out


def validate(p):
    for key, default in DEFAULT.items():
        if key not in p:
            raise ValueError(f"Missing setting: {key}.")
        if isinstance(default, bool):
            if not isinstance(p[key], bool):
                raise ValueError(f"Invalid {key}.")
        elif isinstance(default, (int, float)):
            if isinstance(p[key], bool) or not isinstance(p[key], (int,float)) or not math.isfinite(p[key]):
                raise ValueError(f"Invalid {key}.")
    if p["family"] not in FAMILIES or p["style"] not in STYLES:
        raise ValueError("Choose a supported cabinet family and front style.")
    if p["finish"] not in FINISHES or p["top_finish"] not in TOPS or p["hinge"] not in ("Left", "Right"):
        raise ValueError("Unknown finish or hinge side.")
    w,d,h,t,b = (p[k] for k in ("width","depth","height","thickness","plinth"))
    if not 30 <= w <= 3000 or not 100 <= d <= 1500 or not 100 <= h <= 3000:
        raise ValueError("Width: 30–3000 mm; depth: 100–1500 mm; height: 100–3000 mm.")
    if not 8 <= t <= 40 or not 1 <= p["gap"] <= 6 or not 0 <= b <= 300:
        raise ValueError("Panel: 8–40 mm; front gap: 1–6 mm; plinth: 0–300 mm.")
    if p["family"] != "Filler" and (w <= 2*t+40 or d <= 3*t+40 or h-b <= 2*t+80):
        raise ValueError("The cabinet must leave room for its panels and internal space.")
    if p["family"] in ("Wall", "Wall corner") and (b != 0 or p["worktop"]):
        raise ValueError("Wall cabinets use no plinth or worktop.")
    if p["family"] == "Filler" and b >= h:
        raise ValueError("Filler height must be greater than its plinth height.")
    if "corner" in p["family"] and p["style"] not in ("Blind left", "Blind right"):
        raise ValueError("This version supports blind left/right corner cabinets.")
    if p["style"] in ("Blind left", "Blind right") and w-d < 120:
        raise ValueError("A blind corner needs width at least 120 mm greater than depth.")
    if any(p[k] != int(p[k]) for k in ("shelves","drawers")) or not 0 <= p["shelves"] <= 8 or not 1 <= p["drawers"] <= 8:
        raise ValueError("Use 0–8 shelves and 1–8 drawers.")
    if (h-b-2*t)/(p["shelves"]+1) < t+15:
        raise ValueError("Too many shelves for this cabinet height.")
    if p["style"] in ("Drawers", "Drawer + doors") and (h-b)/p["drawers"] < 80:
        raise ValueError("Drawer fronts need at least 80 mm height.")
    if not 0 <= p["opening"] <= 110 or not 10 <= p["top_thickness"] <= 100 or not 0 <= p["overhang"] <= 100 or not 0 <= p["backsplash"] <= 600:
        raise ValueError("Opening: 0–110°; top: 10–100 mm; overhang: 0–100 mm; backsplash: 0–600 mm.")
    if not 0 <= p["price"] <= 100000000 or not isinstance(p["currency"],str) or not p["currency"].strip() or len(p["currency"]) > 12:
        raise ValueError("Enter a nonnegative unit price and a currency label (up to 12 characters).")
    if not isinstance(p["name"],str) or not p["name"].strip() or len(p["name"]) > 120:
        raise ValueError("Enter a cabinet name (up to 120 characters).")
    if p["style"] == "Appliance niche" and (h-b < 680 or w < 450):
        raise ValueError("An appliance niche needs 680 mm usable height and 450 mm width.")


def geometry(p):
    """Closed solids in mm. x spans the run, y points backwards, z upwards.

    Blind corners are rectangular carcasses with a blank front zone; L-shaped
    kitchens are made by placing a perpendicular run beside this zone.
    """
    validate(p)
    out = []
    def box(name, x,y,z,X,Y,Z, role="body", transform=None):
        if min(X-x,Y-y,Z-z) <= 0:
            raise ValueError(f"{name} has no usable thickness; adjust the dimensions.")
        points = [(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)]
        if transform:
            points = [transform(*v) for v in points]
        out.append((name, points, QUADS, role))
    w,d,h,t,b,gap = (p[k] for k in ("width","depth","height","thickness","plinth","gap"))
    if p["family"] == "Filler":
        box("Filler face",0,0,b,w,t,h,"front")
        return out
    box("Left side",0,t,b,t,d,h)
    box("Right side",w-t,t,b,w,d,h)
    box("Bottom",t,t,b,w-t,d,b+t)
    box("Back",t,d-t,b+t,w-t,d,h-t)
    box("Top",t,t,h-t,w-t,d,h)
    if b:
        plinth_y=t+min(40.,(d-3*t)/4)
        box("Recessed plinth",0,plinth_y,0,w,plinth_y+t,b,"plinth")
        # Legs are kept inside the carcass footprint.
        front_y=plinth_y+t+5
        leg = min(40., (w-2*t)/3., (d-front_y-t)/3.)
        for i,x in enumerate((t,w-t-leg)):
            for j,y in enumerate((front_y,d-t-leg)):
                box(f"Support {i+1}-{j+1}",x,y,0,x+leg,y+leg,b,"metal")
    style = p["style"]
    if style not in ("Drawers", "Appliance niche"):
        shelf_top = h-((h-b)*0.23 if style == "Drawer + doors" else t)
        for n in range(int(p["shelves"])):
            z = b+t+(shelf_top-b-t)*(n+1)/(p["shelves"]+1)-t/2
            box(f"Shelf {n+1}",t,t+10,z,w-t,d-t,z+t)
    angle = math.radians(p["opening"])
    def front(name,x,X,z,Z,right=False,glass=False,drawer=False):
        pivot = X if right else x
        a = angle if right else -angle
        slide = min(d*0.65, p["opening"]/110*d*0.65) if drawer else 0.
        def transform(vx,vy,vz):
            if drawer:
                return (vx,vy-slide,vz)
            return (pivot+(vx-pivot)*math.cos(a)-vy*math.sin(a),
                    (vx-pivot)*math.sin(a)+vy*math.cos(a),vz)
        if glass:
            f = min(45.,(X-x)/4,(Z-z)/4)
            box(name+" left frame",x,0,z,x+f,t,Z,"front",transform)
            box(name+" right frame",X-f,0,z,X,t,Z,"front",transform)
            box(name+" bottom frame",x+f,0,z,X-f,t,z+f,"front",transform)
            box(name+" top frame",x+f,0,Z-f,X-f,t,Z,"front",transform)
            box(name+" glass",x+f,t/2-2,z+f,X-f,t/2+2,Z-f,"glass",transform)
        else:
            box(name,x,0,z,X,t,Z,"front",transform)
        if p["handles"]:
            hw = min(120.,(X-x)*0.45)
            if drawer:
                hx = (x+X-hw)/2
                hz = Z-min(40.,(Z-z)/3)
                box(name+" handle",hx,-22,hz,hx+hw,-12,hz+8,"metal",transform)
            else:
                hx = x+min(25.,(X-x)/4) if right else X-min(25.,(X-x)/4)-8
                hz = z+(Z-z)*0.65
                hh = min(120.,(Z-z)*0.25)
                box(name+" handle",hx,-22,hz,hx+8,-12,hz+hh,"metal",transform)
        if drawer:
            # Drawer box follows its own front, keeping the carcass fixed.
            dw = min(12.,t)
            bh = min(130.,(Z-z)*0.65)
            left,right=x+t,X-t
            box(name+" tray",left,t,z+8,right,d-2*t,z+8+dw,"body",transform)
            box(name+" tray left",left,t,z+8+dw,left+dw,d-2*t,z+bh,"body",transform)
            box(name+" tray right",right-dw,t,z+8+dw,right,d-2*t,z+bh,"body",transform)
            box(name+" tray rear",left+dw,d-2*t-dw,z+8+dw,right-dw,d-2*t,z+bh,"body",transform)
    low,high = b+gap,h-gap
    if style in ("Drawers", "Drawer + doors"):
        n = int(p["drawers"]) if style == "Drawers" else 1
        start = b if style == "Drawers" else h-(h-b)*0.23
        for i in range(n):
            z = start+(h-start)*i/n
            Z = start+(h-start)*(i+1)/n
            front(f"Drawer {i+1}",gap,w-gap,z+gap,Z-gap,drawer=True)
        high = start-gap
    if style == "Open shelves" or style == "Drawers":
        pass
    elif style == "Appliance niche":
        # Deliberately an empty installation niche, not a branded appliance model.
        niche_top = b+600
        box("Niche shelf",t,t,niche_top,w-t,d-t,niche_top+t)
        front("Upper door",gap,w-gap,niche_top+t+gap,h-gap,p["hinge"] == "Right")
    elif style in ("Blind left", "Blind right"):
        blank = d
        if style == "Blind left":
            box("Blind corner blank",gap,0,low,blank-gap,t,high,"front")
            front("Corner door",blank+gap,w-gap,low,high,True)
        else:
            box("Blind corner blank",w-blank+gap,0,low,w-gap,t,high,"front")
            front("Corner door",gap,w-blank-gap,low,high,False)
    elif style in ("Double doors", "Drawer + doors", "Glass doors"):
        front("Left door",gap,w/2-gap/2,low,high,False,style == "Glass doors")
        front("Right door",w/2+gap/2,w-gap,low,high,True,style == "Glass doors")
    else:
        front("Door",gap,w-gap,low,high,p["hinge"] == "Right")
    if p["worktop"]:
        # End edges remain flush for adjacent cabinets: no overlapping slabs.
        top = p["top_thickness"]
        box("Worktop",0,-p["overhang"],h,w,d,h+top,"top")
        if p["backsplash"]:
            box("Backsplash",0,d-t,h+top,w,d,h+top+p["backsplash"],"top")
    return out


def color_for(role,p):
    return (FINISHES[p["finish"]] if role == "front" else TOPS[p["top_finish"]] if role == "top"
            else {"body":(0.82,0.81,0.76), "plinth":(0.23,0.24,0.25),
                  "metal":(0.36,0.40,0.44), "glass":(0.35,0.68,0.80)}[role])


def build_children(p):
    children=[]
    for name,pts,faces,role in geometry(p):
        mesh = Mesh()
        for face in faces:
            f = mesh.add_face([QVector3D(*(v/1000 for v in pts[i])) for i in face])
            f.attrs["color"] = color_for(role,p)
            if role == "glass":
                f.attrs["opacity"] = 0.35
        child = Group(mesh,name=name)
        child.component = False
        children.append(child)
    return children


def make_group(p):
    g = Group(name=p["name"])
    g.adopt(build_children(p))
    g.component = False
    g.ext = {KEY:dict(version=VERSION, parameters=copy.deepcopy(p))}
    return g


def params_of(g):
    data = (getattr(g,"ext",None) or {}).get(KEY)
    if isinstance(data,dict) and isinstance(data.get("parameters"),dict):
        return data["parameters"]
    return None


def selected(scene):
    result=[]
    for item in scene.selection:
        g = getattr(item,"owner",None) or item
        if g in scene.groups and params_of(g) is not None and g not in result:
            result.append(g)
    return result


class UpdateCabinets(Command):
    """One atomic undo step; all new geometry is prepared before mutation."""
    def __init__(self, updates):
        self.updates = [(g,copy.deepcopy(p),build_children(p)) for g,p in updates]
        self.before = None

    def do(self,scene):
        if any(g not in scene.groups or g.xform is None for g,p,c in self.updates):
            raise ValueError("A cabinet was removed or exploded. Reopen the editor.")
        if self.before is None:
            self.before = [(g,g.children,copy.deepcopy(g.ext),g.name) for g,p,c in self.updates]
        for g,p,children in self.updates:
            g.children = children
            g.ext = copy.deepcopy(g.ext or {})
            g.ext[KEY] = dict(version=VERSION,parameters=copy.deepcopy(p))
            g.name = p["name"]
        scene.version += 1

    def undo(self,scene):
        for g,children,ext,name in self.before:
            g.children,g.ext,g.name = children,copy.deepcopy(ext),name
        scene.version += 1


def execute(app,command):
    app.viewport.history.execute(command)
    if app.viewport.history.last_error:
        raise ValueError(app.viewport.history.last_error)
    app.viewport.notify_scene_changed()
    app.viewport.update()


def adjacent_pose(reference,p,gap=0.):
    if reference.xform is None or params_of(reference) is None:
        raise ValueError("Select an intact Kitchen Maker cabinet first.")
    m = QMatrix4x4(reference.xform)
    m.translate((params_of(reference)["width"]+gap)/1000,0,0)
    return m


def report_rows(groups):
    """Group identical configurations, preserve currency, use decimal cents."""
    totals = {}
    def cabinets(items,ancestors=()):
        for g in items:
            if id(g) in ancestors: continue
            if params_of(g) is not None:
                yield g
            else:
                yield from cabinets(getattr(g,"children",[]) or [],ancestors+(id(g),))
    for g in cabinets(groups):
        p = params_of(g)
        if p is None:
            continue
        validate(p)
        # Include every manufacturing option, except the door's display angle.
        key = tuple((k,str(v)) for k,v in sorted(p.items()) if k != "opening")
        if key not in totals:
            totals[key] = [p,0]
        totals[key][1] += 1
    rows=[]
    for p,n in totals.values():
        price = Decimal(str(p["price"])).quantize(Decimal(".01"),rounding=ROUND_HALF_UP)
        rows.append([p["name"],p["family"],p["style"],p["width"],p["depth"],p["height"],
                     p["finish"],"Yes" if p["worktop"] else "No",n,p["currency"].strip(),str(price),str(price*n)])
    return sorted(rows,key=lambda r:(r[9],r[1],r[0]))


REPORT_HEADERS = ["Name","Family","Front","Width mm","Depth mm","Height mm","Finish","Worktop","Qty","Currency","Unit price","Total"]


def export_csv(path, rows):
    # Spreadsheet-safe text: cabinet names must not become formulas on opening.
    def cell(v):
        return "'"+v if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")) else v
    with open(path,"w",encoding="utf-8-sig",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_HEADERS)
        writer.writerows([[cell(v) for v in row] for row in rows])


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.parts=[]
        self.p=dict(DEFAULT)
        self.setMinimumSize(300,300)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor("#102338"))
        if self.parts:
            def project(v):
                x,y,z=v
                return x+0.58*y,0.22*x-0.34*y-z
            points=[project(v) for _,pts,_,_ in self.parts for v in pts]
            lo=[min(v[k] for v in points) for k in (0,1)]
            hi=[max(v[k] for v in points) for k in (0,1)]
            scale=min((self.width()-55)/max(hi[0]-lo[0],1),(self.height()-75)/max(hi[1]-lo[1],1))
            def screen(v):
                x,y=project(v)
                return QPointF(self.width()/2+(x-(lo[0]+hi[0])/2)*scale,
                               (self.height()-20)/2+(y-(lo[1]+hi[1])/2)*scale)
            visible=[]
            view=(0.58,-1.,0.4676)
            for _,pts,faces,role in self.parts:
                for face in faces:
                    a,b,c=[pts[i] for i in face[:3]]
                    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
                    normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    if sum(normal[i]*view[i] for i in range(3)) <= 0:
                        continue
                    depth=sum(sum(pts[j][i]*view[i] for i in range(3)) for j in face)/len(face)
                    visible.append((depth,pts,face,role,normal))
            # A per-pixel depth buffer prevents shelves showing through closed
            # doors; painter's average-face sorting cannot handle tall panels.
            width,height=self.width(),self.height()
            pixels=np.empty((height,width,3),dtype=np.uint8);pixels[:]=(16,35,56)
            depth=np.full((height,width),-np.inf)
            outlines=[]
            ordered=sorted(visible,key=lambda f:(f[3]=="glass",f[0]))
            for _,pts,face,role,normal in ordered:
                rgb=np.array(color_for(role,self.p))*255
                if normal[2]>0: rgb=np.minimum(255,rgb*1.10)
                corners=[]
                for index in face:
                    pt=screen(pts[index])
                    corners.append((pt.x(),pt.y(),sum(pts[index][i]*view[i] for i in range(3))))
                for n in range(1,len(corners)-1):
                    a,b,c=[np.array(corners[i]) for i in (0,n,n+1)]
                    x0=max(0,int(math.floor(min(a[0],b[0],c[0]))));x1=min(width,int(math.ceil(max(a[0],b[0],c[0])))+1)
                    y0=max(0,int(math.floor(min(a[1],b[1],c[1]))));y1=min(height,int(math.ceil(max(a[1],b[1],c[1])))+1)
                    den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                    if abs(den)<1e-8 or x1<=x0 or y1<=y0: continue
                    yy,xx=np.mgrid[y0:y1,x0:x1]
                    u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
                    v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den
                    z=u*a[2]+v*b[2]+(1-u-v)*c[2]
                    region=depth[y0:y1,x0:x1]
                    mask=(u>=0)&(v>=0)&(u+v<=1)&(z>region)
                    target=pixels[y0:y1,x0:x1]
                    target[mask]=rgb if role!="glass" else target[mask]*.60+rgb*.40
                    region[mask]=z[mask]
                outlines.append(corners)
            for corners in outlines:
                for a,b in zip(corners,corners[1:]+corners[:1]):
                    count=max(2,int(max(abs(b[0]-a[0]),abs(b[1]-a[1])))+1)
                    segment=np.linspace(a,b,count)
                    xx=np.clip(np.rint(segment[:,0]).astype(int),0,width-1)
                    yy=np.clip(np.rint(segment[:,1]).astype(int),0,height-1)
                    mask=segment[:,2]>=depth[yy,xx]-2/scale
                    pixels[yy[mask],xx[mask]]=(74,90,106)
            img=QImage(pixels.data,width,height,width*3,QImage.Format_RGB888)
            painter.drawImage(0,0,img)
        painter.setPen(QColor("#90a9c0"))
        painter.drawText(self.rect().adjusted(12,0,-12,-12),Qt.AlignBottom|Qt.AlignRight,"IngeTrazo Tutorials")


class Editor(QDialog):
    def __init__(self,app,target=None,beside=None):
        super().__init__(app.window)
        self.app,self.target,self.beside=app,target,beside
        self.scene=app.scene
        self.original=copy.deepcopy(params_of(target)) if target else None
        self.reference_original=copy.deepcopy(params_of(beside)) if beside else None
        self.fields={}
        self.loading=True
        self.setWindowTitle(TITLE+ (" — Edit cabinet" if target else " — Cabinet library"))
        self.resize(1000,740)
        outer=QVBoxLayout(self)
        outer.addWidget(QLabel("<h2>IngeTrazo Kitchen Maker <small>V.1</small></h2>Parametric cabinets · Dimensions in millimetres"))
        body=QHBoxLayout();outer.addLayout(body,1)
        tabs=QTabWidget();body.addWidget(tabs,1)
        right=QVBoxLayout();body.addLayout(right,1)
        self.preview=Preview();right.addWidget(self.preview,1)
        self.status=QLabel();self.status.setWordWrap(True);right.addWidget(self.status)
        right.addWidget(QLabel("Front faces local −Y. Width follows +X.\nHeight includes the plinth, excludes the worktop.\nBlind corners reserve a blank front for a perpendicular run."))
        self.presets=catalog()
        library_page=QWidget()
        library_layout=QVBoxLayout(library_page)
        library_form=QFormLayout()
        library_layout.addLayout(library_form)
        self.category=QComboBox()
        self.category.addItems(("Base","Wall","Base corner","Wall corner","Tall","High","Filler"))
        self.library=QComboBox()
        self.library.setMinimumContentsLength(22)
        self.library.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.library.setPlaceholderText("Choose a cabinet preset…")
        library_form.addRow("Category",self.category)
        library_form.addRow("Cabinet preset",self.library)
        self.library_info=QLabel()
        self.library_info.setWordWrap(True)
        library_layout.addWidget(self.library_info)
        hint=QLabel("Choose a category, then a cabinet preset.\n\nAdjust its dimensions in Cabinet and finishes in Details. Choosing another preset replaces those settings.")
        hint.setWordWrap(True)
        library_layout.addWidget(hint)
        library_layout.addStretch()
        tabs.addTab(library_page,"Library")
        self.category.currentTextChanged.connect(self.filter_library)
        self.library.currentIndexChanged.connect(self.load_preset)
        forms={}
        for title in ("Cabinet","Details","Placement"):
            widget=QWidget();form=QFormLayout(widget)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget)
            tabs.addTab(scroll,title);forms[title]=form
        def field(key,label,tab="Cabinet",options=None,limits=None):
            value=DEFAULT.get(key,0.)
            if options:
                w=QComboBox();w.addItems(options);w.currentTextChanged.connect(self.refresh)
            elif isinstance(value,bool):
                w=QCheckBox();w.toggled.connect(self.refresh)
            elif isinstance(value,str):
                w=QLineEdit();w.textChanged.connect(self.refresh)
            else:
                w=QSpinBox() if isinstance(value,int) else QDoubleSpinBox()
                w.setRange(*(limits or (0,100000)))
                if isinstance(w,QDoubleSpinBox): w.setDecimals(2)
                w.valueChanged.connect(self.refresh)
            self.fields[key]=w;forms[tab].addRow(label,w)
        field("name","Name")
        field("family","Family",options=FAMILIES)
        field("style","Front style",options=STYLES)
        for key,label,limits in (("width","Width",(30,3000)),("depth","Depth",(100,1500)),("height","Height",(100,3000)),("thickness","Panel thickness",(8,40)),("plinth","Plinth height",(0,300)),("shelves","Shelf count",(0,8)),("drawers","Drawer count",(1,8))):
            field(key,label,limits=limits)
        field("finish","Front finish",options=list(FINISHES))
        field("hinge","Single-door hinge",options=("Left","Right"))
        field("opening","Door / drawer opening","Details",limits=(0,110))
        field("gap","Front gap","Details",limits=(1,6))
        field("handles","Show handles","Details")
        field("worktop","Add worktop","Details")
        field("top_finish","Worktop finish","Details",options=list(TOPS))
        field("top_thickness","Worktop thickness","Details",limits=(10,100))
        field("overhang","Front overhang","Details",limits=(0,100))
        field("backsplash","Backsplash height","Details",limits=(0,600))
        field("price","Unit price (complete cabinet)","Details",limits=(0,100000000))
        field("currency","Currency label","Details")
        self.mode=QComboBox();self.mode.addItems(("Click to place","Exact coordinates","Next to selected (+X)"))
        forms["Placement"].addRow("Placement",self.mode)
        for key,label in (("x","X"),("y","Y"),("z","Z / elevation"),("rotation","Rotation about Z (degrees)"),("spacing","Gap after selected")):
            field(key,label,"Placement",limits=(-1000000,1000000) if key!="rotation" else (-360,360))
        self.mode.currentTextChanged.connect(self.refresh)
        if target:
            self.mode.setEnabled(False)
            for key in ("x","y","z","rotation","spacing"): self.fields[key].setEnabled(False)
            tabs.setCurrentIndex(1)
        if beside: self.mode.setCurrentIndex(2)
        buttons=QHBoxLayout();outer.addLayout(buttons)
        buttons.addStretch()
        self.apply_button=QPushButton("Update cabinet" if target else "Create cabinet")
        self.apply_button.clicked.connect(self.apply);buttons.addWidget(self.apply_button)
        close=QPushButton("Close");close.clicked.connect(self.reject);buttons.addWidget(close)
        self.set_params(self.original or preset())
        self.category.setCurrentText((self.original or DEFAULT)["family"])
        self.filter_library()
        self.loading=False
        self.refresh()

    def set_params(self,p):
        old=self.loading;self.loading=True
        for key,value in p.items():
            w=self.fields.get(key)
            if w is None: continue
            if isinstance(w,QComboBox): w.setCurrentText(value)
            elif isinstance(w,QCheckBox): w.setChecked(value)
            elif isinstance(w,QLineEdit): w.setText(value)
            else: w.setValue(value)
        self.loading=old
        self.refresh()

    def filter_library(self,*args):
        self.library.blockSignals(True)
        self.library.clear()
        for index,p in enumerate(self.presets):
            if p["family"]==self.category.currentText():
                self.library.addItem(f"{p['style']} — {p['width']:g} mm",index)
        self.library.setCurrentIndex(-1)
        self.library.blockSignals(False)
        self.library_info.setText(f"{self.library.count()} presets in {self.category.currentText()}. Dimensions are in millimetres.")
        if not self.loading and self.library.count():
            self.library.setCurrentIndex(0)

    def load_preset(self,index):
        if index<0 or self.loading: return
        p=self.presets[self.library.itemData(index)]
        self.set_params(p)
        if not self.target:
            self.fields["z"].setValue(1500 if "Wall" in p["family"] else 0)

    def parameters(self):
        p={}
        for key in DEFAULT:
            w=self.fields[key]
            p[key] = w.currentText() if isinstance(w,QComboBox) else w.isChecked() if isinstance(w,QCheckBox) else w.text().strip() if isinstance(w,QLineEdit) else w.value()
        return p

    def refresh(self,*args):
        if self.loading: return
        try:
            p=self.parameters()
            self.preview.parts=geometry(p);self.preview.p=p
            self.status.setText(f"{p['width']:g} × {p['depth']:g} × {p['height']:g} mm\n{len(self.preview.parts)} modeled parts · Cabinet settings remain editable")
            self.apply_button.setEnabled(True)
        except (ValueError,KeyError) as e:
            self.preview.parts=[];self.status.setText(str(e));self.apply_button.setEnabled(False)
        self.preview.update()
        if not self.target:
            exact=self.mode.currentIndex()==1
            for key in ("x","y","z"): self.fields[key].setEnabled(exact)
            self.fields["rotation"].setEnabled(self.mode.currentIndex()!=2)
            self.fields["spacing"].setEnabled(self.mode.currentIndex()==2)

    def apply(self):
        try:
            if self.app.scene is not self.scene or self.scene.edit_group is not None:
                raise ValueError("Return to the main model and reopen the editor in the current document.")
            p=self.parameters();validate(p)
            if self.target:
                if self.target not in self.scene.groups or params_of(self.target)!=self.original:
                    raise ValueError("The cabinet changed. Reopen its editor before updating.")
                execute(self.app,UpdateCabinets([(self.target,p)]))
            else:
                g=make_group(p)
                mode=self.mode.currentIndex()
                if mode==2:
                    refs=[self.beside] if self.beside else selected(self.scene)
                    if len(refs)!=1 or refs[0] not in self.scene.groups:
                        raise ValueError("Select exactly one existing Kitchen Maker cabinet.")
                    if self.beside and params_of(self.beside)!=self.reference_original:
                        raise ValueError("The reference cabinet changed. Reopen Add next.")
                    g.xform=adjacent_pose(refs[0],p,self.fields["spacing"].value())
                else:
                    if mode==1:
                        g.xform.translate(*(self.fields[k].value()/1000 for k in ("x","y","z")))
                    g.xform.rotate(self.fields["rotation"].value(),0,0,1)
                if mode==0:
                    self.app.viewport.set_active_tool(PlaceGroupTool(g,anchor=QVector3D(0,0,0)))
                    self.app.viewport.flash_status("Kitchen Maker: click to place the cabinet origin. Esc cancels.",6000)
                else:
                    execute(self.app,InsertGroupCommand(g))
                    self.scene.selection.clear();self.scene.selection.add(g)
                    self.app.viewport.update()
            self.accept()
        except (ValueError,KeyError) as e:
            QMessageBox.warning(self,TITLE,str(e))


class Report(QDialog):
    def __init__(self,app):
        super().__init__(app.window)
        self.setWindowTitle(TITLE+" — Cost report")
        self.resize(1050,480)
        self.rows=report_rows(app.scene.groups)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel("All Kitchen Maker cabinets in this model, including nested groups. Unit price includes its worktop and fittings.\nPlanning estimate only: taxes, labour, wastage and installation are not added."))
        table=QTableWidget(len(self.rows),len(REPORT_HEADERS));table.setHorizontalHeaderLabels(REPORT_HEADERS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for i,row in enumerate(self.rows):
            for j,value in enumerate(row): table.setItem(i,j,QTableWidgetItem(str(value)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(table)
        sums={}
        for row in self.rows: sums[row[9]]=sums.get(row[9],Decimal(0))+Decimal(row[11])
        layout.addWidget(QLabel("Totals: "+(" · ".join(f"{currency} {v:,.2f}" for currency,v in sorted(sums.items())) or "No cabinets")))
        btn=QPushButton("Export CSV…");btn.clicked.connect(self.export);layout.addWidget(btn)

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,"Save kitchen cost report","kitchen-cost-report.csv","CSV files (*.csv)")
        if not path: return
        try: export_csv(path,self.rows)
        except OSError as e: QMessageBox.warning(self,TITLE,str(e))


def toolbar_icon(kind):
    pix=QPixmap(64,64);pix.fill(Qt.transparent)
    painter=QPainter(pix);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#163d5c"),3));painter.setBrush(QColor("#57b7ea"))
    if kind in ("Library","Add next","Edit"):
        painter.drawRect(10,15,40,38);painter.drawLine(30,15,30,53)
        painter.setPen(QPen(QColor("#ffffff"),3));painter.drawLine(25,27,25,39);painter.drawLine(35,27,35,39)
        if kind=="Add next":
            painter.setPen(QPen(QColor("#ed9b38"),5));painter.drawLine(46,8,46,26);painter.drawLine(37,17,55,17)
        elif kind=="Edit":
            painter.setPen(QPen(QColor("#ed9b38"),6));painter.drawLine(33,52,55,30)
    elif kind=="Open / close":
        painter.drawRect(8,13,30,40);painter.setBrush(QColor("#ffcb7c"));painter.drawPolygon(QPolygonF([QPointF(38,13),QPointF(55,24),QPointF(55,61),QPointF(38,53)]))
    elif kind=="Swap hinge":
        painter.drawLine(8,32,56,32);painter.drawLine(8,32,22,18);painter.drawLine(56,32,42,46)
    elif kind=="Finishes":
        for x,c in ((6,"#e0c3a0"),(24,"#587e64"),(42,"#438db9")):
            painter.setBrush(QColor(c));painter.drawRect(x,15,16,36)
    else:
        painter.setBrush(QColor("#f0ece1"));painter.drawRect(13,8,38,48)
        for y in (20,30,40): painter.drawLine(20,y,44,y)
    painter.end();return QIcon(pix)


def setup(app):
    dialogs=[]
    def show(dialog):
        dialogs.append(dialog)
        dialog.finished.connect(lambda _ : dialogs.remove(dialog) if dialog in dialogs else None)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
    def action(name):
        try:
            if app.scene.edit_group is not None:
                raise ValueError("Close the group you are editing first.")
            targets=selected(app.scene)
            if name=="Library": show(Editor(app));return
            if name=="Cost report": show(Report(app));return
            if not targets: raise ValueError("Select a Kitchen Maker cabinet first.")
            if name in ("Edit","Add next"):
                if len(targets)!=1: raise ValueError("Select exactly one cabinet.")
                show(Editor(app,target=targets[0] if name=="Edit" else None,beside=targets[0] if name=="Add next" else None));return
            updates=[]
            if name=="Finishes":
                # Use a modal picker so selection/document cannot change underneath.
                from PySide6.QtWidgets import QInputDialog
                finish,ok=QInputDialog.getItem(app.window,TITLE,"Front finish for selected cabinets",list(FINISHES),0,False)
                if not ok: return
            for g in targets:
                p=copy.deepcopy(params_of(g))
                if name=="Open / close": p["opening"]=0. if p["opening"]>0 else 90.
                elif name=="Swap hinge":
                    p["hinge"]="Right" if p["hinge"]=="Left" else "Left"
                    if p["style"] in ("Blind left","Blind right"):
                        p["style"]="Blind right" if p["style"]=="Blind left" else "Blind left"
                elif name=="Finishes": p["finish"]=finish
                updates.append((g,p))
            execute(app,UpdateCabinets(updates))
        except (ValueError,KeyError) as e: QMessageBox.warning(app.window,TITLE,str(e))
    menu=app.add_menu(TITLE)
    toolbar=QToolBar(TITLE,app.window)
    toolbar.setObjectName("IngeTrazoKitchenMakerToolbarV1")
    toolbar.setMovable(True);toolbar.setFloatable(True);toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    toolbar.setIconSize(QSize(26,26))
    for name in ("Library","Add next","Edit","Open / close","Swap hinge","Finishes","Cost report"):
        a=toolbar.addAction(toolbar_icon(name),name)
        a.setToolTip(f"Kitchen Maker — {name}")
        a.triggered.connect(lambda checked=False,n=name:action(n))
        menu.addAction(a)
    app.window.addToolBar(Qt.TopToolBarArea,toolbar)
    menu.addSeparator();menu.addAction(toolbar.toggleViewAction())
    def context(menu,selection):
        if selected(app.scene):
            sub=menu.addMenu(TITLE)
            for name in ("Edit","Add next","Open / close","Swap hinge"):
                sub.addAction(name,lambda n=name:QTimer.singleShot(0,lambda:action(n)))
    app.add_context_menu(context)
    app.window._ingetrazo_kitchen_maker=(toolbar,dialogs,action)
