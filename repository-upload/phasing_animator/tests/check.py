# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with INGETRAZO_SOURCE pointing at IngeTrazo 0.5.7 source."""
import os
import sys
import copy
import math
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path[:0]=[os.environ['INGETRAZO_SOURCE'],str(ROOT)]
from PySide6.QtCore import Qt,QPoint,QSettings,QEvent,QPointF
from PySide6.QtGui import QVector3D as V,QMatrix4x4,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.extensions import discover_plugins
from core.scene import Scene
from core.layers import Layer
from core.group import Group
from formats.igz import save_scene,load_into
from phasing_animator import engine as e
from phasing_animator.ui import Studio,Timeline,Controller
from demo import scene,box
app=QApplication([])
QSettings.setDefaultFormat(QSettings.IniFormat)
for scope in (QSettings.UserScope,QSettings.SystemScope):QSettings.setPath(QSettings.IniFormat,scope,str(ROOT/'tests/settings'))
plugins,errors=discover_plugins([ROOT]);assert not errors and [p.stem for p in plugins]==['phasing_animator']
import core.extensions
core.extensions.discover_plugins=lambda *a,**k:([],[])
from views.main_window import MainWindow
from views.extension_api import ExtensionApp


def rejects(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Expected validation error')


# Limits and schema, including a large Pro project.
d=e.empty_data();e.add_phase(d,'A',0);e.add_phase(d,'B',3)
e.add_phase(d,'C',6)
for i in range(100):e.add_phase(d,f'Layer {i}',0)
assert len(e.validated(d)['phases'])==103
rejects(lambda:e.add_phase(d,'A',0))
bad=copy.deepcopy(d);bad['phases'][0]['end']=float('nan');rejects(lambda:e.validated(bad))
bad=copy.deepcopy(d);bad['edition']='lite';assert 'edition' not in e.validated(bad)

# Phase boundaries, rise, fade, hide and disabling.
p=e.new_phase('A',2,12);p.update(end=6,effect='fade')
assert e.phase_value(p,1)==(False,0.,0.)
assert e.phase_value(p,4)==(True,.5,0.)
p.update(effect='rise',rise=4);assert e.phase_value(p,4)==(True,1.,-2.)
p['after']='hide';assert not e.phase_value(p,6)[0]
p['enabled']=False;assert e.phase_value(p,0)==(True,1.,0.)

# Nested tagged faces, instance isolation, material fade and repeatability.
s=scene();source=([tuple(v.position.toTuple()) for v in s.groups[0].mesh.vertices],copy.deepcopy([f.attrs for f in s.groups[0].mesh.faces]));snap=e.Snapshot(s)
snap.apply(s.plugin_data[e.KEY],1.5)
assert abs(snap.scene.groups[0].xform.map(V()).z()+1)<1e-5
assert s.groups[0].xform is None
for original,cloned in zip(s.groups,snap.scene.groups):assert original.mesh is not cloned.mesh
snap.apply(s.plugin_data[e.KEY],12);assert abs(snap.scene.groups[0].xform.map(V()).z())<1e-6
snap.apply(s.plugin_data[e.KEY],0);assert ([tuple(v.position.toTuple()) for v in s.groups[0].mesh.vertices],[f.attrs for f in s.groups[0].mesh.faces])==source
tagged=Group(box(0,0,0,1,1,1,(1,0,0)),'Nested tags')
for f in tagged.mesh.faces:f.attrs['layer']='Roof'
holder=Group();holder.xform=QMatrix4x4();holder.xform.rotate(90,V(1,0,0));holder.children=[tagged]
s.groups=[holder];d=e.empty_data();p=e.add_phase(d,'Roof',0);p.update(effect='rise',rise=2,end=4)
snap=e.Snapshot(s);snap.apply(d,2)
root=snap.scene.groups[0];child=root.children[0];part=child.children[0]
assert abs((root.xform*child.xform*part.xform).map(V()).z()+1)<1e-5
shared=box(0,0,0,1,1,1,(1,0,0));g1=Group(shared);g1.layer='Roof';g2=Group(shared);g2.layer='Foundation';s.groups=[g1,g2]
for f in shared.faces:f.attrs={}
g1.material={'color':(.1,.6,.2),'opacity':.8}
p.update(effect='fade');snap=e.Snapshot(s);snap.apply(d,2)
assert abs(snap.scene.groups[0].mesh.faces[0].attrs['opacity']-.4)<1e-6
assert 'opacity' not in snap.scene.groups[1].mesh.faces[0].attrs
assert shared.faces[0].attrs=={}
snap.apply(d,4);assert abs(snap.scene.groups[0].mesh.faces[0].attrs['opacity']-.8)<1e-6

# Loose geometry including independent tags.
s=Scene();s.layers.append(Layer('Roof'));s.mesh=box(0,0,0,1,1,1,(1,0,0))
for f in s.mesh.faces:f.attrs['layer']='Roof'
snap=e.Snapshot(s);p['effect']='rise';snap.apply(d,2)
assert len(snap.scene.groups)==1 and abs(snap.scene.groups[0].xform.map(V()).z()+1)<1e-6

# Actual host integration, Undo/Redo, record keys and IGZ serialization.
w=MainWindow();host=ExtensionApp(w,e.KEY);host.scene.groups=scene().groups;host.scene.layers=scene().layers
controller=Controller(host);studio=Studio(host);studio.reload()
assert all(not a.icon().isNull() for a in controller.toolbar.actions())
g=host.scene.groups[0];host.scene.selection={g};studio.add_objects()
assert g.xform is not None and not g.component
assert host.viewport.history.undo() and g.xform is None
assert host.viewport.history.redo() and g.xform is not None
g.xform.translate(4,0,0);studio.key_time.setValue(4);studio.record_objects()
studio.key_time.setValue(0);studio.record_camera();host.viewport.camera.target=V(4,2,1);studio.key_time.setValue(4);studio.record_camera()
studio.seek(2);assert abs(studio.snapshot.scene.groups[0].xform.map(V()).x()-2)<1e-5
assert abs(g.xform.map(V()).x()-4)<1e-5
assert (studio.vp.camera.target-V(2,1,.5)).length()<1e-5
data=studio.read();p=e.add_phase(data,'Foundation',0);p.update(end=3);e.add_phase(data,'Roof',5);studio.commit(data)
assert studio.add_button.isEnabled()
assert host.viewport.history.undo();studio.reload();assert studio.add_button.isEnabled()
assert host.viewport.history.redo();studio.reload()
data=studio.read();data['edition']='pro';e.add_phase(data,'Structure',3);studio.commit(data)
assert not hasattr(studio,'edition') and len(studio.read()['phases'])==3
assert studio.render.isEnabled()
assert not hasattr(studio,'channel_button')
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'phasing.igz';save_scene(host.scene,path);loaded=Scene();load_into(loaded,path)
    assert loaded.plugin_data[e.KEY]==studio.read()
studio.toggle();assert studio.timer.isActive();studio.seek(1);assert not studio.timer.isActive()
studio.toggle();studio.reject();assert not studio.timer.isActive()

# Timeline real mouse events: ruler seek, bar click, drag, trim and hover.
tl=Timeline();tl.resize(900,180);data=e.empty_data();phase=e.add_phase(data,'A',1);phase['end']=4;tl.refresh(data,phase['id'])
seeks=[];moves=[];tl.seek.connect(seeks.append);tl.timingChanged.connect(lambda *args:moves.append(args));tl.show();app.processEvents()
QTest.mouseClick(tl,Qt.LeftButton,pos=QPoint(round(tl.xpos(6)),15));assert abs(seeks[-1]-6)<.03
QTest.mouseClick(tl,Qt.LeftButton,pos=QPoint(round(tl.xpos(2)),48));assert abs(seeks[-1]-2)<.03
def drag(x1,x2,y=48):
    QTest.mousePress(tl,Qt.LeftButton,pos=QPoint(round(x1),y))
    event=QMouseEvent(QEvent.MouseMove,QPointF(x2,y),QPointF(x2,y),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(tl,event);QTest.mouseRelease(tl,Qt.LeftButton,pos=QPoint(round(x2),y))
drag(tl.xpos(2),tl.xpos(4));assert abs(moves[-1][1]-3)<.03 and abs(moves[-1][2]-6)<.03
drag(tl.xpos(6)-2,tl.xpos(8));assert abs(moves[-1][2]-8)<.1
tl.hover=True;QTest.mouseMove(tl,QPoint(round(tl.xpos(10)),100));assert abs(seeks[-1]-10)<.03
assert e.frame_count(1,24)==24 and e.frame_time(23,1,24)==1
tl.close();w.hide();studio.close()
print('PASS: loader, limits, phases, nested tags, materials, isolation, keyframes, Undo/Redo, IGZ, timeline mouse interactions, frame sampling')

