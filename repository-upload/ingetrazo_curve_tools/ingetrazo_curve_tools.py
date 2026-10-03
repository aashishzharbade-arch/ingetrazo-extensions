# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo Curve Tools V1.0 — native, editable sampled curves for 0.5.7.

Independent Python implementation of standard curve mathematics. No reference
extension code/assets bundled. Recipe and geometry coordinates are metres.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from PySide6.QtCore import Qt,QPointF,QSize,QTimer
from PySide6.QtGui import QVector3D,QMatrix4x4,QPainter,QPen,QColor,QPixmap,QIcon
from PySide6.QtWidgets import (QDialog,QWidget,QLabel,QVBoxLayout,QHBoxLayout,QFormLayout,
    QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QPushButton,QTableWidget,QTableWidgetItem,
    QMessageBox,QToolBar,QHeaderView)
from core.mesh import Mesh,Edge
from core.group import Group
from core.history import Command,InsertGroupCommand
from tools.base import Tool

KEY='ingetrazo_curve_tools'
VERSION='1.0.0'
TITLE='IngeTrazo Curve Tools V1.0'
KINDS=('Bézier','Cubic Bézier','B-spline','Catmull–Rom','Polyline')
HELP={
    'Bézier':'One Bézier curve. First/last points are endpoints; others are shaping controls. Closed mode adds the first point as the final control; the seam may be sharp.',
    'Cubic Bézier':'Open: 4, 7, 10… controls (anchor, handle, handle, anchor…). Closed: 3, 6, 9… controls; the first anchor is reused at the end. Handles determine seam smoothness.',
    'B-spline':'Cubic where possible (lower degree with 2–3 controls). Open curves reach the endpoints; closed curves use a periodic spline. Interior controls do not generally lie on the curve.',
    'Catmull–Rom':'Centripetal spline through every point. Closed curves wrap smoothly through the first point. Adjacent points must be distinct.',
    'Polyline':'Straight segments through the points. Closed mode joins the last point to the first.'}


def recipe(kind='Bézier',points=None,segments=24,closed=False):
    return dict(version=VERSION,kind=kind,points=copy.deepcopy(points or []),segments=segments,closed=closed)


def sample(data):
    kind=data.get('kind');closed=data.get('closed',False);steps=data.get('segments',24)
    if kind not in KINDS:raise ValueError('Choose a supported curve type.')
    if isinstance(steps,bool) or not isinstance(steps,int) or not 2<=steps<=256:raise ValueError('Use 2–256 segments.')
    p=np.asarray(data.get('points',[]),dtype=float)
    maximum=512 if kind=='Polyline' else 32 if kind=='Bézier' else 128
    if p.ndim!=2 or p.shape[1]!=3 or not 2<=len(p)<=maximum or not np.isfinite(p).all():
        raise ValueError(f'Enter 2–{maximum} finite XYZ points.')
    if closed and np.linalg.norm(p[0]-p[-1])<1e-8:p=p[:-1]
    if closed and len(p)<3:raise ValueError('A closed curve needs at least three distinct controls.')
    if np.max(np.linalg.norm(p-p[0],axis=1))<.0002:raise ValueError('The curve is too small for the model precision.')
    def bezier(controls,t):
        work=controls.copy()
        for length in range(len(work)-1,0,-1):work[:length]=(1-t)*work[:length]+t*work[1:length+1]
        return work[0].copy()
    if kind=='Polyline':out=list(p)+([p[0]] if closed else [])
    elif kind=='Bézier':
        controls=np.vstack((p,p[0])) if closed else p
        out=[bezier(controls,t) for t in np.linspace(0,1,steps+1)]
    elif kind=='Cubic Bézier':
        controls=np.vstack((p,p[0])) if closed else p
        if (len(controls)-1)%3 or len(controls)<4:raise ValueError('Cubic Bézier needs 4+3n open controls, or 3+3n closed controls.')
        out=[]
        for start in range(0,len(controls)-1,3):
            out.extend(bezier(controls[start:start+4],t) for t in np.linspace(0,1,steps+1)[:-1])
        out.append(controls[-1])
    elif kind=='B-spline':
        degree=min(3,len(p)-1)
        controls=np.vstack((p,p[:degree])) if closed else p
        count=len(controls)
        knots=np.arange(count+degree+1,dtype=float) if closed else np.r_[np.zeros(degree+1),np.arange(1,count-degree),np.full(degree+1,count-degree)]
        low,high=knots[degree],knots[count]
        out=[]
        for t in np.linspace(low,high,steps+1):
            if not closed and t==high:out.append(p[-1]);continue
            span=min(count-1,int(np.searchsorted(knots,t,side='right')-1))
            work=controls[span-degree:span+1].copy()
            for level in range(1,degree+1):
                for j in range(degree,level-1,-1):
                    index=span-degree+j
                    denominator=knots[index+degree-level+1]-knots[index]
                    alpha=(t-knots[index])/denominator if denominator else 0.
                    work[j]=(1-alpha)*work[j-1]+alpha*work[j]
            out.append(work[degree].copy())
        if closed:out[-1]=out[0].copy()
    else:
        pairs=zip(p,np.roll(p,-1,axis=0)) if closed else zip(p,p[1:])
        if any(np.linalg.norm(a-b)<.0001 for a,b in pairs):
            raise ValueError('Catmull–Rom points must be at least 0.1 mm apart.')
        count=len(p);out=[]
        for i in range(count if closed else count-1):
            a=p[(i-1)%count] if closed or i>0 else 2*p[0]-p[1]
            b=p[i];c=p[(i+1)%count]
            d=p[(i+2)%count] if closed or i+2<count else 2*p[-1]-p[-2]
            controls=[a,b,c,d];times=[0.]
            for x,y in zip(controls,controls[1:]):times.append(times[-1]+float(np.linalg.norm(y-x))**.5)
            def blend(x,y,left,right,t):return ((right-t)*x+(t-left)*y)/(right-left)
            for t in np.linspace(times[1],times[2],steps+1)[:-1]:
                first=[blend(controls[j],controls[j+1],times[j],times[j+1],t) for j in range(3)]
                left=blend(first[0],first[1],times[0],times[2],t)
                right=blend(first[1],first[2],times[1],times[3],t)
                out.append(blend(left,right,times[1],times[2],t))
        out.append(p[0] if closed else p[-1])
    if len(out)>8193:raise ValueError('Too many sampled segments. Reduce precision or the point count.')
    result=[]
    for point in out:
        if not result or tuple(np.rint(point*10000))!=tuple(np.rint(result[-1]*10000)):result.append(np.array(point))
    if len(result)<2:raise ValueError('Sampling collapses below IngeTrazo precision. Enlarge the curve or change its controls.')
    return [list(map(float,point)) for point in result]


def curve_mesh(data):
    path=sample(data);mesh=Mesh();cid=Mesh.next_curve_id()
    for a,b in zip(path,path[1:]):
        edge=mesh.add_edge(QVector3D(*a),QVector3D(*b));edge.curve=cid
    return mesh


def make_group(data):
    g=Group(curve_mesh(data),name='Curve — '+data['kind']);g.xform=QMatrix4x4();g.component=False
    g.ext={KEY:copy.deepcopy(data)}
    return g


def data_of(g):
    return (getattr(g,'ext',None) or {}).get(KEY)


def validate_source(g):
    if g.children or g.mesh.faces:raise ValueError('This group contains added geometry. Use Convert on a wire-only source instead.')
    expected=curve_mesh(data_of(g))
    def signature(mesh):
        return {tuple(sorted((e.v0.position.toTuple(),e.v1.position.toTuple()))) for e in mesh.edges}
    if signature(expected)!=signature(g.mesh):
        raise ValueError('This curve was changed outside Curve Tools. Use Convert to start a new editable curve from its edges.')


class EditCurve(Command):
    def __init__(self,g,data):
        self.g=g;self.data=copy.deepcopy(data);self.mesh=curve_mesh(data)
        self.before=(g.mesh,copy.deepcopy(g.ext),g.name)
    def do(self,scene):
        if self.g not in scene.groups:raise ValueError('The curve was removed. Reopen the editor.')
        self.g.mesh=self.mesh;self.g.ext=copy.deepcopy(self.g.ext or {});self.g.ext[KEY]=copy.deepcopy(self.data)
        self.g.name='Curve — '+self.data['kind'];scene.selection.clear();scene.selection.add(self.g);scene.version+=1
    def undo(self,scene):
        self.g.mesh,self.g.ext,self.g.name=self.before[0],copy.deepcopy(self.before[1]),self.before[2]
        scene.selection.clear();scene.selection.add(self.g);scene.version+=1


def execute(app,command):
    app.viewport.history.execute(command)
    if app.viewport.history.last_error:raise ValueError(app.viewport.history.last_error)
    app.viewport.notify_scene_changed();app.viewport.update()


def selected_group(scene):
    groups=[]
    for item in scene.selection:
        g=getattr(item,'owner',None) or item
        if g in scene.groups and g not in groups:groups.append(g)
    if len(groups)!=1:raise ValueError('Select one curve group.')
    return groups[0]


def ordered_path(edges):
    """Order a single chain or loop by connectivity, never selection order."""
    edges=set(edges)
    if not edges:raise ValueError('Select a connected edge chain or a wire-only group.')
    neighbors={}
    for e in edges:
        neighbors.setdefault(e.v0,[]).append((e.v1,e));neighbors.setdefault(e.v1,[]).append((e.v0,e))
    if any(len(n)>2 for n in neighbors.values()):raise ValueError('The selection branches. Select one unbranched chain or loop.')
    ends=[v for v,n in neighbors.items() if len(n)==1]
    if len(ends) not in (0,2):raise ValueError('Select one chain or loop.')
    start=min(ends or list(neighbors),key=lambda v:v.position.toTuple());v=start;path=[v.position.toTuple()];remaining=set(edges)
    while remaining:
        options=[(other,e) for other,e in neighbors[v] if e in remaining]
        if not options:raise ValueError('The selection contains disconnected paths.')
        other,e=min(options,key=lambda pair:pair[0].position.toTuple());remaining.remove(e);v=other
        path.append(v.position.toTuple())
    closed=v is start
    if closed:path.pop()
    if len(path)>512:raise ValueError('Conversion supports up to 512 path vertices. Simplify the source first.')
    return [list(p) for p in path],closed


def conversion_data(scene):
    group=None
    groups=[g for g in scene.groups if g in scene.selection]
    if groups:
        if len(groups)!=1:raise ValueError('Select one wire group for conversion.')
        group=groups[0]
        if group.children or group.mesh.faces:raise ValueError('Select a wire-only group or an edge chain.')
        edges=group.mesh.edges
    else:edges=[e for e in scene.selection if isinstance(e,Edge) and e in scene.mesh.edges]
    points,closed=ordered_path(edges)
    if group and group.xform is not None:points=[list(group.xform.map(QVector3D(*p)).toTuple()) for p in points]
    return recipe('Polyline',points,closed=closed)


class Preview(QWidget):
    def __init__(self):
        super().__init__();self.points=[];self.path=[];self.setMinimumSize(280,220)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor('#102338'))
        allpoints=self.points+self.path
        if not allpoints:return
        def project(p):return (p[0]+.4*p[1],.15*p[0]-.3*p[1]-p[2])
        projected=[project(p) for p in allpoints];lo=np.min(projected,axis=0);hi=np.max(projected,axis=0)
        scale=min((self.width()-45)/max(hi[0]-lo[0],.001),(self.height()-50)/max(hi[1]-lo[1],.001))
        def screen(p):
            x,y=(np.array(project(p))-(lo+hi)/2)*scale
            return QPointF(self.width()/2+x,self.height()/2+y)
        painter.setPen(QPen(QColor('#697f96'),1,Qt.DashLine))
        for a,b in zip(self.points,self.points[1:]):painter.drawLine(screen(a),screen(b))
        painter.setPen(QPen(QColor('#1cc8ff'),2))
        for a,b in zip(self.path,self.path[1:]):painter.drawLine(screen(a),screen(b))
        painter.setBrush(QColor('#ffc06d'));painter.setPen(QColor('#ffc06d'))
        for i,p in enumerate(self.points):
            q=screen(p);painter.drawEllipse(q,4,4);painter.drawText(q+QPointF(6,-6),str(i+1))


def interaction(editor):
    # Local class: discovery must not try to instantiate a Tool without an editor.
    class CurveInteraction(Tool):
        name='Curve control points';wireframe_color=(.08,.8,1.,1.);uses_snap=True
        def __init__(self):self.drag=None;self.original=None
        def on_activate(self,vp):vp.flash_status('Curve Tools: click points; Enter applies. Drag mode moves numbered controls.',7000)
        def on_deactivate(self,vp):
            if self.drag is not None:self.cancel_drag()
        def cancel_drag(self):
            if self.drag is not None:editor.points[self.drag]=self.original;self.drag=None;editor.sync_table();editor.refresh()
        def drag_plane(self,vp):
            if editor.finished_edit:return None
            if editor.plane.currentText()=='3D / view':
                if self.drag is not None:return (editor.world(editor.points[self.drag]),vp.camera.forward())
                return None
            axis={'XY':2,'XZ':1,'YZ':0}[editor.plane.currentText()]
            p=[0.,0.,0.];p[axis]=editor.elevation.value()/1000;n=[0.,0.,0.];n[axis]=1.
            return QVector3D(*p),QVector3D(*n)
        def local(self,ctx):
            p=QVector3D(ctx.world)
            if editor.plane.currentText()!='3D / view':
                axis={'XY':2,'XZ':1,'YZ':0}[editor.plane.currentText()]
                values=list(p.toTuple());values[axis]=editor.elevation.value()/1000;p=QVector3D(*values)
            inverse,ok=editor.transform.inverted()
            if not ok:raise ValueError('The curve transform is singular.')
            return list(inverse.map(p).toTuple())
        def on_click(self,ctx):
            if not editor.valid_context():return
            if editor.mode.currentText()=='Add points':
                p=self.local(ctx)
                if not editor.points or np.linalg.norm(np.array(p)-editor.points[-1])>.0001:
                    editor.points.append(p);editor.sync_table();editor.refresh()
            else:
                projected=editor.app.world_to_pixels([editor.world(p).toTuple() for p in editor.points]) if editor.points else None
                if projected is None:return
                xs,ys,visible=projected
                distances=[math.hypot(x-ctx.screen.x(),y-ctx.screen.y()) if front else float('inf') for x,y,front in zip(xs,ys,visible)]
                index=int(np.argmin(distances))
                if distances[index]<=14:self.drag=index;self.original=list(editor.points[index]);editor.table.selectRow(index)
        def on_hover(self,ctx):
            if self.drag is not None and editor.valid_context():
                editor.points[self.drag]=self.local(ctx);editor.sync_table();editor.refresh()
        def on_release(self,vp):self.drag=None;self.original=None
        def on_cancel(self,vp):
            if self.drag is not None:self.cancel_drag()
            else:editor.reject()
        def on_key(self,vp,key,modifiers):
            if key in (Qt.Key_Return,Qt.Key_Enter):editor.apply();return True
            if key in (Qt.Key_Backspace,Qt.Key_Delete):editor.remove_point();return True
            return False
        def rubber_band_lines(self):
            if editor.finished_edit:return []
            return [(editor.world(a),editor.world(b)) for a,b in zip(editor.path,editor.path[1:])]
    return CurveInteraction()


class Editor(QDialog):
    def __init__(self,app,kind='Bézier',target=None,initial=None):
        super().__init__(app.window)
        self.app=app;self.scene=app.scene;self.target=target;self.finished_edit=False;self.loading=True
        self.original=copy.deepcopy(data_of(target)) if target else None
        self.original_mesh=target.mesh if target else None
        self.original_state=target.mesh.capture_state() if target else None
        self.transform=QMatrix4x4(target.xform) if target and target.xform is not None else QMatrix4x4()
        data=copy.deepcopy(self.original or initial or recipe(kind));self.points=data['points'];self.path=[]
        self.setWindowTitle(TITLE);self.resize(850,650)
        outer=QVBoxLayout(self);outer.addWidget(QLabel('<h2>IngeTrazo Curve Tools</h2>Draw, shape and convert curves · coordinates in mm'))
        body=QHBoxLayout();outer.addLayout(body,1)
        left=QVBoxLayout();body.addLayout(left,1);right=QVBoxLayout();body.addLayout(right,1)
        form=QFormLayout();left.addLayout(form)
        self.kind=QComboBox();self.kind.addItems(KINDS);self.kind.setCurrentText(data['kind'])
        self.segments=QSpinBox();self.segments.setRange(2,256);self.segments.setValue(data['segments'])
        self.closed=QCheckBox('Closed loop');self.closed.setChecked(data['closed'])
        self.mode=QComboBox();self.mode.addItems(['Add points','Drag points']);self.mode.setCurrentIndex(1 if target else 0)
        self.plane=QComboBox();self.plane.addItems(['XY','XZ','YZ','3D / view']);self.plane.setCurrentText('3D / view' if target else 'XY')
        self.elevation=QDoubleSpinBox();self.elevation.setRange(-1e8,1e8);self.elevation.setDecimals(3)
        form.addRow('Curve type',self.kind);form.addRow('Segments / span*',self.segments);form.addRow('',self.closed)
        form.addRow('Mouse mode',self.mode);form.addRow('World drawing plane',self.plane);form.addRow('Plane offset (mm)',self.elevation)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['X mm','Y mm','Z mm'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectRows)
        left.addWidget(self.table,1)
        row=QHBoxLayout();left.addLayout(row)
        add=QPushButton('Add row');add.clicked.connect(self.add_point);row.addWidget(add)
        remove=QPushButton('Remove point');remove.clicked.connect(self.remove_point);row.addWidget(remove)
        resume=QPushButton('Pick / drag in model');resume.clicked.connect(self.activate);left.addWidget(resume)
        self.preview=Preview();right.addWidget(self.preview,1)
        self.help=QLabel();self.help.setWordWrap(True);right.addWidget(self.help)
        self.status=QLabel();self.status.setWordWrap(True);right.addWidget(self.status)
        right.addWidget(QLabel('* Total segments for Bézier / B-spline;\nper span for Cubic Bézier / Catmull–Rom.\nPoints are local to an edited curve group.'))
        buttons=QHBoxLayout();outer.addLayout(buttons)
        poly=QPushButton('Convert draft to polyline');poly.clicked.connect(self.to_polyline);buttons.addWidget(poly)
        buttons.addStretch();self.apply_button=QPushButton('Update curve' if target else 'Create curve');self.apply_button.clicked.connect(self.apply);buttons.addWidget(self.apply_button)
        close=QPushButton('Cancel');close.clicked.connect(self.reject);buttons.addWidget(close)
        outer.addWidget(QLabel('IngeTrazo Tutorials · Enter: apply · Esc: cancel · Changes are committed only on Apply'))
        self.table.cellChanged.connect(self.table_changed)
        self.kind.currentTextChanged.connect(self.refresh);self.segments.valueChanged.connect(self.refresh);self.closed.toggled.connect(self.refresh)
        self.plane.currentTextChanged.connect(lambda _:self.elevation.setEnabled(self.plane.currentText()!='3D / view'))
        self.finished.connect(self.cleanup)
        self.tool=interaction(self);self.sync_table();self.loading=False;self.refresh()
        self.elevation.setEnabled(self.plane.currentText()!='3D / view')
    def data(self):return recipe(self.kind.currentText(),self.points,self.segments.value(),self.closed.isChecked())
    def world(self,p):return self.transform.map(QVector3D(*p))
    def sync_table(self):
        self.table.blockSignals(True);self.table.setRowCount(len(self.points))
        for i,p in enumerate(self.points):
            for j,value in enumerate(p):self.table.setItem(i,j,QTableWidgetItem(f'{value*1000:.6f}'))
        self.table.blockSignals(False)
    def table_changed(self,row,column):
        try:
            value=float(self.table.item(row,column).text())/1000
            if not math.isfinite(value):raise ValueError()
            self.points[row][column]=value;self.refresh()
        except (ValueError,AttributeError):
            self.sync_table();self.refresh();self.status.setText('Invalid coordinate was reverted. Enter a finite number.')
    def add_point(self):
        self.points.append([self.points[-1][0]+1,self.points[-1][1],self.points[-1][2]] if self.points else [0.,0.,0.])
        self.sync_table();self.refresh()
    def remove_point(self):
        self.tool.cancel_drag()
        if not self.points:return
        index=self.table.currentRow();self.points.pop(index if 0<=index<len(self.points) else -1)
        self.sync_table();self.refresh()
    def refresh(self,*args):
        if self.loading or self.finished_edit:return
        self.help.setText(HELP[self.kind.currentText()]);self.preview.points=copy.deepcopy(self.points)
        try:
            self.path=sample(self.data());length=sum(np.linalg.norm(np.array(a)-b) for a,b in zip(self.path,self.path[1:]))
            self.status.setText(f'{len(self.points)} controls · {len(self.path)-1} segments\nApproximate length: {length*1000:,.2f} mm')
            self.apply_button.setEnabled(True)
        except ValueError as e:self.path=[];self.status.setText(str(e));self.apply_button.setEnabled(False)
        self.preview.path=self.path;self.preview.update();self.app.viewport.update()
    def valid_context(self):
        valid=self.app.scene is self.scene and self.scene.edit_group is None and not self.finished_edit
        if not valid and not self.finished_edit:self.status.setText('Document/editing context changed. Close and reopen Curve Tools.')
        return valid
    def activate(self):
        if self.valid_context():self.app.viewport.set_active_tool(self.tool);self.app.viewport.setFocus()
    def to_polyline(self):
        try:
            path=sample(self.data())
            if self.closed.isChecked():path=path[:-1]
            if len(path)>512:raise ValueError('Reduce sampling to at most 512 vertices before converting to polyline.')
            self.points=path;self.kind.setCurrentText('Polyline');self.sync_table();self.refresh()
        except ValueError as e:QMessageBox.warning(self,TITLE,str(e))
    def apply(self):
        try:
            if not self.valid_context():raise ValueError('Reopen the editor in the main model.')
            data=self.data();sample(data)
            if self.target:
                g=self.target
                if g not in self.scene.groups or data_of(g)!=self.original or g.mesh is not self.original_mesh:
                    raise ValueError('The source curve changed. Reopen its editor.')
                validate_source(g)
                state=g.mesh.capture_state()
                if state['edges']!=self.original_state['edges'] or any(state['vpos'].get(v)!=p for v,p in self.original_state['vpos'].items()):
                    raise ValueError('The source geometry changed. Reopen its editor.')
                current=QMatrix4x4(g.xform) if g.xform is not None else QMatrix4x4()
                if current!=self.transform:raise ValueError('The source placement changed. Reopen its editor.')
                execute(self.app,EditCurve(g,data))
            else:execute(self.app,InsertGroupCommand(make_group(data)))
            self.accept()
        except ValueError as e:QMessageBox.warning(self,TITLE,str(e))
    def cleanup(self,*args):
        if self.finished_edit:return
        self.finished_edit=True
        if self.app.viewport.active_tool is self.tool:
            self.tool.drag=None
            if hasattr(self.app.window,'_activate_tool'):self.app.window._activate_tool('select')
            else:self.app.viewport.set_active_tool(None)
        self.app.viewport.update()
    def overlay(self,vp,painter):
        if self.finished_edit or vp.active_tool is not self.tool or not self.valid_context() or not self.points:return
        xs,ys,front=self.app.world_to_pixels([self.world(p).toTuple() for p in self.points])
        painter.setPen(QPen(QColor('#dfac66'),1,Qt.DashLine))
        for i in range(len(self.points)-1):
            if front[i] and front[i+1]:painter.drawLine(QPointF(xs[i],ys[i]),QPointF(xs[i+1],ys[i+1]))
        painter.setPen(QPen(QColor('#102338'),1));painter.setBrush(QColor('#ffc06d'))
        for i,(x,y,visible) in enumerate(zip(xs,ys,front)):
            if visible:painter.drawEllipse(QPointF(x,y),5,5);painter.drawText(QPointF(x+8,y-8),str(i+1))


def icon(kind):
    pix=QPixmap(64,64);pix.fill(Qt.transparent);p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing)
    controls=[[5.,45.,0.],[18.,4.,0.],[43.,58.,0.],[58.,14.,0.]]
    path=sample(recipe(kind if kind in KINDS else 'Bézier',controls,24))
    p.setPen(QPen(QColor('#078bda'),4))
    for a,b in zip(path,path[1:]):p.drawLine(QPointF(a[0],a[1]),QPointF(b[0],b[1]))
    p.setBrush(QColor('#ffb657'));p.setPen(QColor('#153149'))
    for x,y,z in controls:p.drawEllipse(QPointF(x,y),4,4)
    if kind=='Edit':p.setPen(QPen(QColor('#d48217'),5));p.drawLine(40,53,59,34)
    if kind=='Convert':p.setPen(QPen(QColor('#d48217'),4));p.drawLine(35,53,58,53);p.drawLine(58,53,51,46)
    p.end();return QIcon(pix)


def setup(app):
    state={'editor':None}
    def launch(kind):
        try:
            if app.scene.edit_group is not None:raise ValueError('Close the current group-editing session first.')
            old=state['editor']
            if old and not old.finished_edit:old.raise_();old.activateWindow();return
            if kind=='Edit':
                target=selected_group(app.scene)
                if not data_of(target):raise ValueError('Select a Curve Tools curve, or use Convert on an ordinary wire.')
                validate_source(target)
                editor=Editor(app,target=target)
            elif kind=='Convert':editor=Editor(app,initial=conversion_data(app.scene))
            else:editor=Editor(app,kind)
            state['editor']=editor;editor.setAttribute(Qt.WA_DeleteOnClose)
            editor.finished.connect(lambda _:state.update(editor=None))
            editor.show();editor.activate()
        except ValueError as e:QMessageBox.warning(app.window,TITLE,str(e))
    toolbar=QToolBar(TITLE,app.window);toolbar.setObjectName('IngeTrazoCurveToolsToolbarV1')
    toolbar.setMovable(True);toolbar.setFloatable(True);toolbar.setAllowedAreas(Qt.AllToolBarAreas);toolbar.setIconSize(QSize(26,26))
    menu=app.add_menu(TITLE)
    for kind in (*KINDS,'Edit','Convert'):
        a=toolbar.addAction(icon(kind),kind);a.setToolTip('Curve Tools — '+kind)
        a.triggered.connect(lambda checked=False,k=kind:launch(k));menu.addAction(a)
    menu.addSeparator();menu.addAction(toolbar.toggleViewAction());app.window.addToolBar(toolbar)
    app.add_overlay(lambda vp,painter:state['editor'].overlay(vp,painter) if state['editor'] else None)
    def context(menu,selection):
        try:g=selected_group(app.scene)
        except ValueError:return
        if data_of(g):menu.addAction('Edit Curve Tools curve',lambda:QTimer.singleShot(0,lambda:launch('Edit')))
    app.add_context_menu(context)
    app.window._ingetrazo_curve_tools=(toolbar,state,launch)
