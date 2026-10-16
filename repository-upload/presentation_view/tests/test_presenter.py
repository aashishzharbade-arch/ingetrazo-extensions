import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile
from PySide6.QtCore import QSettings
_settings_dir=tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,_settings_dir.name)
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'work/ingetrazo'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication,QMainWindow,QPushButton
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent,QVector3D
from presentation_view import PresentationWindow,setup
from views.viewport import Viewport
app=QApplication.instance() or QApplication([])

def make():
    host=QMainWindow();host.viewport=Viewport(host)
    from PySide6.QtWidgets import QMenu
    return SimpleNamespace(window=host,viewport=host.viewport,scene=host.viewport.scene,add_menu=lambda name:QMenu(name,host))

def test_readonly_state_controls_and_gizmo():
    host=make();v=host.viewport
    v.scene.selection.add('sentinel');before=v.scene.version
    w=PresentationWindow(host)
    assert len(w.controls.findChildren(QPushButton))==3
    assert w.viewport.camera is not v.camera and w.viewport.scene is not v.scene
    assert not w.viewport.scene.selection and v.scene.selection=={'sentinel'}
    w.viewport.camera.target.setX(123)
    assert v.camera.target.x()!=123
    w.gizmo_button.click();assert not w.viewport.gizmo.isHidden()
    w.gizmo_button.click();assert w.viewport.gizmo.isHidden()
    w.viewport.keyPressEvent(QKeyEvent(QEvent.KeyPress,Qt.Key_Delete,Qt.NoModifier))
    assert v.scene.version==before and v.scene.selection=={'sentinel'}
    w.resize(1200,800);w.resizeEvent(QEvent(QEvent.Resize)) if False else None
    w.close();host.window.close()

def test_setup_idempotent():
    host=make();calls=[];host.add_menu_action=lambda *a,**kw:calls.append((a,kw))
    setup(host);setup(host);assert len(calls)==2
    assert calls[0][0][0]=='Presentation viewer'
    host.window.close()

def test_gizmo_render_and_escape():
    host=make();w=PresentationWindow(host)
    w.viewport.gizmo.grab();assert len(w.viewport.gizmo.hits)==6
    w.viewport.keyPressEvent(QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier))
    assert not w.isVisible()
    host.window.close()

def test_navigation_and_axis_click():
    from PySide6.QtCore import QPointF
    host=make();w=PresentationWindow(host);v=w.viewport
    old_yaw=host.viewport.camera.yaw
    class Mouse:
        def position(self):return QPointF(70,40)
        def buttons(self):return Qt.LeftButton
        def modifiers(self):return Qt.NoModifier
        def accept(self):pass
    v._present_pos=QPointF(10,10);v.mouseMoveEvent(Mouse())
    assert v.camera.yaw!=old_yaw and host.viewport.camera.yaw==old_yaw
    gizmo=v.gizmo;gizmo.grab();point,view=gizmo.hits[-1]
    event=Mouse();event.position=lambda:point
    gizmo.mousePressEvent(event)
    assert (v.camera.yaw,v.camera.pitch)==v.camera._STANDARD_VIEWS[view]
    w.close();host.window.close()


def test_toolbar_docking_restore_and_launch(monkeypatch):
    import presentation_view as plugin
    host=make();calls=[];host.add_menu_action=lambda *a,**kw:calls.append((a,kw))
    setup(host);state=host.window._presentation_view;bar=state['toolbar']
    assert bar.isMovable() and bar.isFloatable()
    assert bar.allowedAreas()==Qt.AllToolBarAreas
    assert not state['launch_action'].icon().isNull()
    host.window.addToolBar(Qt.LeftToolBarArea,bar)
    saved=host.window.saveState()
    host.window.addToolBar(Qt.BottomToolBarArea,bar)
    assert host.window.restoreState(saved)
    assert host.window.toolBarArea(bar)==Qt.LeftToolBarArea
    bar.hide();calls[1][0][1]();assert not bar.isHidden()
    launched=[]
    monkeypatch.setattr(plugin.PresentationWindow,'showFullScreen',lambda self:launched.append(self))
    state['launch_action'].trigger();assert len(launched)==1
    assert isinstance(state['window'],PresentationWindow)
    state['window'].close();host.window.close()


def test_combined_toggles_and_one_toolbar():
    from PySide6.QtWidgets import QToolBar
    from presentation_view import fps_meter
    from views import viewport as module
    host=make();host.add_menu_action=lambda *a,**kw:None
    setup(host);setup(host);state=host.window._presentation_view
    assert len(host.window.findChildren(QToolBar))==1
    assert len(state['toolbar'].actions())==3
    original=state['axes_action'].isChecked()
    state['axes_action'].setChecked(False)
    data,spans=module._axes_vertices(1)
    assert all(count==0 for start,count in spans.values()) and len(data)>0
    state['axes_action'].setChecked(True)
    data,spans=module._axes_vertices(1)
    assert any(count>0 for start,count in spans.values())
    state['axes_action'].setChecked(original)
    state['fps_action'].setChecked(True)
    meter=fps_meter._meter_for(host.viewport)
    assert meter and meter._timer.isActive() and not meter.stress
    state['fps_action'].setChecked(False)
    assert fps_meter._meter_for(host.viewport) is None and not meter._timer.isActive()
    host.window.close()


def test_fps_follows_presentation_launch(monkeypatch):
    import presentation_view as plugin
    from presentation_view import fps_meter
    host=make();host.add_menu_action=lambda *a,**kw:None
    setup(host);state=host.window._presentation_view
    monkeypatch.setattr(plugin.PresentationWindow,'showFullScreen',lambda self:None)
    state['fps_action'].setChecked(True)
    state['launch_action'].trigger()
    viewer=state['window'];meter=fps_meter._meter_for(viewer.viewport)
    assert meter is not None and meter.overlay.x()==12
    state['fps_action'].setChecked(False)
    assert fps_meter._meter_for(viewer.viewport) is None
    viewer.close();host.window.close()
