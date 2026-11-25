"""Game Play for the IngeTrazo model viewport."""
import math
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QUrl,Qt,QEvent,QPointF,QRectF,QTimer,QLineF,QPoint,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPolygonF,QVector3D,QIcon,QPixmap,QDesktopServices
from PySide6.QtWidgets import QWidget,QPushButton,QMessageBox
from .world import World
from .character import Character

ROOT=Path(__file__).parent
MOVE={Qt.Key_W,Qt.Key_A,Qt.Key_S,Qt.Key_D,Qt.Key_Shift}
def bounded(v,lo,hi):return max(lo,min(hi,v))

class Session(QWidget):
    stateChanged=Signal()

    def __init__(self,view,world,character):
        super().__init__(view)
        self.view=view
        self.world=world
        self.scene_version=view.scene.version
        self.step_sound=None
        try:
            from PySide6.QtMultimedia import QSoundEffect
            self.step_sound=QSoundEffect(self)
            self.step_sound.setSource(QUrl.fromLocalFile(str(ROOT/'step.wav')))
            self.step_sound.setVolume(.16)
        except (ImportError,RuntimeError):
            pass
        self.muted=False
        self.seated=False
        self.sit_phase=0.
        self.mode=None
        self.character=character
        self.player=None
        self.keys=set()
        self.drag=None
        self.pan=np.zeros(3)
        self.velocity=np.zeros(3)
        self.distance=3.8
        self.map_width=210
        self.phase=0
        self.slice_at=None
        self.walls=[]
        self.inside=False
        self.active=True
        self.cam=view.camera
        self.saved={k:getattr(self.cam,k) for k in ('target','distance','yaw','pitch','perspective','two_point','fov_deg')}
        self.previous=view._draw_preview_faces
        self.previous_local=view.__dict__.get('_draw_preview_faces')
        self.mesh=None
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.exit_button=QPushButton('Exit Game Play',self)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.setStyleSheet('QPushButton {background:#202a32;color:white;border:1px solid #708088;border-radius:5px;padding:7px 13px;} QPushButton:hover {background:#364550;}')
        self.exit_button.adjustSize()
        self.exit_button.clicked.connect(self.finish)
        self.timer=QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.resize(view.size())
        view.installEventFilter(self)
        view._draw_preview_faces=self.draw_actor
        view.sceneVersionChanged.connect(self.scene_changed)
        self.show()
        self.raise_()
        self.setFocus()
        self.last=time.perf_counter()

    def scene_changed(self,*args):
        if self.view.scene.version!=self.scene_version:self.finish()

    def finish(self):
        if not self.active:return
        self.active=False
        self.stateChanged.emit()
        self.timer.stop()
        v=self.view
        v.removeEventFilter(self)
        v.sceneVersionChanged.disconnect(self.scene_changed)
        if self.previous_local is None:v.__dict__.pop('_draw_preview_faces',None)
        else:v._draw_preview_faces=self.previous_local
        for k,val in self.saved.items():setattr(self.cam,k,val)
        self.hide();v.update();self.deleteLater()
        if v.isVisible():v.setFocus()

    def eventFilter(self,obj,e):
        if e.type()==QEvent.Resize:self.resize(self.view.size())
        if e.type()==QEvent.Hide:self.finish()
        return False

    def resizeEvent(self,e):
        self.exit_button.move(max(0,self.width()-self.exit_button.width()-12),12)

    def event(self,e):
        if e.type()==QEvent.ShortcutOverride and e.key() in MOVE|{Qt.Key_M,Qt.Key_Escape,Qt.Key_Plus,Qt.Key_Equal,Qt.Key_Minus}:
            e.accept();return True
        return super().event(e)

    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Escape:self.finish()
        elif e.key()==Qt.Key_M and not e.isAutoRepeat():self.muted=not self.muted
        elif e.key() in MOVE:self.keys.add(e.key())
        elif e.key() in (Qt.Key_Plus,Qt.Key_Equal,Qt.Key_Minus):
            self.map_width=bounded(self.map_width+(20 if e.key()!=Qt.Key_Minus else -20),140,380)
            self.update()
        e.accept()

    def keyReleaseEvent(self,e):
        if not e.isAutoRepeat():self.keys.discard(e.key())
        e.accept()

    def focusOutEvent(self,e):
        self.keys.clear();self.drag=None;self.velocity[:]=0
        super().focusOutEvent(e)

    def toggle_seat(self):
        if self.player is None:return
        self.seated=not self.seated
        self.velocity[:]=0
        self.keys.clear()
        self.stateChanged.emit()

    def place(self,p):
        self.player=np.array(p,dtype=float)
        self.heading=self.cam.yaw+math.pi
        self.cam.perspective=True;self.cam.two_point=False
        self.cam.pitch=.24;self.cam.fov_deg=50
        self.last=time.perf_counter()
        self.tick();self.timer.start(33);self.stateChanged.emit()

    def mousePressEvent(self,e):
        self.setFocus()
        p=e.position()
        if self.player is None:
            if e.button()!=Qt.LeftButton:return
            origin,direction=self.view._pixel_to_ray(p.x(),p.y())
            if origin is None:return
            a=np.array(origin.toTuple());d=np.array(direction.toTuple())
            t=self.world.ray(a,d,1.e6)
            surface=self.world.ray(a,d,1.e6,True)
            if t is not None and (surface is None or abs(surface-t)>.05):return
            if t is None and d[2]<-1.e-5:t=-a[2]/d[2]
            if t is not None and t>0:self.place(a+d*t)
            return
        self.drag=(p,e.button())

    def mouseReleaseEvent(self,e):self.drag=None
    def mouseMoveEvent(self,e):
        if not self.drag or self.player is None:return
        last,button=self.drag;delta=e.position()-last
        self.drag=(e.position(),button)
        if button==Qt.MiddleButton or e.modifiers()&Qt.ShiftModifier:
            right=np.array([-math.sin(self.cam.yaw),math.cos(self.cam.yaw),0])
            self.pan+=(-delta.x()*right+np.array([0,0,delta.y()]))*self.distance*.0018
        else:
            self.cam.yaw-=delta.x()*.008
            self.cam.pitch=bounded(self.cam.pitch+delta.y()*.007,-.28,1.3)

    def wheelEvent(self,e):
        self.distance=bounded(self.distance*math.exp(-e.angleDelta().y()/750),.8,14)
        e.accept()

    def tick(self):
        now=time.perf_counter();dt=min(.06,now-self.last);self.last=now
        yaw=self.cam.yaw
        forward=np.array([-math.cos(yaw),-math.sin(yaw),0])
        right=np.array([forward[1],-forward[0],0])
        intent=forward*((Qt.Key_W in self.keys)-(Qt.Key_S in self.keys))+right*((Qt.Key_D in self.keys)-(Qt.Key_A in self.keys))
        speed=3.8 if Qt.Key_Shift in self.keys else 1.5
        target=intent/max(1,np.linalg.norm(intent))*speed
        if self.seated or self.sit_phase>0:target[:]=0
        self.velocity+=(target-self.velocity)*(1-math.exp(-dt*12))
        before=self.player.copy()
        if np.linalg.norm(self.velocity)>.02:
            step=self.velocity*dt
            self.player=self.world.advance(before,step)
            if np.array_equal(before,self.player):
                for axis in (0,1):
                    part=np.zeros(3);part[axis]=step[axis]
                    self.player=self.world.advance(self.player,part)
        delta=self.player-before
        rate=np.linalg.norm(delta[:2])/max(dt,1e-6)
        if rate>.035:
            desired=math.atan2(delta[1],delta[0])
            self.heading+=math.remainder(desired-self.heading,2*math.pi)*(1-math.exp(-dt*16))
        mode='Breathing Idle' if rate<.035 else ('Running' if rate>2.45 else 'Walking')
        if self.seated or self.sit_phase>0:mode='Sitting'
        if mode!=self.mode:
            self.phase=0.
            self.mode=mode
        previous_phase=self.phase
        _,duration,travel=self.character.motion[mode]
        if mode=='Sitting':
            self.sit_phase=bounded(self.sit_phase+(1 if self.seated else -1)*dt/duration,0,1)
            self.phase=self.sit_phase
        elif mode in ('Walking','Running'):
            stride=np.linalg.norm(travel)*self.character.scale
            self.phase=(self.phase+rate*dt/stride)%1
            if int(previous_phase*2)!=int(self.phase*2) and self.step_sound and not self.muted:
                self.step_sound.play()
        else:self.phase=(self.phase+dt/duration)%1
        coords=self.character.frame(mode,self.phase)
        indices=self.character.idx
        uv=self.character.uv
        angle=self.heading+math.pi/2
        c,s=math.cos(angle),math.sin(angle)
        xyz=coords@np.array([[c,s,0],[-s,c,0],[0,0,1]],dtype='f4')+self.player
        if self.mesh is None:
            self.mesh=np.empty((len(indices),5),dtype='f4')
            self.mesh[:,3:]=uv
        self.mesh[:,:3]=xyz[indices]
        aim=self.player+[0,0,1.12]+self.pan
        self.cam.target=QVector3D(*aim)
        direction=np.array([math.cos(yaw)*math.cos(self.cam.pitch),math.sin(yaw)*math.cos(self.cam.pitch),math.sin(self.cam.pitch)])
        obstruction=self.world.ray(aim,direction,self.distance)
        self.cam.distance=max(.22,obstruction-.14) if obstruction else self.distance
        if self.slice_at is None or np.linalg.norm(self.player-self.slice_at)>.18:
            self.walls=self.world.section(self.player,20)
            self.inside=self.world.inside(self.player)
            self.slice_at=self.player.copy()
        self.view.update();self.update()

    def draw_actor(self):
        if self.mesh is None:return self.previous()
        v=self.view
        v._program.setUniformValue(v._loc_use_tex,1)
        v._program.setUniformValue1f(v._loc_shade,1.)
        v._preview_tex_vao.bind()
        try:
            raw=self.mesh.tobytes();v._preview_tex_vbo.bind()
            v._preview_tex_vbo.allocate(raw,len(raw));v._preview_tex_vbo.release()
            batches=self.character.batches
            for path,start,count in batches:
                tex=v._get_texture(path)
                if tex is not None:
                    tex.bind(0)
                    v._gl.glDrawArrays(4,start,count)
                    tex.release(0)
        finally:
            v._preview_tex_vao.release()
            v._program.setUniformValue(v._loc_use_tex,0)

    def paintEvent(self,e):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.player is None:
            text='Click a floor or the ground to place your character'
            w=p.fontMetrics().horizontalAdvance(text)+28
            rect=QRectF((self.width()-w)/2,16,w,32)
            p.setPen(Qt.NoPen);p.setBrush(QColor(22,31,38,225));p.drawRoundedRect(rect,6,6)
            p.setPen(Qt.white);p.drawText(rect,Qt.AlignCenter,text);p.end();return
        w=min(self.map_width,max(100,self.width()-30));h=w*.62
        box=QRectF(14,self.height()-h-15,w,h)
        p.setPen(QPen(QColor('#88969a'),1));p.setBrush(QColor(18,27,32,225));p.drawRoundedRect(box,7,7)
        p.setPen(QColor('#f0f4f4'))
        p.drawText(box.adjusted(10,4,-9,0),Qt.AlignTop|Qt.AlignLeft,'INSIDE' if self.inside else 'OUTSIDE')
        p.drawText(box.adjusted(10,4,-9,0),Qt.AlignTop|Qt.AlignRight,'N \u2191')
        region=box.adjusted(5,24,-5,-5);p.setClipRect(region)
        center=region.center();px=w/24
        p.setPen(QPen(QColor('#cad2cf'),1.8))
        points=(self.walls-self.player[:2])*np.array([px,-px])+[center.x(),center.y()]
        p.drawLines([QLineF(*a,*b) for a,b in points])
        p.translate(center);p.rotate(-math.degrees(self.heading))
        p.setBrush(QColor('#38e3d5'));p.setPen(QPen(QColor('#062f37'),1.4))
        p.drawPolygon(QPolygonF([QPointF(9,0),QPointF(-6,-5),QPointF(-3,0),QPointF(-6,5)]))
        p.end()

def setup(app):
    state={}
    menu=app.add_menu('Game Play')
    toolbar=app.window._new_toolbar('Game Play','game_play_toolbar')
    from views.icons import tool_icon

    def button(label, icon, tip):
        action=toolbar.addAction(icon,label)
        action.setToolTip(tip)
        action.setStatusTip(tip)
        return action

    def glyph(lines, circle=None):
        pix=QPixmap(48,48)
        pix.fill(Qt.transparent)
        painter=QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#4087ef'),3,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        for points in lines:
            painter.drawPolyline(QPolygonF([QPointF(x,y) for x,y in points]))
        if circle:
            painter.drawEllipse(QPointF(*circle),4,4)
        painter.end()
        return QIcon(pix)

    play=button('Play',tool_icon('walk'),'Enter Game Play')
    stop=button('Exit',glyph([[(17,7),(7,7),(7,40),(17,40)],[(18,24),(40,24)],[(31,15),(40,24),(31,33)]]),'Exit Game Play')
    seat=button('Sit',glyph([[(18,17),(18,27),(31,27),(35,39)],[(8,19),(8,33),(27,33)],[(11,34),(11,40)]],(18,9)),'Sit down')
    stand=button('Stand',glyph([[(23,17),(23,28),(18,40)],[(23,28),(29,40)],[(13,25),(22,16),(32,24)]],(23,8)),'Stand up')
    controls=button('Controls',tool_icon('first_person'),'Show movement and camera controls')
    developer=button('More from developer',glyph([[(23,9),(8,9),(8,40),(39,40),(39,26)],[(21,27),(39,9)],[(26,9),(39,9),(39,22)]]),'More from developer — IngeTrazo Tutorials')
    developer.triggered.connect(lambda: QDesktopServices.openUrl(QUrl('https://ingetrazotutorials.gumroad.com/')))

    def fit_buttons(*args):
        horizontal=toolbar.orientation()==Qt.Horizontal
        buttons=[toolbar.widgetForAction(a) for a in toolbar.actions()]
        length=sum((w.sizeHint().width() if horizontal else w.sizeHint().height()) for w in buttons if w)
        length+=24+max(0,toolbar.layout().spacing())*len(buttons)
        toolbar.setMinimumSize(length if horizontal else 0,0 if horizontal else length)

    toolbar.orientationChanged.connect(fit_buttons)
    toolbar.iconSizeChanged.connect(fit_buttons)
    fit_buttons()

    def refresh():
        session=state.get('session')
        active=session is not None and session.active
        placed=active and session.player is not None
        play.setEnabled(not active)
        stop.setEnabled(active)
        seat.setEnabled(placed and not session.seated)
        stand.setEnabled(placed and session.seated)

    def start():
        session=state.get('session')
        if session is not None and session.active:
            session.view.window().activateWindow()
            session.setFocus()
            return
        view=app.viewport
        if view.camera.locked:
            QMessageBox.information(app.window,'Game Play','Unlock this camera view before walking.')
            return
        try:
            if 'character' not in state:
                character=Character(ROOT/'Player.glb')
                character.prepare_motion()
                state['character']=character
            session=Session(view,World(view.scene),state['character'])
            state['session']=session
            session.stateChanged.connect(refresh)
            refresh()
            app.window.activateWindow()
            session.setFocus()
        except Exception as exc:
            QMessageBox.warning(app.window,'Game Play',str(exc))

    def sit_or_stand():
        session=state.get('session')
        if session is not None and session.active:
            session.toggle_seat()
            app.window.activateWindow()
            session.setFocus()

    play.triggered.connect(start)
    stop.triggered.connect(lambda: state['session'].finish())
    seat.triggered.connect(sit_or_stand)
    stand.triggered.connect(sit_or_stand)
    menu.addAction('Enter Game Play',start)
    toggle=toolbar.toggleViewAction()
    toggle.setText('Show Game Play Toolbar')
    menu.addAction(toggle)
    controls.triggered.connect(lambda: QMessageBox.information(app.window,'Game Play controls',
        'Click a floor to start.\n\nWASD    Walk\nShift + WASD    Run\nDrag    Orbit\nShift + drag or middle drag    Pan\nScroll    Zoom\n+ / −    Resize minimap\nM    Toggle footsteps\nEsc    Exit'))
    menu.addAction(controls)
    refresh()
