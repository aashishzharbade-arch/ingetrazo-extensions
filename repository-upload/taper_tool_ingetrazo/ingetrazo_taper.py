# SPDX-License-Identifier: GPL-3.0-or-later
"""Original mesh taper extension for IngeTrazo 0.5.7. No Rhino dependency."""
import copy
import math
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QVector3D as V, QMatrix4x4, QAction, QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QDoubleSpinBox, QSpinBox, QPushButton, QToolBar, QMessageBox
from core.mesh import Mesh, Face, Edge
from core.group import Group, world_mesh, transformed_mesh
from core.history import Command
from tools.base import Tool

KEY = 'ingetrazo_taper'
VERSION = '1.0.0'
DISPLAY_NAME = 'Taper Tool for IngeTrazo V1.0'
EPS = 1e-7
dot = V.dotProduct

def center_of(points):
    if not points: raise ValueError('Selected object has no mesh geometry.')
    return V(*[(min(getattr(p,c)() for p in points)+max(getattr(p,c)() for p in points))/2 for c in ('x','y','z')])


class Mapping:
    def __init__(self, a, b, direction, reference, target, flat=False, infinite=True):
        self.a, self.axis = V(a), V(b)-V(a)
        self.length = self.axis.length()
        if self.length < EPS or reference < EPS:
            raise ValueError('Axis length and reference distance must be greater than zero.')
        self.axis /= self.length
        d = V(direction)-self.axis*dot(direction,self.axis)
        if d.length() < EPS: raise ValueError('Pick the reference point away from the axis.')
        self.direction = d.normalized()
        self.ratio = target/reference
        if not math.isfinite(self.ratio) or not EPS < self.ratio <= 1000:
            raise ValueError('Target/reference ratio must be greater than zero and at most 1000.')
        self.flat, self.infinite = flat, infinite

    def __call__(self, p):
        rel = V(p)-self.a
        t = dot(rel,self.axis)/self.length
        if not self.infinite: t = max(0.,min(1.,t))
        factor = 1+(self.ratio-1)*t
        if factor <= EPS: raise ValueError('This taper collapses or reverses geometry. Reduce the taper or turn Infinite off.')
        radial = self.direction*dot(rel,self.direction) if self.flat else rel-self.axis*dot(rel,self.axis)
        return V(p)+radial*(factor-1)


def split_polygon(poly, origin, normal, distance):
    """Split a convex polygon at an axis-normal plane, keeping both sides."""
    values = [dot(p-origin,normal)-distance for p in poly]
    if min(values) >= -EPS or max(values) <= EPS: return [poly]
    sides = [[],[]]
    for i,p in enumerate(poly):
        q = poly[(i+1)%len(poly)]; x,y = values[i],values[(i+1)%len(poly)]
        if x <= EPS: sides[0].append(p)
        if x >= -EPS: sides[1].append(p)
        if x*y < -EPS*EPS:
            point = p+(q-p)*(x/(x-y))
            sides[0].append(point); sides[1].append(point)
    return [s for s in sides if len(s)>=3]


def deform_mesh(source, mapping, rigid=False, divisions=4):
    if not source.vertices: raise ValueError('Selected object has no mesh geometry.')
    result = Mesh()
    if rigid:
        pts = [v.position for v in source.vertices]
        center = center_of(pts)
        matrix = QMatrix4x4(); matrix.translate(mapping(center)-center)
        return transformed_mesh(source,matrix)
    # Cut triangles at regular axial stations before deforming. Result faces
    # remain planar triangles; shared intersection vertices weld in Mesh.
    cuts = [mapping.length*i/divisions for i in range(divisions+1)]
    for face in source.faces:
        triangles = list(face.triangulate())
        if not triangles: raise ValueError('A selected face cannot be triangulated.')
        for tri in triangles:
            polygons = [list(tri)]
            for t in cuts:
                polygons = [part for poly in polygons for part in split_polygon(poly,mapping.a,mapping.axis,t)]
            for poly in polygons:
                pts = [mapping(p) for p in poly]
                for i in range(1,len(pts)-1):
                    if V.crossProduct(pts[i]-pts[0],pts[i+1]-pts[0]).length()<1e-12: continue
                    f = result.add_face([pts[0],pts[i],pts[i+1]])
                    f.attrs = copy.deepcopy(face.attrs)
        if len(result.faces)>200000: raise ValueError('Result exceeds 200,000 faces. Reduce axial divisions or selection size.')
    for edge in result.edges: edge.soft = True
    for edge in source.edges:
        a,b = V(edge.a),V(edge.b)
        start,end = dot(a-mapping.a,mapping.axis),dot(b-mapping.a,mapping.axis)
        params = [0.,1.]
        if abs(end-start)>EPS:
            params += [(t-start)/(end-start) for t in cuts if EPS < (t-start)/(end-start) < 1-EPS]
        points = [mapping(a+(b-a)*t) for t in sorted(set(params))]
        for p,q in zip(points,points[1:]):
            if (q-p).length()<EPS: continue
            e=result.add_edge(p,q);e.soft=edge.soft;e.hidden=edge.hidden;e.layer=edge.layer
    return result


class Selection:
    def __init__(self, scene):
        if scene.edit_group is not None:
            raise ValueError('Exit group editing, then select the group to taper.')
        self.scene = scene
        self.version = scene.version-scene.view_version
        self.selected = set(scene.selection)
        self.groups = [g for g in scene.groups if g in self.selected]
        self.faces = [f for f in scene.mesh.faces if f in self.selected]
        self.edges = [e for e in scene.mesh.edges if e in self.selected or any(f in self.faces for f in e.faces)]
        recognized = set(self.groups+self.faces+self.edges)
        if not recognized or self.selected-recognized:
            raise ValueError('Select mesh groups, faces or edges only.')
        if any(f not in self.faces for e in self.edges for f in e.faces):
            raise ValueError('Select the complete connected object, or group it first. Partial face boundaries are not supported.')
        if any(g.billboard or not scene.entity_visible(g) for g in self.groups):
            raise ValueError('Select visible mesh objects; face-me billboards are not supported.')
        self.sources = [(g,transformed_mesh(world_mesh(g),QMatrix4x4())) for g in self.groups]
        if self.faces or self.edges:
            mesh=Mesh()
            for f in self.faces:
                new=mesh.add_face(f.vertices,f.holes);new.attrs=copy.deepcopy(f.attrs)
            for e in self.edges:
                new=mesh.add_edge(e.a,e.b);new.soft=e.soft;new.hidden=e.hidden;new.layer=e.layer
            self.sources.append((None,mesh))

    def valid(self,scene):
        return scene is self.scene and scene.edit_group is None and self.version == scene.version-scene.view_version

    def build(self,mapping,rigid,divisions):
        output=[]
        for original,mesh in self.sources:
            group=Group(deform_mesh(mesh,mapping,rigid,divisions),name=(original.name if original else 'Loose geometry')+' · Taper Tool')
            if original:
                group.layer=original.layer;group.material=copy.deepcopy(original.material);group.ifc=copy.deepcopy(original.ifc)
            output.append(group)
        return output


class TaperCommand(Command):
    def __init__(self,selection,result,copy_result):
        self.source,self.result,self.copy=selection,result,copy_result
        self.before=self.after=None

    def do(self,scene):
        if self.before is None:
            if not self.source.valid(scene): raise ValueError('Document changed. Start Taper again.')
            self.before=scene.mesh.capture_state();self.groups_before=list(scene.groups);self.selection_before=set(scene.selection)
            try:
                if not self.copy:
                    for face in self.source.faces: scene.mesh.remove_face(face)
                    for edge in self.source.edges:
                        if edge in scene.mesh.edges and not edge.faces: scene.mesh.remove_edge(edge)
                    scene.mesh.prune_orphan_vertices()
                    scene.groups[:]=[g for g in scene.groups if g not in self.source.groups]
                scene.groups.extend(self.result)
                self.after=scene.mesh.capture_state();self.groups_after=list(scene.groups)
            except Exception:
                scene.mesh.restore_state(self.before);scene.groups[:]=self.groups_before
                raise
        else:
            scene.mesh.restore_state(self.after);scene.groups[:]=self.groups_after
        scene.selection=set(self.result);scene.version+=1

    def undo(self,scene):
        scene.mesh.restore_state(self.before);scene.groups[:]=self.groups_before
        scene.selection=set(self.selection_before);scene.version+=1


def interaction(editor):
    # Local class avoids an unintended loader-created menu tool.
    class TaperInteraction(Tool):
        name='Taper';uses_snap=True;wireframe_color=(1.,.55,.08,1.)
        vcb_label='Target distance'
        def on_activate(self,vp): editor.update_status()
        def on_deactivate(self,vp):
            if not editor.finished: editor.reject()
        def on_cancel(self,vp): editor.reject()
        def drag_plane(self,vp):
            if len(editor.points)>=2: return editor.points[1],(editor.points[1]-editor.points[0]).normalized()
            return None
        def on_hover(self,ctx):
            if not editor.valid(): return
            if len(editor.points)==3:
                editor.measure_target(ctx.world)
        def on_click(self,ctx):
            if not editor.valid(): return
            p=V(ctx.world);n=len(editor.points)
            if n==1 and (p-editor.points[0]).length()<EPS:
                editor.status.setText('Axis endpoints must differ.');return
            if n==2:
                axis=(editor.points[1]-editor.points[0]).normalized()
                d=p-editor.points[0];d-=axis*dot(d,axis)
                if d.length()<EPS:editor.status.setText('Pick the reference point away from the axis.');return
                editor.reference.setValue(d.length()*1000)
            if n<3:
                editor.points.append(p);editor.update_status()
            else:
                editor.measure_target(p);editor.apply()
        def on_value(self,vp,value):
            # Host numeric length input is converted to metres by the host.
            if isinstance(value,(int,float)) and math.isfinite(value) and value>0 and len(editor.points)==3:
                editor.target.setValue(value*1000);editor.apply();return True
            return False
        def rubber_band_lines(self): return editor.lines if not editor.finished else []
        def on_key(self,vp,key,modifiers):
            if key in (Qt.Key_Return,Qt.Key_Enter):editor.apply();return True
            return False
    return TaperInteraction()


class Editor(QDialog):
    def __init__(self,app,source):
        super().__init__(app.window)
        self.app,self.source=app,source;self.points=[];self.lines=[];self.result=None;self.finished=False
        self.setWindowTitle(DISPLAY_NAME);self.setWindowFlag(Qt.Tool,True)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('<b>Taper Tool for IngeTrazo V1.0</b> · distances in mm'))
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.reference=QDoubleSpinBox();self.target=QDoubleSpinBox()
        for title,field in [('Reference distance',self.reference),('Target distance',self.target)]:
            field.setDecimals(3);field.setRange(.001,1e9);field.setValue(1000);field.setSuffix(' mm')
            row=QHBoxLayout();row.addWidget(QLabel(title));row.addWidget(field);layout.addLayout(row)
        self.copy=QCheckBox('Copy (keep originals)');self.flat=QCheckBox('Flat (reference direction only)');self.rigid=QCheckBox('Rigid (translate each selected object)');self.infinite=QCheckBox('Infinite (extend taper beyond axis)');self.infinite.setChecked(True)
        for field in (self.copy,self.flat,self.rigid,self.infinite):layout.addWidget(field);field.toggled.connect(self.refresh)
        self.divisions=QSpinBox();self.divisions.setRange(1,32);self.divisions.setValue(4)
        row=QHBoxLayout();row.addWidget(QLabel('Axial divisions'));row.addWidget(self.divisions);layout.addLayout(row)
        layout.addWidget(QLabel('Orange wire preview · originals change only on Apply\nEsc / Cancel discards the draft.'))
        row=QHBoxLayout();self.apply_button=QPushButton('Apply');again=QPushButton('Pick axis again');cancel=QPushButton('Cancel')
        for button in (again,self.apply_button,cancel):
            button.setAutoDefault(False);row.addWidget(button)
        layout.addLayout(row);layout.addWidget(QLabel('IngeTrazo Tutorials · GPL-3.0-or-later'))
        self.reference.valueChanged.connect(self.refresh);self.target.valueChanged.connect(self.refresh);self.divisions.valueChanged.connect(self.refresh)
        again.clicked.connect(self.restart);cancel.clicked.connect(self.reject);self.apply_button.clicked.connect(self.apply)
        self.tool=interaction(self);self.update_status();self.resize(440,360)

    def valid(self):
        if self.finished:return False
        if not self.source.valid(self.app.scene):
            self.status.setText('Document changed. Cancel and start Taper again.');self.result=None;self.lines=[];self.apply_button.setEnabled(False);return False
        return True

    def update_status(self):
        labels=['1/4 — Click axis start in the model.','2/4 — Click axis end (use geometry snaps for 3D).','3/4 — Click reference distance away from the axis.','4/4 — Move the pointer to preview; click target distance to apply.']
        self.status.setText(labels[min(len(self.points),3)])
        self.refresh()

    def restart(self):
        self.points=[];self.result=None;self.lines=[];self.update_status();self.app.viewport.setFocus()

    def mapping(self):
        return Mapping(self.points[0],self.points[1],self.points[2]-self.points[0],self.reference.value()/1000,self.target.value()/1000,self.flat.isChecked(),self.infinite.isChecked())

    def measure_target(self,p):
        axis=(self.points[1]-self.points[0]).normalized()
        direction=self.points[2]-self.points[0];direction-=axis*dot(direction,axis)
        rel=V(p)-self.points[1];radial=rel-axis*dot(rel,axis)
        distance=abs(dot(radial,direction.normalized())) if self.flat.isChecked() else radial.length()
        self.target.setValue(max(.001,distance*1000))

    def refresh(self,*args):
        if not self.valid():return
        self.result=None;self.lines=[];self.apply_button.setEnabled(False)
        if len(self.points)>1:self.lines=[(self.points[0],self.points[1])]
        if len(self.points)<3:self.app.viewport.update();return
        try:
            m=self.mapping()
            # Preview only transforms a bounded sample of original edges.
            lines=[]
            for original,mesh in self.source.sources:
                if self.rigid.isChecked():
                    ps=[v.position for v in mesh.vertices];center=center_of(ps)
                    delta=m(center)-center;fn=lambda p:V(p)+delta
                else:fn=m
                for v in mesh.vertices:fn(v.position)
                stride=max(1,len(mesh.edges)//5000)
                lines.extend((fn(e.a),fn(e.b)) for e in mesh.edges[::stride])
            self.lines+=lines;self.apply_button.setEnabled(True)
        except ValueError as exc:self.status.setText(str(exc))
        self.app.viewport.update()

    def apply(self,*args):
        if not self.valid() or len(self.points)<3:return
        try:
            result=self.source.build(self.mapping(),self.rigid.isChecked(),self.divisions.value())
            self.app.viewport.history.execute(TaperCommand(self.source,result,self.copy.isChecked()))
            if self.app.viewport.history.last_error:raise ValueError(self.app.viewport.history.last_error)
        except (ValueError,RuntimeError) as exc:self.status.setText(str(exc));return
        self.app.viewport.notify_scene_changed();self.reject()

    def reject(self):
        if self.finished:return
        self.finished=True;self.lines=[]
        if self.app.viewport.active_tool is self.tool:self.app.viewport.set_active_tool(None)
        self.app.viewport.update();super().reject()

    def closeEvent(self,event):self.reject();event.accept()


def icon():
    px=QPixmap(32,32);px.fill(Qt.transparent);p=QPainter(px);p.setPen(QPen(QColor('#159de8'),2))
    for a,b in [((5,27),(27,27)),((5,27),(11,5)),((27,27),(21,5)),((11,5),(21,5))]:p.drawLine(*a,*b)
    p.setPen(QPen(QColor('#f29b38'),2));p.drawLine(16,3,16,29);p.end();return QIcon(px)


def setup(app):
    if hasattr(app.window,'_ingetrazo_taper_tool'):return
    state={'editor':None}
    def launch():
        old=state['editor']
        if old and not old.finished:old.show();old.raise_();return
        try:source=Selection(app.scene)
        except ValueError as exc:QMessageBox.information(app.window,DISPLAY_NAME,str(exc));return
        editor=Editor(app,source);state['editor']=editor;editor.show()
        app.viewport.set_active_tool(editor.tool);app.viewport.setFocus()
    bar=QToolBar(DISPLAY_NAME,app.window);bar.setObjectName(KEY+'_toolbar');bar.setMovable(True);bar.setFloatable(True)
    action=QAction(icon(),DISPLAY_NAME,bar);action.setToolTip('Select objects, then pick axis and taper distances');action.triggered.connect(launch);bar.addAction(action);app.window.addToolBar(bar)
    app.add_menu_action(DISPLAY_NAME,launch,tip='Interactive mesh taper')
    app.window._ingetrazo_taper_tool=(bar,state,launch)
