# SPDX-License-Identifier: GPL-3.0-or-later
"""Native OpenGL smoke test; opens a temporary test editor, then exits."""
import os,sys,json,traceback,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[os.environ['INGETRAZO_SOURCE'],str(ROOT)]
os.environ.pop('QT_QPA_PLATFORM',None)
from PySide6.QtWidgets import QApplication,QToolBar
from PySide6.QtCore import QTimer,QSettings,Qt
from PySide6.QtGui import QImage,QVector3D as V
from formats.igz import save_scene
from phasing_animator import engine as e
from phasing_animator.ui import Studio,Controller
from demo import scene
app=QApplication([])
QSettings.setDefaultFormat(QSettings.IniFormat)
for scope in (QSettings.UserScope,QSettings.SystemScope):QSettings.setPath(QSettings.IniFormat,scope,str(ROOT/'tests/settings'))
import core.extensions
core.extensions.discover_plugins=lambda *a,**k:([],[])
from views.main_window import MainWindow
from views.extension_api import ExtensionApp
w=MainWindow();s=scene();w.viewport.scene=s;w.viewport.history.scene=s
w.viewport.camera.target=V(0,0,1.6);w.viewport.camera.distance=14;w.viewport.camera.yaw=.7;w.viewport.camera.pitch=.55
host=ExtensionApp(w,e.KEY);control=Controller(host);studio=Studio(host);studio.reload();studio.tabs.setCurrentIndex(2);studio.show()
out=ROOT/'tests/renders';out.mkdir(parents=True,exist_ok=True)
errors=[];result={}
def fail(exc):
    errors.append(str(exc));traceback.print_exc();studio.cancel_export();studio.close();w.hide();app.exit(1)
def safe(fn):
    def call():
        try:fn()
        except Exception as exc:fail(exc)
    return call
def png_export():
    # Export opened directly, with no previous visible preview.
    d=studio.read();d['duration']=.1
    for i,p in enumerate(d['phases']):p.update(start=i*.02,end=(i+1)*.025)
    studio.commit(d)
    studio.begin_export(out,dict(ratio='16:9',size=[1280,720],fps=24,format='PNG sequence'))
    poll_export(png_done)
def poll_export(callback):
    if studio.busy:QTimer.singleShot(60,safe(lambda:poll_export(callback)))
    else:callback()
def png_done():
    manifest=json.loads((studio.export_folder/'manifest.json').read_text())
    assert manifest['status']=='complete',studio.export_status.text()
    files=sorted(studio.export_folder.glob('frame-*.png'));assert len(files)==3
    first,last=QImage(str(files[0])),QImage(str(files[-1]));assert first.size().width()==1280 and first.size().height()==720
    assert first!=last,'Animation frames should change'
    result['landscape']={'frames':len(files),'size':[1280,720],'different_endpoints':True}
    studio.begin_export(out,dict(ratio='9:16',size=[1080,1920],fps=30,format='PNG sequence'));poll_export(portrait_done)
def portrait_done():
    manifest=json.loads((studio.export_folder/'manifest.json').read_text());assert manifest['status']=='complete',studio.export_status.text()
    image=QImage(str(studio.export_folder/'frame-000002.png'));assert (image.width(),image.height())==(1080,1920)
    result['portrait']={'frames':3,'size':[1080,1920]}
    if os.environ.get('PHASING_FFMPEG'):
        studio.begin_export(out,dict(ratio='16:9',size=[1280,720],fps=24,format='MP4 · H.264'),os.environ['PHASING_FFMPEG'])
        poll_export(mp4_done)
    else:cancel_check()
def decode(path):
    run=subprocess.run([os.environ['PHASING_FFMPEG'],'-hide_banner','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert run.returncode==0,run.stderr.decode('utf-8','replace')
def mp4_done():
    manifest=json.loads((studio.export_folder/'manifest.json').read_text());assert manifest['status']=='complete',studio.export_status.text()
    assert (studio.export_folder/'animation.mp4').stat().st_size>1000
    decode(studio.export_folder/'animation.mp4');result['mp4_decode']='passed'
    studio.begin_export(out,dict(ratio='16:9',size=[1280,720],fps=24,format='WebM · VP9'),os.environ['PHASING_FFMPEG'])
    poll_export(webm_done)
def webm_done():
    manifest=json.loads((studio.export_folder/'manifest.json').read_text());assert manifest['status']=='complete',studio.export_status.text()
    assert (studio.export_folder/'animation.webm').stat().st_size>1000
    decode(studio.export_folder/'animation.webm');result['webm_decode']='passed'
    studio.begin_export(out,dict(ratio='16:9',size=[1280,720],fps=24,format='MP4 · H.264'),str(out/'missing-encoder.exe'))
    poll_export(encoder_failure)
def encoder_failure():
    manifest=json.loads((studio.export_folder/'manifest.json').read_text());assert manifest['status']=='failed'
    assert len(list(studio.export_folder.glob('frame-*.png')))==3
    result['encoder_failure_preserves_frames']=True
    cancel_check()
def cancel_check():
    studio.begin_export(out,dict(ratio='16:9',size=[1280,720],fps=24,format='PNG sequence'));studio.cancel_export()
    assert json.loads((studio.export_folder/'manifest.json').read_text())['status']=='cancelled'
    assert not studio.busy and not studio.export_timer.isActive()
    result['cancelled_cleanly']=True
    capture()
def capture():
    s.plugin_data[e.KEY]=scene().plugin_data[e.KEY];studio.reload();studio.tabs.setCurrentIndex(0);studio.export_strip.hide();studio.seek(10.8)
    studio.choose(studio.data['phases'][-1]['id'])
    QTimer.singleShot(700,safe(capture_done))
def capture_done():
    assert studio.vp.isValid()
    studio.status.setText('Roof assembly · scrub the timeline to explore construction phases.')
    studio.grab().save(str(ROOT/'editor-preview.png'))
    studio.vp.grabFramebuffer().save(str(ROOT/'model-preview.png'))
    studio.tabs.setCurrentIndex(2);studio.ffmpeg.clear();studio.grab().save(str(ROOT/'export-preview.png'))
    tb=QToolBar();tb.setToolButtonStyle(Qt.ToolButtonIconOnly);tb.setIconSize(control.toolbar.iconSize());tb.addActions(control.toolbar.actions());tb.show();tb.adjustSize();app.processEvents();tb.grab().save(str(ROOT/'toolbar.png'));tb.close()
    examples=ROOT/'examples';examples.mkdir(exist_ok=True);save_scene(s,examples/'Pavilion-phasing.igz')
    result['renderer_valid']=True
    (out/'render-results.json').write_text(json.dumps(result,indent=2))
    print('PASS:',json.dumps(result),flush=True)
    studio.close();w.hide();app.quit()
def timeout():fail(RuntimeError('Render checks exceeded 60 seconds.'))
QTimer.singleShot(60000,timeout);QTimer.singleShot(300,safe(png_export));app.exec()
sys.exit(1 if errors else 0)
