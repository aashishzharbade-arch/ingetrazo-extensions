# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression test against the actual 0.5.7 host; no GPU rendering required."""
import os
import sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [os.environ['INGETRAZO_SOURCE'], str(root)]
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, QCoreApplication, QEvent
from views.main_window import MainWindow
from views.extension_api import ExtensionApp
import ingetrazo_multiview as plugin
app = QApplication([])
QSettings.setDefaultFormat(QSettings.IniFormat)
for scope in (QSettings.UserScope, QSettings.SystemScope):
    QSettings.setPath(QSettings.IniFormat, scope, str(root / 'test-settings'))
plugin._log = lambda message: None
window = MainWindow()
window.resize(1500, 950)
controller = plugin.MultiViewController(ExtensionApp(window, plugin.KEY))
editor = window.viewport
controller.activate()
container = controller.container
for n in range(10):
    window.layout().activate()
    app.processEvents()
    assert window.centralWidget() is container
    assert container.parentWidget() is window and not container.isWindow()
    assert window.viewport is editor
    controller.container.toggle_maximize(controller.container.cell_top)
    controller.deactivate()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    assert window.centralWidget() is editor
    assert container.isHidden() and not container.isWindow()
    assert editor.parentWidget() is window
    controller.activate()
    assert controller.container is container
    assert len(window.findChildren(plugin.MultiViewContainer)) == 1
controller.act_two.trigger()
assert container.two_views and container.bottom_splitter.isHidden()
container.toggle_maximize(container.cell_top)
container.toggle_maximize()
assert container.bottom_splitter.isHidden() and not container.top_splitter.isHidden()
controller.act_two.trigger()
assert not container.two_views and not container.bottom_splitter.isHidden()
controller.deactivate()
controller.act_two.trigger()
assert controller.is_active and container.two_views
controller.deactivate()
from core.scene import Scene
from core.history import History
editor.scene = Scene()
editor.history = History(editor.scene)
controller._on_doc_changed()
assert all(v.scene is editor.scene and v.history is editor.history
           for v in (controller.top_vp, controller.front_vp, controller.right_vp))
print('PASS: 10 toggle/maximize cycles; one retained container; hidden inactive panel; original editor restored.')
