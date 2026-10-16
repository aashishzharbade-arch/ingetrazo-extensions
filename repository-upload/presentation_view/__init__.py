# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal, read-only presentation window for IngeTrazo API 2."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt, QPointF, QSize, QSettings
from PySide6.QtGui import QVector3D, QPainter, QColor, QPen, QIcon, QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QToolBar
from views.viewport import Viewport


class PresentationViewport(Viewport):
    def _draw_overlay(self):
        pass

    def mousePressEvent(self,event):
        self._present_pos=event.position()
        event.accept()

    def mouseMoveEvent(self,event):
        last=getattr(self,'_present_pos',event.position())
        delta=event.position()-last;self._present_pos=event.position()
        if event.buttons() & (Qt.RightButton|Qt.MiddleButton) or (event.buttons() & Qt.LeftButton and event.modifiers() & Qt.ShiftModifier):
            self.camera.pan(delta.x(),delta.y(),max(1,self.height()))
        elif event.buttons() & Qt.LeftButton:
            self.camera.orbit(delta.x(),delta.y(),max(1,self.height()))
        self.update()
        if hasattr(self,'gizmo'):self.gizmo.update()
        event.accept()

    def mouseReleaseEvent(self,event):event.accept()
    def mouseDoubleClickEvent(self,event):event.accept()
    def contextMenuEvent(self,event):event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:self.window().close()
        event.accept()
    def keyReleaseEvent(self,event):event.accept()
    def wheelEvent(self,event):
        self.camera.zoom(event.angleDelta().y()/120.);self.update();event.accept()


class OrientationGizmo(QWidget):
    """Six clickable axis ends, positioned using the live camera orientation."""
    def __init__(self,viewport):
        super().__init__(viewport);self.viewport=viewport;self.setFixedSize(140,140)
        self.setToolTip('Click an axis end to align the camera. Drag the model to orbit.')
        self.hits=[]

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen);p.setBrush(QColor(255,255,255,220));p.drawRoundedRect(self.rect(),16,16)
        matrix=self.viewport.camera.view_matrix();center=QPointF(70,70);self.hits=[]
        ends=[]
        for label,vec,color,view in [('X',(1,0,0),'#d95058','right'),('-X',(-1,0,0),'#d95058','left'),('Y',(0,1,0),'#3c9864','back'),('-Y',(0,-1,0),'#3c9864','front'),('Z',(0,0,1),'#488cda','top'),('-Z',(0,0,-1),'#488cda','bottom')]:
            v=matrix.mapVector(QVector3D(*vec));ends.append((v.z(),label,QPointF(70+v.x()*45,70-v.y()*45),color,view))
        for _,label,point,color,view in sorted(ends):
            p.setPen(QPen(QColor(color),2));p.drawLine(center,point)
            p.setBrush(QColor(color));p.drawEllipse(point,13,13);p.setPen(Qt.white)
            p.drawText(int(point.x()-13),int(point.y()-13),26,26,Qt.AlignCenter,label)
            self.hits.append((point,view))

    def mousePressEvent(self,event):
        for point,view in reversed(self.hits):
            if (point-event.position()).manhattanLength()<20:
                self.viewport.camera.set_view(view);self.viewport.update();self.update();break
        event.accept()


class PresentationWindow(QWidget):
    def __init__(self,app):
        super().__init__(app.window,Qt.Window|Qt.FramelessWindowHint)
        self.setWindowTitle('Presentation view');self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModal)
        self.app=app
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.viewport=PresentationViewport(self);layout.addWidget(self.viewport)
        source=app.viewport
        # Separate presentation state; geometry is shared read-only. All input
        # handlers above bypass host editing commands and keyboard shortcuts.
        self.viewport.scene=copy.copy(source.scene)
        self.viewport.scene.selection=set()
        self.viewport.camera=copy.copy(source.camera)
        self.viewport.camera.target=QVector3D(source.camera.target)
        self.viewport.style_override=copy.copy(source.scene.display_style)
        from core import units
        units.bind_scene(source.scene)
        self.viewport.gizmo=OrientationGizmo(self.viewport);self.viewport.gizmo.hide()
        self.controls=QWidget(self.viewport)
        row=QHBoxLayout(self.controls);row.setContentsMargins(0,0,0,0);row.setSpacing(7)
        self.gizmo_button=QPushButton('3D Gizmo');self.gizmo_button.setCheckable(True)
        self.gizmo_button.toggled.connect(self.viewport.gizmo.setVisible)
        self.minimize_button=QPushButton('Minimize');self.minimize_button.clicked.connect(self.showMinimized)
        self.close_button=QPushButton('Close');self.close_button.clicked.connect(self.close)
        for button in (self.gizmo_button,self.minimize_button,self.close_button):
            button.setMinimumHeight(36);row.addWidget(button)
        self.controls.setStyleSheet('QPushButton {background:rgba(255,255,255,235);color:#26313d;border:1px solid #cbd0d6;border-radius:7px;padding:0 14px;font:13px "Segoe UI";} QPushButton:hover {background:#e9eef4;} QPushButton:checked {background:#d7e9fb;}')
        self.controls.adjustSize()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.controls.move(max(0,self.width()-self.controls.width()-18),18)
        self.viewport.gizmo.move(max(0,self.width()-158),66)
        self.controls.raise_();self.viewport.gizmo.raise_()

    def closeEvent(self,event):
        self.app.window.raise_();self.app.window.activateWindow()
        super().closeEvent(event)


def setup(app):
    if hasattr(app.window,'_presentation_view'):return
    from . import axis_visibility, fps_meter
    from views import viewport as viewport_module
    settings=QSettings('aashishzharbade-arch','Presentation view')
    axis_state=axis_visibility.install_axis_hook(viewport_module)
    state={'window':None,'fps':False};app.window._presentation_view=state
    def launch():
        if state['window'] is not None:
            state['window'].showFullScreen();state['window'].raise_();return
        if app.scene.edit_group is not None:
            QMessageBox.information(app.window,'Presentation view','Close group editing before starting the presentation.');return
        window=PresentationWindow(app);state['window']=window
        window.destroyed.connect(lambda:state.update(window=None))
        window.showFullScreen();window.viewport.setFocus()
        if state['fps']:fps_meter._meter_for(window.viewport,create=True)
    app.add_menu_action('Presentation viewer',launch,'Ctrl+Alt+P',tip='Show the model full screen with three presentation controls.')


    toolbar=QToolBar('Presentation view',app.window)
    toolbar.setObjectName('PresentationViewToolbar')
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    toolbar.setIconSize(QSize(28,28))
    toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    action=toolbar.addAction(QIcon(str(Path(__file__).with_name('presenter.svg'))),'Presentation viewer')
    action.setToolTip('Presentation viewer - show the model full screen')
    action.triggered.connect(launch)
    app.window.addToolBar(Qt.TopToolBarArea,toolbar)
    state['toolbar']=toolbar
    state['launch_action']=action
    def show_toolbar():
        toolbar.show();toolbar.raise_()
    app.add_menu_action('Show Presentation view toolbar',show_toolbar,
                        tip='Restore the draggable Presentation view toolbar.')

    axes=QAction(axis_visibility.axis_icon(),'Axis visible',app.window)
    axes.setCheckable(True);axes.setObjectName('PresentationViewAxes')
    def set_axes(visible):
        axis_state['hidden']=not visible
        settings.setValue('axes_visible',visible)
        axes.setToolTip('Axes visible - click to hide' if visible else 'Axes hidden - click to show')
        app.viewport.update()
    axes.toggled.connect(set_axes)
    visible=settings.value('axes_visible',not axis_state['hidden'],type=bool)
    axes.setChecked(visible);set_axes(visible)
    toolbar.addAction(axes);state['axes_action']=axes
    fps=QAction(QIcon(str(Path(__file__).with_name('fps.svg'))),'FPS meter',app.window)
    fps.setCheckable(True);fps.setObjectName('PresentationViewFPS')
    fps.setToolTip('Show FPS, frame interval, process CPU and history')
    def set_fps(enabled):
        state['fps']=enabled
        viewports=[app.viewport]
        if state['window'] is not None:viewports.append(state['window'].viewport)
        for viewport in viewports:
            meter=fps_meter._meter_for(viewport,create=enabled)
            if meter is not None and not enabled:
                meter.close();setattr(viewport,fps_meter._ATTR,None)
    fps.toggled.connect(set_fps);toolbar.addAction(fps);state['fps_action']=fps
    menu=app.add_menu('Presentation view')
    for item in (action,axes,fps):menu.addAction(item)
    menu.addSeparator();menu.addAction(toolbar.toggleViewAction())
