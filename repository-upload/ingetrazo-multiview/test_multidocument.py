"""Qt lifecycle checks with a tabbed host adapter and stub OpenGL viewports."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import types
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget
from shiboken6 import delete, isValid

from test_theme_performance import app as qt_app, plugin


class StubViewport(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = types.SimpleNamespace(
            bounds=lambda: (QVector3D(-1, -1, -1), QVector3D(1, 1, 1)))
        self.history = object()
        self.camera = types.SimpleNamespace(
            perspective=True, set_view=Mock(), fit_box=Mock(),
            target=QVector3D(), distance=20.0)
        self.nav_mode = None
        self.active_tool = object()
        self._vbo_parts = {}
        self._edges_version = 0
        self.sceneVersionChanged = types.SimpleNamespace(connect=Mock())
        self.flash_status = Mock()
        self.reset_document_caches = Mock()
        self.nav_calls = []

    def set_nav_mode(self, mode):
        self.nav_mode = mode
        self.nav_calls.append(mode)

    def isValid(self):
        return False  # No OpenGL context in these tests.


class TabWindow(QMainWindow):
    """Model the per-project central-widget API described by the host developer."""
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        super().setCentralWidget(self.tabs)
        self.owner = None
        self.slots = []
        self.viewports = []
        for name in ("A", "B"):
            slot = QWidget()
            layout = QVBoxLayout(slot)
            viewport = StubViewport(slot)
            layout.addWidget(viewport)
            self.slots.append(slot)
            self.viewports.append(viewport)
            self.tabs.addTab(slot, name)

    def _slot(self):
        return self.owner if self.owner is not None else self.tabs.currentWidget()

    def centralWidget(self):
        slot = self._slot()
        if slot is None or not isValid(slot) or not slot.layout().count():
            return None
        return slot.layout().itemAt(0).widget()

    def takeCentralWidget(self):
        slot = self._slot()
        widget = self.centralWidget()
        if widget is not None:
            self.owner = slot
            slot.layout().removeWidget(widget)
            widget.setParent(None)
        return widget

    def setCentralWidget(self, widget):
        slot = self._slot()
        slot.layout().addWidget(widget)
        if any(widget is vp for vp in self.viewports):
            self.owner = None


class Host:
    def __init__(self, window, close_hook=True):
        self.window = window
        self.changed = []
        self.closed = []
        if not close_hook:
            self.on_document_closed = None

    @property
    def viewport(self):
        slot = self.window.tabs.currentWidget()
        if slot is None:
            return None
        return self.window.viewports[self.window.slots.index(slot)]

    def on_document_changed(self, callback):
        self.changed.append(callback)

    def on_document_closed(self, callback):
        self.closed.append(callback)

    def switch(self, index, notify=True):
        self.window.tabs.setCurrentIndex(index)
        if notify:
            for callback in self.changed:
                callback(self.viewport)

    def close_slot(self, index, notify_before=False):
        slot = self.window.slots[index]
        if notify_before:
            for callback in self.closed:
                callback(index)
        tab_index = self.window.tabs.indexOf(slot)
        self.window.tabs.removeTab(tab_index)
        if self.window.owner is slot:
            self.window.owner = None
        delete(slot)
        if not notify_before:
            for callback in self.closed:
                callback(index)


class MultiDocumentTests(unittest.TestCase):
    def setUp(self):
        self.window = TabWindow()
        self.host = Host(self.window)
        units = types.ModuleType("core.units")
        units.bind_scene = Mock()
        core = types.ModuleType("core")
        core.units = units
        icons = types.ModuleType("views.icons")
        icons.toolbar_icon_px = lambda: 24
        icons.style_overflow_button = lambda toolbar: None
        self.module_patch = patch.dict(sys.modules, {
            "core": core, "core.units": units, "views.icons": icons})
        self.module_patch.start()
        self.viewport_patch = patch.object(plugin, "Viewport", StubViewport)
        self.viewport_patch.start()
        self.controller = plugin.MultiViewController(self.host)

    def tearDown(self):
        self.controller.deactivate()
        self.controller._discard_layout()
        qt_app.removeEventFilter(self.controller._space_filter)
        delete(self.window)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        qt_app.processEvents()
        self.viewport_patch.stop()
        self.module_patch.stop()

    def assert_project(self, index):
        c = self.controller
        self.assertTrue(c.is_active)
        self.assertIs(c.main_vp, self.window.viewports[index])
        self.assertIs(c.container.cell_persp.viewport, c.main_vp)
        for vp in (c.top_vp, c.front_vp, c.right_vp):
            self.assertIs(vp.scene, c.main_vp.scene)
            self.assertIs(vp.history, c.main_vp.history)

    def test_activate_on_second_tab_without_first_activation(self):
        self.host.switch(1)
        self.controller.activate()
        self.assert_project(1)
        self.assertIs(self.window.tabs.widget(0).layout().itemAt(0).widget(),
                      self.window.viewports[0])

    def test_switch_deactivates_original_and_rebuilds_for_next_project(self):
        c = self.controller
        c.activate()
        old_container = c.container
        old_secondary = c.top_vp
        self.host.switch(1)
        self.assertFalse(c.is_active)
        self.assertIsNone(c.container)
        self.assertIs(self.window.slots[0].layout().itemAt(0).widget(),
                      self.window.viewports[0])
        c.activate()
        self.assert_project(1)
        self.assertIsNot(c.container, old_container)
        self.assertIsNot(c.top_vp, old_secondary)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(old_container))
        self.assertFalse(isValid(old_secondary))
        self.assertTrue(isValid(self.window.viewports[0]))
        self.assertTrue(isValid(self.window.viewports[1]))
        self.host.switch(0)
        c.activate()
        self.assert_project(0)

    def test_repeated_toggles_reuse_layout_and_do_not_stack_nav_hooks(self):
        c = self.controller
        original = self.host.viewport.set_nav_mode
        for _ in range(10):
            c.activate()
            container = c.container
            self.host.viewport.set_nav_mode("pan")
            self.assertTrue(all(cell.viewport.nav_mode == "pan"
                                for cell in c.container.all_cells))
            c.deactivate()
            self.assertEqual(self.host.viewport.set_nav_mode, original)
            self.assertIs(c.container, container)
        self.assertEqual(self.host.viewport.nav_calls, ["pan"] * 10)
        self.assertEqual(self.window.tabs.count(), 2)

    def test_navigation_moves_to_new_tab_and_leaves_previous_tab_alone(self):
        c = self.controller
        original_a = self.host.viewport.set_nav_mode
        c.activate()
        self.host.switch(1)
        self.assertEqual(self.window.viewports[0].set_nav_mode, original_a)
        c.activate()
        self.window.viewports[0].set_nav_mode("orbit")
        self.assertIsNone(c.top_vp.nav_mode)
        self.host.viewport.set_nav_mode("pan")
        self.assertEqual(c.top_vp.nav_mode, "pan")

    def test_single_view_presets_and_zoom_follow_selected_tab(self):
        self.host.switch(1)
        self.controller.apply_preset_view("front", False)
        self.controller.zoom_extents_all()
        a, b = self.window.viewports
        a.camera.set_view.assert_not_called()
        a.camera.fit_box.assert_not_called()
        b.camera.set_view.assert_called_once_with("front")
        b.camera.fit_box.assert_called_once()

    def test_close_first_tab_after_qt_deletes_active_grid(self):
        c = self.controller
        c.activate()
        first = c.main_vp
        self.host.close_slot(0)
        self.assertFalse(isValid(first))
        self.assertFalse(c.is_active)
        self.assertIsNone(c.main_vp)
        self.assertFalse(c.act_toggle.isChecked())
        c.activate()
        self.assert_project(1)

    def test_close_notification_before_deletion_restores_host_viewport(self):
        self.controller.activate()
        self.host.close_slot(0, notify_before=True)
        self.assertFalse(self.controller.is_active)
        self.controller.activate()
        self.assert_project(1)

    def test_close_first_tab_before_any_activation(self):
        self.host.close_slot(0)
        self.controller.activate()
        self.assert_project(1)

    def test_close_last_tab_and_use_actions_is_safe(self):
        self.controller.activate()
        self.host.close_slot(0)
        self.controller.activate()
        self.host.close_slot(1)
        self.controller.activate()
        self.controller.apply_preset_view("top", False)
        self.controller.zoom_extents_all()
        self.controller.toggle_two_views(True)
        self.assertFalse(self.controller.is_active)
        self.assertFalse(self.controller.act_two.isChecked())

    def test_new_document_in_same_viewport_discards_old_scene_and_tools(self):
        c = self.controller
        c.activate()
        vp = c.main_vp
        old = c.top_vp
        vp.scene = types.SimpleNamespace(bounds=lambda: (None, None))
        vp.history = object()
        vp.active_tool = object()
        self.host.changed[0]()
        self.assertFalse(c.is_active)
        c.activate()
        self.assert_project(0)
        self.assertIsNot(c.top_vp, old)
        self.assertIs(c.top_vp.active_tool, vp.active_tool)

    def test_refuses_other_workspace_and_resets_checked_actions(self):
        other = QWidget(self.window.slots[0])
        original = self.window.takeCentralWidget()
        original.setParent(self.window)
        self.window.setCentralWidget(other)
        self.controller.act_toggle.setChecked(True)
        self.controller.toggle_two_views(True)
        self.assertFalse(self.controller.is_active)
        self.assertFalse(self.controller.act_toggle.isChecked())
        self.assertFalse(self.controller.act_two.isChecked())
        original.flash_status.assert_called_once()
        self.assertIs(self.window.centralWidget(), other)

    def test_toggle_off_from_another_tab_without_switch_notifications(self):
        self.controller.activate()
        self.host.switch(1, notify=False)
        self.controller.deactivate()
        for index, vp in enumerate(self.window.viewports):
            self.assertIs(self.window.slots[index].layout().itemAt(0).widget(), vp)
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.controller.activate()
        self.assert_project(1)

    def test_older_host_without_close_hook(self):
        old_host = Host(self.window, close_hook=False)
        old = plugin.MultiViewController(old_host)
        try:
            old.activate()
            self.assertTrue(old.is_active)
            old_host.changed[0]()
            self.assertFalse(old.is_active)
        finally:
            old.deactivate()
            old._discard_layout()
            qt_app.removeEventFilter(old._space_filter)

    def test_other_extension_nav_wrapper_is_preserved(self):
        c = self.controller
        c.activate()
        vp = c.main_vp
        ours = vp.set_nav_mode
        external = lambda mode: ours(mode)
        vp.set_nav_mode = external
        c.deactivate()
        self.assertIs(vp.set_nav_mode, external)
        vp.set_nav_mode("orbit")
        self.assertEqual(vp.nav_mode, "orbit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
