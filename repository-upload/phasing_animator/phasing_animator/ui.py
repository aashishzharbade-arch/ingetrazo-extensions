# SPDX-License-Identifier: GPL-3.0-or-later
"""Modern native Qt editor; no browser, server or proprietary runtime needed."""
import copy
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
import uuid
from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, Signal, QProcess, QSettings
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QCheckBox, QLineEdit, QListWidget,
    QSplitter, QScrollArea, QTabWidget, QToolBar, QFileDialog, QProgressBar, QMessageBox,
    QAbstractItemView, QSizePolicy)
from views.viewport import Viewport
from . import engine as e


def icon(kind):
    pix=QPixmap(64,64);pix.fill(Qt.transparent);pix.setDevicePixelRatio(2)
    p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing);p.setPen(QPen(QColor('#36baf2'),2));p.setBrush(Qt.NoBrush)
    if kind=='play':
        p.setBrush(QColor('#36baf2'));p.drawPolygon(QPolygonF([QPointF(10,6),QPointF(25,16),QPointF(10,26)]))
    elif kind=='pause':p.drawLine(12,7,12,25);p.drawLine(21,7,21,25)
    elif kind=='record':p.setBrush(QColor('#ff9d52'));p.drawEllipse(8,8,16,16)
    elif kind=='plus':p.drawLine(7,16,25,16);p.drawLine(16,7,16,25)
    elif kind=='export':
        p.drawLine(16,5,16,22);p.drawLine(10,16,16,22);p.drawLine(16,22,22,16);p.drawLine(6,25,26,25)
    elif kind=='rewind':
        p.drawLine(7,7,7,25);p.drawPolygon(QPolygonF([QPointF(23,7),QPointF(11,16),QPointF(23,25)]))
    elif kind=='delete':
        p.drawRect(9,10,14,17);p.drawLine(6,7,26,7);p.drawLine(12,4,20,4)
    elif kind=='camera':p.drawRoundedRect(5,10,23,16,3,3);p.drawEllipse(12,13,10,10);p.drawLine(10,6,21,6)
    else:
        p.drawRoundedRect(4,5,25,22,3,3);p.drawLine(6,22,27,22)
        for x,y,w in ((7,9,10),(12,14,13),(18,19,8)):p.drawLine(x,y,x+w,y)
    p.end();return QIcon(pix)


class Timeline(QWidget):
    seek=Signal(float)
    chosen=Signal(str)
    timingChanged=Signal(str,float,float)
    dragStarted=Signal()
    LABEL=174;ROW=38;TOP=32
    def __init__(self,parent=None):
        super().__init__(parent);self.setMouseTracking(True)
        self.data=e.empty_data();self.t=0.;self.selected='';self.hover=False;self.drag=None
        self.setMinimumWidth(440);self.setMinimumHeight(130)
    def refresh(self,data,selected):
        self.data=copy.deepcopy(data);self.selected=selected
        self.setMinimumHeight(max(130,self.TOP+self.ROW*len(data['phases'])+14));self.update()
    def xpos(self,t):return self.LABEL+t/self.data['duration']*max(1,self.width()-self.LABEL-16)
    def time_at(self,x):return max(0.,min(self.data['duration'],(x-self.LABEL)/max(1,self.width()-self.LABEL-16)*self.data['duration']))
    def bar_rect(self,i,p):return QRectF(self.xpos(p['start']),self.TOP+i*self.ROW+8,max(4,self.xpos(p['end'])-self.xpos(p['start'])),22)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#141c27'));p.setPen(QColor('#9caec3'))
        p.drawText(QRectF(12,0,self.LABEL-18,self.TOP),Qt.AlignVCenter,'PHASE TIMELINE')
        for i in range(5):
            x=self.xpos(self.data['duration']*i/4)
            p.setPen(QColor('#273449'));p.drawLine(QPointF(x,self.TOP),QPointF(x,self.height()))
            p.setPen(QColor('#9caec3'));p.drawText(QRectF(x-18,0,40,30),Qt.AlignCenter,f'{self.data["duration"]*i/4:g}s')
        for i,tr in enumerate(self.data['phases']):
            y=self.TOP+i*self.ROW
            p.setPen(QColor('#eff5fc'));name=p.fontMetrics().elidedText(tr['name'],Qt.ElideRight,self.LABEL-22)
            p.drawText(QRectF(12,y,self.LABEL-20,self.ROW),Qt.AlignVCenter,name)
            p.setPen(Qt.NoPen);p.setBrush(QColor('#253246'));p.drawRoundedRect(QRectF(self.LABEL,y+8,self.width()-self.LABEL-16,22),4,4)
            p.setBrush(QColor('#3db9ee' if tr.get('enabled',True) else '#526172'));p.drawRoundedRect(self.bar_rect(i,tr),4,4)
            if tr['id']==self.selected:
                p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor('#ccecff'),1));p.drawRoundedRect(self.bar_rect(i,tr).adjusted(-2,-2,2,2),5,5)
            p.setPen(QPen(QColor('#152131'),2));r=self.bar_rect(i,tr)
            for x in (r.left()+4,r.right()-4):p.drawLine(QPointF(x,y+14),QPointF(x,y+24))
        x=self.xpos(self.t);p.setPen(QPen(QColor('#ffbc71'),2));p.drawLine(QPointF(x,25),QPointF(x,self.height()))
        p.setBrush(QColor('#ffbc71'));p.drawPolygon(QPolygonF([QPointF(x-5,22),QPointF(x+5,22),QPointF(x,29)]))
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        pos=event.position();row=int((pos.y()-self.TOP)//self.ROW)
        tr=self.data['phases'][row] if pos.y()>=self.TOP and 0<=row<len(self.data['phases']) else None
        if pos.x()<self.LABEL:
            if tr:self.chosen.emit(tr['id'])
            return
        self.dragStarted.emit()
        if tr and self.bar_rect(row,tr).contains(pos):
            r=self.bar_rect(row,tr);mode='start' if abs(pos.x()-r.left())<=6 else 'end' if abs(pos.x()-r.right())<=6 else 'move'
            self.drag=dict(id=tr['id'],x=pos.x(),start=tr['start'],end=tr['end'],mode=mode,moved=False)
            self.chosen.emit(tr['id'])
        else:self.drag={'mode':'seek'};self.seek.emit(self.time_at(pos.x()))
    def mouseMoveEvent(self,event):
        x=event.position().x()
        if self.drag:
            d=self.drag
            if d['mode']=='seek':self.seek.emit(self.time_at(x));return
            if abs(x-d['x'])>3:d['moved']=True
            if not d['moved']:return
            tr=next((p for p in self.data['phases'] if p['id']==d['id']),None)
            if tr is None:return
            delta=(x-d['x'])/max(1,self.width()-self.LABEL-16)*self.data['duration']
            if d['mode']=='move':
                delta=max(-d['start'],min(self.data['duration']-d['end'],delta));tr['start']=d['start']+delta;tr['end']=d['end']+delta
            elif d['mode']=='start':tr['start']=max(0.,min(d['end']-.01,d['start']+delta))
            else:tr['end']=min(self.data['duration'],max(d['start']+.01,d['end']+delta))
            self.update()
        elif self.hover and x>=self.LABEL:self.seek.emit(self.time_at(x))
    def mouseReleaseEvent(self,event):
        if not self.drag:return
        d=self.drag;self.drag=None
        if d['mode']!='seek':
            if d['moved']:
                tr=next(p for p in self.data['phases'] if p['id']==d['id']);self.timingChanged.emit(tr['id'],round(tr['start'],3),round(tr['end'],3))
            else:self.seek.emit(self.time_at(event.position().x()))


class PreviewViewport(Viewport):
    def paintGL(self):
        # Host styled-frame rendering omits axes/guides. Preserve the current
        # scene style so material, face mode and background still match it.
        previous = self.style_override
        self.style_override = self._effective_style()
        try:
            super().paintGL()
        finally:
            self.style_override = previous

    def contextMenuEvent(self,event):event.accept()
    def keyPressEvent(self,event):event.accept()
    def mouseDoubleClickEvent(self,event):event.accept()
    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton:super().mousePressEvent(event)
        else:event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MiddleButton:super().mouseReleaseEvent(event)
        else:event.accept()


STYLE='''
QDialog#PhasingStudio {background:#101720;color:#edf3fa;}
#PhasingStudio QWidget {color:#edf3fa;font-family:"Segoe UI";font-size:12px;}
#PhasingStudio QLabel {background:transparent;}
#PhasingStudio QLabel[role="title"] {font-size:20px;font-weight:600;}
#PhasingStudio QLabel[role="muted"] {color:#9caec3;}
#PhasingStudio QPushButton {background:#243248;border:1px solid #35455b;border-radius:6px;padding:7px 12px;}
#PhasingStudio QPushButton:hover {background:#31445e;}
#PhasingStudio QPushButton:disabled {color:#6f8096;background:#1b2534;}
#PhasingStudio QPushButton[primary="true"] {background:#087eaf;border-color:#159cca;}
#PhasingStudio QLineEdit,#PhasingStudio QDoubleSpinBox,#PhasingStudio QComboBox {background:#182331;border:1px solid #35455b;border-radius:5px;padding:5px;min-height:22px;}
#PhasingStudio QComboBox QAbstractItemView {background:#202e40;selection-background-color:#17698b;}
#PhasingStudio QListWidget {background:#141e2b;border:0;border-radius:6px;padding:4px;}
#PhasingStudio QListWidget::item {padding:10px;border-radius:4px;}
#PhasingStudio QListWidget::item:selected {background:#16435c;color:#e2f5ff;}
#PhasingStudio QTabWidget::pane {border:1px solid #2c3a4e;border-radius:6px;background:#17212e;}
#PhasingStudio QTabBar::tab {background:#182331;padding:10px 18px;border-bottom:2px solid transparent;}
#PhasingStudio QTabBar::tab:selected {background:#243248;border-bottom:2px solid #39b9ef;}
#PhasingStudio QScrollArea {border:0;background:#141c27;}
#PhasingStudio QCheckBox {spacing:7px;}
#PhasingStudio QSplitter::handle {background:#2a394e;}
#PhasingStudio QProgressBar {border:0;background:#243248;border-radius:4px;text-align:center;}
#PhasingStudio QProgressBar::chunk {background:#087eaf;}
'''


class Studio(QDialog):
    def __init__(self,app):
        super().__init__(app.window);self.app=app;self.data=e.empty_data();self.selected='';self.t=0.;self.loading=False
        self.snapshot=None;self.busy=False;self.export_folder=None;self.process=None;self.export_settings=None
        self.setObjectName('PhasingStudio');self.setWindowTitle(e.TITLE);self.setWindowFlag(Qt.Tool,True)
        self.setStyleSheet(STYLE);self.resize(1240,820)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick)
        self.export_timer=QTimer(self);self.export_timer.timeout.connect(self.export_frame)
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.timeout.connect(lambda:self.safe(self.reload))
        box=QVBoxLayout(self);box.setContentsMargins(18,16,18,12);box.setSpacing(12)
        header=QHBoxLayout();box.addLayout(header)
        title=QLabel(e.TITLE);title.setProperty('role','title');header.addWidget(title);header.addStretch()
        header.addWidget(QLabel('OPEN SOURCE'))
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        animation=QWidget();layout=QVBoxLayout(animation);self.tabs.addTab(animation,'Animation')
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();lb=QVBoxLayout(left);lb.addWidget(QLabel('MODEL LAYERS'))
        self.layers=QListWidget();lb.addWidget(self.layers)
        self.add_button=self.button('Add phase track','plus',self.add_phase);lb.addWidget(self.add_button)
        self.step_button=self.button('Capture construction step','record',self.capture_step);lb.addWidget(self.step_button)
        self.limit=QLabel();self.limit.setWordWrap(True);lb.addWidget(self.limit);split.addWidget(left)
        center=QWidget();cb=QVBoxLayout(center);cb.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();row.addWidget(QLabel('ISOLATED PREVIEW'));row.addStretch();row.addWidget(self.button('Refresh model','timeline',self.reload));cb.addLayout(row)
        self.vp=PreviewViewport(center);self.vp.active_tool=None;self.vp.setMinimumSize(320,240);cb.addWidget(self.vp,1)
        hint=QLabel('Middle mouse: orbit · wheel: zoom · source model stays unchanged');hint.setProperty('role','muted');hint.setWordWrap(True);cb.addWidget(hint);split.addWidget(center)
        props=QWidget();pb=QVBoxLayout(props);pb.addWidget(QLabel('PHASE PROPERTIES'));form=QFormLayout();pb.addLayout(form)
        self.name=QLineEdit();self.binding=QComboBox();self.start=self.spin(0,3600);self.end=self.spin(.001,3600)
        self.effect=QComboBox()
        for label,value in [('Show instantly','show'),('Fade in','fade'),('Rise into place','rise')]:self.effect.addItem(label,value)
        self.after=QComboBox();self.after.addItem('Keep visible','keep');self.after.addItem('Hide layer','hide')
        self.rise=self.spin(-10000000,10000000,' mm');self.rise.setValue(3000);self.enabled=QCheckBox('Enable phase')
        for label,w in [('Track name',self.name),('Model layer',self.binding),('Start · seconds',self.start),('End · seconds',self.end),('Entrance',self.effect),('After phase',self.after),('Rise distance',self.rise)]:form.addRow(label,w)
        pb.addWidget(self.enabled);pb.addWidget(self.button('Apply phase settings','timeline',self.apply_phase));pb.addWidget(self.button('Remove track','delete',self.remove_phase));pb.addStretch();split.addWidget(props);split.setSizes([210,680,280])
        transport=QHBoxLayout();layout.addLayout(transport)
        transport.addWidget(self.button('Rewind','rewind',lambda:self.seek(0)))
        self.play=self.button('Play','play',self.toggle);transport.addWidget(self.play)
        self.time_field=self.spin(0,12,' s');self.time_field.setDecimals(3);transport.addWidget(self.time_field)
        self.loop=QCheckBox('Loop');transport.addWidget(self.loop)
        self.hover=QCheckBox('Hover scrub');transport.addWidget(self.hover);transport.addStretch()
        transport.addWidget(QLabel('Duration'));self.duration=self.spin(.1,3600,' s');transport.addWidget(self.duration)
        self.fps=QComboBox();self.fps.addItems([str(f) for f in e.FPS]);transport.addWidget(self.fps);transport.addWidget(self.button('Save timing','timeline',self.save_timing))
        self.timeline=Timeline();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.timeline);scroll.setMinimumHeight(155);scroll.setMaximumHeight(280);layout.addWidget(scroll);self.timeline_scroll=scroll
        label=QLabel('Click anywhere to seek · drag empty space to scrub · drag a bar to move · drag its ends to trim');label.setProperty('role','muted');layout.addWidget(label)
        self.build_keys();self.build_export()
        self.export_strip=QWidget();strip=QHBoxLayout(self.export_strip);strip.setContentsMargins(0,0,0,0)
        strip.addWidget(self.progress,1);strip.addWidget(self.export_status,2);strip.addWidget(self.cancel)
        box.addWidget(self.export_strip);self.export_strip.hide()
        self.status=QLabel('Assign objects to model layers, then add a phase track.');self.status.setWordWrap(True);box.addWidget(self.status)
        footer=QLabel('Developed by aashishzharbade-arch · GPL-3.0-or-later · Changes saved in the IGZ document')
        footer.setProperty('role','muted');box.addWidget(footer)
        self.layers.currentRowChanged.connect(self.layer_selected)
        self.timeline.seek.connect(self.seek);self.timeline.chosen.connect(self.choose);self.timeline.timingChanged.connect(lambda uid,a,b:self.safe(lambda:self.move_phase(uid,a,b)))
        self.timeline.dragStarted.connect(self.pause);self.hover.toggled.connect(lambda value:setattr(self.timeline,'hover',value))
        self.time_field.valueChanged.connect(self.seek)
        self.effect.currentIndexChanged.connect(lambda:self.rise.setEnabled(self.effect.currentData()=='rise'))
        self.app.on_document_changed(self.document_changed)
    @staticmethod
    def spin(lo,hi,suffix=''):
        w=QDoubleSpinBox();w.setRange(lo,hi);w.setDecimals(3);w.setSingleStep(.1);w.setSuffix(suffix);return w
    def button(self,text,kind,fn):
        b=QPushButton(icon(kind),text);b.setAutoDefault(False);b.clicked.connect(lambda _=False:self.safe(fn));return b
    def safe(self,fn):
        try:return fn()
        except Exception as exc:
            self.pause();self.status.setText(str(exc))
            if hasattr(self,'timeline'):self.timeline.refresh(self.data,self.selected)
    def document_changed(self):
        if self.isVisible() and not self.busy:self.refresh_timer.start(120)
    def read(self):return e.validated(self.app.scene.plugin_data.get(e.KEY))
    def commit(self,data,prepare=()):
        if self.busy:raise ValueError('Wait for export to finish or cancel it first.')
        self.pause();self.refresh_timer.stop()
        vp=self.app.viewport;vp.history.execute(e.EditAnimation(data,prepare))
        if vp.history.last_error:raise ValueError(vp.history.last_error)
        vp.notify_scene_changed();vp.update();self.refresh_timer.stop();self.reload()
        self.status.setText('Saved in the document · Ctrl+Z in the model undoes this change.')
    def reload(self):
        if self.busy:return
        self.pause();self.data=self.read();self.loading=True
        try:
            source_camera=e.camera_data(self.app.viewport.camera)
            keep_camera=self.snapshot is not None and source_camera==getattr(self,'source_camera',None)
            preview_camera=e.camera_data(self.vp.camera) if keep_camera else source_camera
            self.source_camera=source_camera
            old_layer=self.layers.currentItem().text() if self.layers.currentItem() else None
            self.duration.setValue(self.data['duration']);self.time_field.setMaximum(self.data['duration']);self.fps.setCurrentText(str(self.data['fps']))
            self.layers.clear();self.binding.clear()
            for ly in self.app.scene.layers:
                self.layers.addItem(ly.name);self.binding.addItem(ly.name)
                if ly.name==old_layer:self.layers.setCurrentRow(self.layers.count()-1)
            for p in self.data['phases']:
                if self.binding.findText(p['layer'])<0:self.binding.addItem(p['layer'])
            if not any(p['id']==self.selected for p in self.data['phases']):self.selected=self.data['phases'][0]['id'] if self.data['phases'] else ''
            self.inspector();self.timeline.refresh(self.data,self.selected)
            self.timeline_scroll.setMinimumHeight(min(260,max(150,Timeline.TOP+Timeline.ROW*len(self.data['phases'])+16)))
            n=len(self.data['phases']);self.limit.setText(f'{n} phase tracks · Unlimited')
            self.add_button.setEnabled(True)
            self.step_button.setEnabled(bool(self.app.scene.selection))
            self.snapshot=e.Snapshot(self.app.scene);self.vp.scene=self.snapshot.scene
            self.vp.reset_document_caches();e.set_camera(self.vp.camera,preview_camera)
            self.refresh_keys();self.load_export();self.seek(min(self.t,self.data['duration']))
        finally:self.loading=False
    def choose(self,uid):
        self.selected=uid;self.timeline.selected=uid;self.timeline.update();self.inspector()
    def inspector(self):
        p=next((p for p in self.data['phases'] if p['id']==self.selected),None)
        for w in (self.name,self.binding,self.start,self.end,self.effect,self.after,self.rise,self.enabled):w.setEnabled(p is not None)
        if not p:return
        self.name.setText(p['name']);self.binding.setCurrentText(p['layer']);self.start.setValue(p['start']);self.end.setValue(p['end'])
        self.effect.setCurrentIndex(self.effect.findData(p['effect']));self.after.setCurrentIndex(self.after.findData(p['after']));self.rise.setValue(p['rise']*1000);self.rise.setEnabled(p['effect']=='rise');self.enabled.setChecked(p.get('enabled',True))
    def layer_selected(self,row):
        if self.loading or row<0:return
        name=self.layers.item(row).text();p=next((p for p in self.data['phases'] if p['layer']==name),None)
        if p:self.choose(p['id'])
    def add_phase(self):
        item=self.layers.currentItem()
        if item is None:raise ValueError('Choose a model layer on the left first.')
        d=self.read();p=e.add_phase(d,item.text(),self.t);self.selected=p['id'];self.commit(d)
    def capture_step(self):
        """Create/select a phase and record selected transforms at the playhead.

        This is the construction-sequence workflow: select installed objects,
        choose their layer, move the playhead, then capture the current step.
        Visibility timing and object motion remain separate data so either can
        be edited without destroying the other.
        """
        groups=self.groups_selected()
        if self.t>=self.data['duration']:raise ValueError('Move the playhead before the clip end to capture a construction step.')
        item=self.layers.currentItem()
        if item is None:raise ValueError('Choose the construction layer first.')
        d=self.read();layer=item.text();p=next((p for p in d['phases'] if p['layer']==layer),None)
        if p is None:p=e.add_phase(d,layer,self.t);self.selected=p['id']
        if self.t<p['start']:p['start']=self.t
        if self.t>=p['end']:p['end']=min(d['duration'],self.t+.1)
        for g in groups:
            if g.uid not in d['objects']:
                d['objects'][g.uid]=dict(name=g.name,keys=[dict(t=0.,value=e.pose(g.xform))])
            e.put_key(d['objects'][g.uid]['keys'],self.t,e.pose(g.xform))
        self.commit(d,groups)
        self.status.setText(f'Construction step captured at {self.t:g} s for {len(groups)} object(s).')
    def apply_phase(self):
        d=self.read();p=next((p for p in d['phases'] if p['id']==self.selected),None)
        if p is None:raise ValueError('Select a phase track first.')
        p.update(name=self.name.text().strip() or self.binding.currentText(),layer=self.binding.currentText(),start=self.start.value(),end=self.end.value(),effect=self.effect.currentData(),after=self.after.currentData(),rise=self.rise.value()/1000,enabled=self.enabled.isChecked())
        self.commit(d)
    def remove_phase(self):
        d=self.read();d['phases']=[p for p in d['phases'] if p['id']!=self.selected];self.commit(d)
    def move_phase(self,uid,start,end):
        d=self.read()
        for p in d['phases']:
            if p['id']==uid:p.update(start=start,end=end)
        self.commit(d)
    def save_timing(self):
        d=self.read();d['duration']=self.duration.value();d['fps']=int(self.fps.currentText());self.commit(d)
    def seek(self,t,playback=False):
        if self.busy and not playback:return
        if not playback:self.pause()
        self.t=max(0.,min(self.data['duration'],t));self.time_field.blockSignals(True);self.time_field.setValue(self.t);self.time_field.blockSignals(False)
        self.timeline.t=self.t;self.timeline.update()
        if self.snapshot:
            self.snapshot.apply(self.data,self.t)
            if self.data['camera']:e.set_camera(self.vp.camera,e.camera_mix(*e.segment(self.data['camera'],self.t)))
            self.vp.update()
    def pause(self):
        self.timer.stop();self.play.setText('Play');self.play.setIcon(icon('play'))
        if hasattr(self,'timeline'):self.timeline.hover=self.hover.isChecked()
    def toggle(self):
        if self.busy:return
        if self.timer.isActive():self.pause();return
        if self.t>=self.data['duration']:self.seek(0)
        self.timeline.hover=False
        self.play_start=time.monotonic()-self.t;self.timer.start(max(1,round(1000/self.data['fps'])));self.play.setText('Pause');self.play.setIcon(icon('pause'))
    def tick(self):
        t=time.monotonic()-self.play_start
        if t>=self.data['duration']:
            if self.loop.isChecked():t%=self.data['duration'];self.play_start=time.monotonic()-t
            else:t=self.data['duration'];self.pause()
        self.safe(lambda:self.seek(t,True))
    def build_keys(self):
        panel=QWidget();box=QVBoxLayout(panel);self.tabs.addTab(panel,'Object & camera keys')
        label=QLabel('Add selected top-level groups before moving them. Move / rotate / scale in the model, then record at a new time.');label.setWordWrap(True);box.addWidget(label)
        row=QHBoxLayout();box.addLayout(row);row.addWidget(QLabel('Key time'));self.key_time=self.spin(0,3600,' s');row.addWidget(self.key_time);row.addStretch()
        for title,kind,fn in [('Add selected groups','plus',self.add_objects),('Record pose','record',self.record_objects),('Record camera','camera',self.record_camera)]:row.addWidget(self.button(title,kind,fn))
        self.key_list=QListWidget();self.key_list.setSelectionMode(QAbstractItemView.ExtendedSelection);box.addWidget(self.key_list)
        row=QHBoxLayout();box.addLayout(row)
        row.addWidget(self.button('Delete key at time','delete',self.delete_key));row.addWidget(self.button('Remove selected tracks','delete',self.remove_keys));row.addWidget(self.button('Import Animation Lite data','timeline',self.import_legacy));row.addStretch()
    def groups_selected(self):
        if self.app.scene.edit_group is not None:raise ValueError('Exit group editing first.')
        groups=[g for g in self.app.scene.groups if g in self.app.scene.selection]
        if not groups:raise ValueError('Select top-level groups / components in the model first.')
        if any(g.billboard for g in groups):raise ValueError('Face-me billboard transforms cannot be recorded.')
        return groups
    def add_objects(self):
        d=self.read();groups=self.groups_selected()
        for g in groups:
            if g.uid not in d['objects']:d['objects'][g.uid]=dict(name=g.name,keys=[dict(t=0.,value=e.pose(g.xform))])
        self.commit(d,groups)
    def record_objects(self):
        d=self.read();groups=self.groups_selected()
        for g in groups:
            if g.uid not in d['objects'] or g.xform is None:raise ValueError('Add this group before moving it. Re-add a track if geometry was materialized.')
            e.put_key(d['objects'][g.uid]['keys'],self.key_time.value(),e.pose(g.xform))
        self.commit(d)
    def record_camera(self):
        d=self.read();e.put_key(d['camera'],self.key_time.value(),e.camera_data(self.app.viewport.camera));self.commit(d)
    def refresh_keys(self):
        self.key_list.clear()
        for uid,tr in list(self.data['objects'].items())+[('@camera',dict(name='Camera',keys=self.data['camera']))]:
            if uid=='@camera' and not tr['keys']:continue
            times=', '.join(f'{k["t"]:g}s' for k in tr['keys'])
            self.key_list.addItem(f'{tr["name"]}   ·   {times or "No keys"}');self.key_list.item(self.key_list.count()-1).setData(Qt.UserRole,uid)
    def delete_key(self):
        d=self.read()
        for item in self.key_list.selectedItems():
            uid=item.data(Qt.UserRole);keys=d['camera'] if uid=='@camera' else d['objects'][uid]['keys'];keys[:]=[k for k in keys if abs(k['t']-self.key_time.value())>.0001]
        self.commit(d)
    def remove_keys(self):
        d=self.read()
        for item in self.key_list.selectedItems():
            uid=item.data(Qt.UserRole)
            if uid=='@camera':d['camera']=[]
            else:d['objects'].pop(uid,None)
        self.commit(d)
    def import_legacy(self):
        raw=self.app.scene.plugin_data.get('ingetrazo_animation')
        if not raw or raw.get('schema')!=1 or len(raw.get('clips',[]))!=1:raise ValueError('No compatible Animation Lite data in this model.')
        d=self.read()
        if d['objects'] or d['camera']:raise ValueError('Remove current object / camera tracks before importing. Phase tracks are kept.')
        d['objects']=copy.deepcopy(raw['clips'][0]['tracks']);d['camera']=copy.deepcopy(raw['clips'][0]['camera']);d['duration']=max(d['duration'],raw['duration']);self.commit(d)
    def build_export(self):
        panel=QWidget();box=QVBoxLayout(panel);self.tabs.addTab(panel,'Export animation')
        label=QLabel('Native GPU / OpenGL export\nPNG sequences work without an encoder. MP4 and WebM use your installed FFmpeg.');label.setWordWrap(True);box.addWidget(label)
        form=QFormLayout();box.addLayout(form)
        self.ratio=QComboBox();self.ratio.addItems(e.SIZES);self.size=QComboBox();self.export_fps=QComboBox();self.export_fps.addItems([str(f) for f in e.FPS]);self.format=QComboBox();self.format.addItems(['PNG sequence','MP4 · H.264','WebM · VP9'])
        self.ffmpeg=QLineEdit(QSettings('IngeTrazo','PhasingAnimator').value('ffmpeg',shutil.which('ffmpeg') or ''));self.ffmpeg.setPlaceholderText('Optional: path to ffmpeg executable')
        form.addRow('Renderer',QLabel('IngeTrazo native OpenGL (GPU)'));form.addRow('Canvas ratio',self.ratio);form.addRow('Output size',self.size);form.addRow('Frames per second',self.export_fps);form.addRow('Format',self.format)
        row=QHBoxLayout();row.addWidget(self.ffmpeg);row.addWidget(self.button('Browse','export',self.browse_ffmpeg));form.addRow('FFmpeg',row)
        self.export_summary=QLabel();box.addWidget(self.export_summary)
        row=QHBoxLayout();box.addLayout(row);self.render=self.button('Export animation…','export',self.start_export);self.render.setProperty('primary',True);row.addWidget(self.render);self.cancel=self.button('Cancel export','delete',self.cancel_export);self.cancel.setEnabled(False);row.addWidget(self.cancel);row.addStretch()
        self.progress=QProgressBar();self.progress.setValue(0);box.addWidget(self.progress);self.export_status=QLabel('Choose settings, then select an output folder.');self.export_status.setWordWrap(True);box.addWidget(self.export_status);box.addStretch()
        self.ratio.currentIndexChanged.connect(self.populate_sizes)
        for w in (self.size,self.export_fps,self.format):w.currentIndexChanged.connect(self.export_info)
        self.populate_sizes()
    def populate_sizes(self):
        self.size.clear()
        for w,h in e.SIZES[self.ratio.currentText()]:self.size.addItem(f'{w} × {h}',[w,h])
        self.size.setCurrentIndex(min(1,self.size.count()-1));self.export_info()
    def export_info(self):
        if not hasattr(self,'export_summary') or not self.size.currentData():return
        fps=int(self.export_fps.currentText());self.export_summary.setText(f'{e.frame_count(self.data["duration"],fps)} frames · {self.data["duration"]:g} seconds · {self.ratio.currentText()}')
    def load_export(self):
        cfg=self.data['export'];self.ratio.setCurrentText(cfg.get('ratio','16:9'));self.populate_sizes()
        for i in range(self.size.count()):
            if self.size.itemData(i)==cfg.get('size'):self.size.setCurrentIndex(i)
        self.export_fps.setCurrentText(str(cfg.get('fps',30)));self.format.setCurrentText(cfg.get('format','PNG sequence'));self.render.setEnabled(True);self.export_info()
    def browse_ffmpeg(self):
        path,_=QFileDialog.getOpenFileName(self,'Select FFmpeg executable')
        if path:self.ffmpeg.setText(path)
    def start_export(self):
        if self.busy:return
        cfg=dict(ratio=self.ratio.currentText(),size=self.size.currentData(),fps=int(self.export_fps.currentText()),format=self.format.currentText())
        encoder=self.ffmpeg.text().strip()
        if cfg['format']!='PNG sequence' and not Path(encoder).is_file():raise ValueError('Choose an installed FFmpeg executable, or select PNG sequence.')
        folder=QFileDialog.getExistingDirectory(self,'Select output folder')
        if not folder:return
        self.begin_export(folder,cfg,encoder)
    def begin_export(self,folder,cfg,encoder=''):
        """Start an export in a fresh child directory, never overwriting a run."""
        if self.busy:raise ValueError('An export is already running.')
        d=self.read();d['export']=cfg;self.commit(d)
        self.export_settings=copy.deepcopy(cfg);self.encoder=encoder
        QSettings('IngeTrazo','PhasingAnimator').setValue('ffmpeg',encoder)
        self.export_folder=Path(folder)/('Phasing-Animator-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);self.export_folder.mkdir()
        self.frame=0;self.total=e.frame_count(d['duration'],cfg['fps']);self.restore_time=self.t;self.busy=True
        self.cancel.setEnabled(True);self.render.setEnabled(False)
        self.restore_tab=self.tabs.currentIndex();self.tabs.setCurrentIndex(0);self.tabs.tabBar().setEnabled(False)
        self.export_strip.show();self.tabs.widget(0).setEnabled(False)
        # Keep the GL widget visible and allow its first show/initializeGL event.
        self.progress.setRange(0,self.total);self.progress.setValue(0)
        self.export_status.setText('Preparing GPU preview…')
        self.gpu_wait_started=time.monotonic()
        try:self.manifest('rendering');self.export_timer.start(20)
        except Exception as exc:self.finish_export('failed',str(exc))
    def manifest(self,status):
        if not self.export_folder:return
        cfg=self.export_settings
        value=dict(app=e.TITLE,version=e.VERSION,status=status,renderer='IngeTrazo native OpenGL',settings=cfg,duration=self.data['duration'],expected_frames=self.total,written_frames=self.frame,endpoint_sampling=True)
        (self.export_folder/'manifest.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    def export_frame(self):
        try:
            if not self.vp.isValid():
                if time.monotonic()-self.gpu_wait_started<5:return
                raise RuntimeError('OpenGL preview could not initialize. Check your graphics driver.')
            cfg=self.export_settings;w,h=cfg['size'];t=e.frame_time(self.frame,self.data['duration'],cfg['fps']);self.seek(t,True)
            old=self.vp.camera.aspect;self.vp.camera.aspect=w/h
            try:image=self.vp.render_image(w,h,overlays=False)
            finally:self.vp.camera.aspect=old
            if image is None or image.isNull():raise RuntimeError('OpenGL rendering is unavailable. Reopen the editor with a working GPU viewport.')
            if not image.save(str(self.export_folder/f'frame-{self.frame:06d}.png')):raise OSError('Could not save frame. Check output space and permissions.')
            self.frame+=1;self.progress.setValue(self.frame);self.export_status.setText(f'Rendering {self.frame} / {self.total} · {w} × {h}')
            if self.frame>=self.total:
                self.export_timer.stop()
                if cfg['format']=='PNG sequence':self.finish_export('complete')
                else:self.encode_video()
        except Exception as exc:self.finish_export('failed',str(exc))
    def encode_video(self):
        cfg=self.export_settings;mp4=cfg['format'].startswith('MP4');self.video_path=self.export_folder/('animation.mp4' if mp4 else 'animation.webm')
        self.partial_path=self.export_folder/('animation.partial.mp4' if mp4 else 'animation.partial.webm')
        args=['-hide_banner','-loglevel','error','-nostdin','-n','-framerate',str(cfg['fps']),'-i',str(self.export_folder/'frame-%06d.png'),'-an']
        args+=['-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart'] if mp4 else ['-c:v','libvpx-vp9','-crf','30','-b:v','0','-pix_fmt','yuv420p']
        args+=[str(self.partial_path)];self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels);self.encoder_log=''
        self.process.readyReadStandardOutput.connect(self.read_encoder);self.process.finished.connect(self.encoded);self.process.errorOccurred.connect(self.encoder_error)
        self.export_status.setText('Encoding video… PNG frames are retained.');self.manifest('encoding');self.process.start(self.encoder,args)
    def read_encoder(self):
        if self.process:self.encoder_log=(self.encoder_log+bytes(self.process.readAllStandardOutput()).decode('utf-8','replace'))[-4000:]
    def encoded(self,code,status):
        if not self.busy:return
        self.read_encoder()
        if code==0 and self.partial_path.exists():
            try:self.partial_path.rename(self.video_path);self.finish_export('complete')
            except OSError as exc:self.finish_export('failed',str(exc))
        else:self.finish_export('failed',self.encoder_log or 'Video encoder failed; PNG frames are retained.')
    def encoder_error(self,error):
        if self.busy and error==QProcess.FailedToStart:self.finish_export('failed','FFmpeg could not start. PNG frames are retained.')
    def cancel_export(self):
        if self.busy:self.finish_export('cancelled')
    def finish_export(self,status,detail=''):
        self.export_timer.stop();self.busy=False
        if self.process:
            process=self.process;self.process=None
            process.finished.disconnect();process.errorOccurred.disconnect();process.readyReadStandardOutput.disconnect()
            if process.state()!=QProcess.NotRunning:process.kill();process.waitForFinished(1000)
            process.deleteLater()
        try:self.manifest(status)
        except OSError as exc:detail+=' '+str(exc)
        self.tabs.widget(0).setEnabled(True);self.tabs.tabBar().setEnabled(True);self.tabs.setCurrentIndex(getattr(self,'restore_tab',2))
        self.cancel.setEnabled(False);self.render.setEnabled(True);self.seek(getattr(self,'restore_time',0))
        self.export_status.setText(f'Export {status}. {detail}\n{self.export_folder}');self.status.setText(f'Export {status}. Source model unchanged.')
    def reject(self):self.pause();self.cancel_export();self.refresh_timer.stop();super().reject()
    def closeEvent(self,event):self.pause();self.cancel_export();self.refresh_timer.stop();event.accept()


class Controller:
    def __init__(self,app):
        self.app=app;self.editor=None
        self.toolbar=QToolBar(e.TITLE,app.window);self.toolbar.setObjectName(e.KEY+'_toolbar');self.toolbar.setMovable(True);self.toolbar.setFloatable(True);self.toolbar.setIconSize(QSize(24,24));self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        for kind,title,fn in [('timeline','Open Phasing Animator',self.open),('record','Object and camera keyframes',lambda:self.open(1)),('play','Play / pause animation',self.play),('export','Export animation',lambda:self.open(2))]:
            a=QAction(icon(kind),title,self.toolbar);a.setToolTip(title);a.triggered.connect(lambda _=False,f=fn:f());self.toolbar.addAction(a)
        app.window.addToolBar(self.toolbar);app.add_menu_action(e.TITLE,self.open,tip='Layer phases, keyframes, timeline and animation export')
    def open(self,tab=0):
        try:
            if self.app.scene.edit_group is not None:raise ValueError('Exit group editing before opening Phasing Animator.')
            if self.editor is None:self.editor=Studio(self.app)
            self.editor.reload();self.editor.tabs.setCurrentIndex(tab);self.editor.show();self.editor.raise_();self.editor.activateWindow()
        except Exception as exc:QMessageBox.warning(self.app.window,e.TITLE,str(exc))
    def play(self):
        if self.editor is None or not self.editor.isVisible():self.open()
        if self.editor:self.editor.safe(self.editor.toggle)

