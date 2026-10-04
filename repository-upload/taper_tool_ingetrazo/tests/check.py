import os,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent.parent
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path[:0]=[os.environ['INGETRAZO_SOURCE'],str(ROOT)]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QVector3D as V,QMatrix4x4,QFontDatabase,QFont
from views.main_window import MainWindow
from views.extension_api import ExtensionApp
import ingetrazo_taper as t
from core.extensions import discover_plugins
plugins,errors=discover_plugins([ROOT])
assert not errors and len(plugins)==1 and not plugins[0].tools,(plugins,errors)
APP=QApplication([])
font=Path('C:/Windows/Fonts/arial.ttf')
if font.exists():
 QFontDatabase.addApplicationFont(str(font));APP.setFont(QFont('Arial',10))
QSettings.setDefaultFormat(QSettings.IniFormat)
for scope in (QSettings.UserScope,QSettings.SystemScope):QSettings.setPath(QSettings.IniFormat,scope,str(ROOT/'tests/settings'))
def close(a,b):assert (a-b).length()<1e-5,(a,b)
m=t.Mapping(V(),V(0,0,2),V(1,0,0),1,.5)
close(m(V(2,2,2)),V(1,1,2))
close(t.Mapping(V(),V(0,0,2),V(1,0,0),1,.5,True)(V(2,2,2)),V(1,2,2))
close(t.Mapping(V(),V(0,0,2),V(1,0,0),1,.5,False,False)(V(2,2,4)),V(1,1,4))
close(t.Mapping(V(1,1,1),V(3,1,1),V(0,1,0),1,.5)(V(3,3,3)),V(3,2,2))
def box():
 mesh=t.Mesh()
 ps=[V(x,y,z) for z in (0,2) for y in (-1,1) for x in (-1,1)]
 for ids in ((0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)):mesh.add_face([ps[i] for i in ids])
 return mesh
mesh=box();result=t.deform_mesh(mesh,m)
assert len(mesh.faces)==6 and len(result.faces)>6
assert all(len(e.faces)==2 for e in result.edges),'Non-manifold result'
rigid=t.deform_mesh(mesh,m,True)
for a,b in zip(mesh.edges,rigid.edges):assert abs((a.b-a.a).length()-(b.b-b.a).length())<1e-5
window=MainWindow();app=ExtensionApp(window,t.KEY);t.setup(app)
g=t.Group(mesh,name='Test');g.xform=QMatrix4x4();g.xform.translate(3,0,0)
app.scene.groups.append(g);app.scene.selection={g};app.scene.version+=1
bar,state,launch=window._ingetrazo_taper_tool
launch();d=state['editor'];original=[V(v.position) for v in mesh.vertices]
for p in (V(),V(0,0,2),V(1,0,2)):d.tool.on_click(SimpleNamespace(world=p))
d.tool.on_hover(SimpleNamespace(world=V(.5,0,2)))
assert d.lines and not d.finished and len(app.scene.groups)>=1
assert all(a==b.position for a,b in zip(original,mesh.vertices))
d.reject();assert app.viewport.active_tool is None and g in app.scene.groups
launch();d=state['editor']
for p in (V(),V(0,0,2),V(1,0,2),V(.5,0,2)):d.tool.on_click(SimpleNamespace(world=p))
assert d.finished,d.status.text()
assert g not in app.scene.groups
assert app.viewport.history.undo() and g in app.scene.groups
assert app.viewport.history.redo() and g not in app.scene.groups
assert app.viewport.history.undo()
app.scene.selection={g};launch();d=state['editor'];d.copy.setChecked(True)
for p in (V(),V(0,0,2),V(1,0,2),V(.5,0,2)):d.tool.on_click(SimpleNamespace(world=p))
assert d.finished and g in app.scene.groups
assert all(a==b.position for a,b in zip(original,mesh.vertices))
assert app.viewport.history.undo()
app.scene.selection={g};launch();d=state['editor'];app.scene.version+=1
assert not d.valid() and not d.apply_button.isEnabled();d.reject()
app.scene.selection={g};launch();d=state['editor']
for p in (V(),V(0,0,2),V(1,0,2)):d.tool.on_click(SimpleNamespace(world=p))
assert not d.tool.on_value(app.viewport,(1,2,3))
assert d.tool.on_value(app.viewport,.75) and d.finished
assert app.viewport.history.undo()
loose=app.scene.mesh.add_face([V(10,0,0),V(11,0,0),V(11,0,1),V(10,0,1)])
app.scene.selection={loose};app.scene.version+=1
s=t.Selection(app.scene);r=s.build(m,False,4)
app.viewport.history.execute(t.TaperCommand(s,r,False))
assert loose not in app.scene.mesh.faces and not app.viewport.history.last_error
assert app.viewport.history.undo() and loose in app.scene.mesh.faces
app.scene.selection={g};launch();d=state['editor']
d.show();APP.processEvents();d.grab().save(str(ROOT/'editor-preview.png'))
bar.grab().save(str(ROOT/'toolbar.png'));d.close();assert d.finished
print('PASS: mapping, Flat, finite, tilted axis, closed topology, Rigid, real host four clicks, cancel, transformed group, Copy, Undo/Redo, stale document guard')
window.hide()
