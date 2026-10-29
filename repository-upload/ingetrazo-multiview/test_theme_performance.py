"""Qt regression checks for MultiView styling; host/OpenGL viewport is stubbed."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

source = Path(__file__).resolve().parent / "ingetrazo_multiview.py"
viewport_module = types.ModuleType("views.viewport")
viewport_module.Viewport = QWidget
with patch.dict(sys.modules, {"views.viewport": viewport_module}):
    spec = importlib.util.spec_from_file_location("multiview_under_test", source)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
plugin._log = lambda message: None
plugin.is_dark_ui = lambda widget=None: False
app = QApplication.instance() or QApplication([])


class ThemePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.window = QMainWindow()
        self.controller = types.SimpleNamespace(
            window=self.window, toolbar=None, is_active=False,
            _reposition_sidebar_handle=lambda: None,
            update_toolbar_state=Mock(),
        )
        for name in ("main_vp", "top_vp", "front_vp", "right_vp"):
            viewport = QWidget()
            viewport.camera = types.SimpleNamespace(perspective=True)
            setattr(self.controller, name, viewport)
        self.container = plugin.MultiViewContainer(self.controller)
        self.controller.container = self.container

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        app.processEvents()

    def test_first_style_and_initial_active_selection(self):
        self.assertIs(self.container.active_cell, self.container.cell_persp)
        for cell in self.container.all_cells:
            self.assertTrue(cell.styleSheet())
            self.assertEqual(cell.is_active, cell is self.container.cell_persp)
            self.assertIn("2px" if cell.is_active else "1px", cell.styleSheet())

    def test_100_repeated_clicks_skip_cell_and_toolbar_work(self):
        self.controller.toolbar = object()
        with patch.object(plugin.QuadCell, "setStyleSheet", autospec=True) as styles:
            for _ in range(100):
                self.container.set_active_cell(self.container.cell_persp)
        self.assertEqual(styles.call_count, 0)
        self.controller.update_toolbar_state.assert_not_called()

    def test_switch_updates_only_old_and_new_active_cells(self):
        calls = []
        original = plugin.QuadCell.setStyleSheet

        def record(cell, stylesheet):
            calls.append(cell)
            original(cell, stylesheet)

        self.controller.toolbar = object()
        with patch.object(plugin.QuadCell, "setStyleSheet", record):
            self.container.set_active_cell(self.container.cell_top)
        self.assertEqual(calls, [self.container.cell_top, self.container.cell_persp])
        self.controller.update_toolbar_state.assert_called_once()
        self.assertTrue(self.container.cell_top.is_active)
        self.assertFalse(self.container.cell_persp.is_active)

    def test_direct_same_state_call_does_not_reapply_stylesheet(self):
        for cell in self.container.all_cells:
            with patch.object(cell, "setStyleSheet") as styles:
                cell.set_active(cell.is_active)
                styles.assert_not_called()

    def test_theme_flip_refreshes_active_and_inactive_cells(self):
        before = [cell.styleSheet() for cell in self.container.all_cells]
        with patch.object(plugin, "is_dark_ui", return_value=True):
            self.container.apply_theme()
            for cell, old_style in zip(self.container.all_cells, before):
                self.assertNotEqual(cell.styleSheet(), old_style)
                self.assertIn("#1e1e1e", cell.styleSheet())
                self.assertIn("#252526", cell.header.styleSheet())
                self.assertEqual(cell.is_active, cell is self.container.cell_persp)
        self.container.apply_theme()
        self.assertEqual(before, [cell.styleSheet() for cell in self.container.all_cells])

    def test_container_ignores_local_palette_changes(self):
        with patch.object(self.container, "apply_theme") as refresh:
            self.container.changeEvent(QEvent(QEvent.PaletteChange))
            refresh.assert_not_called()
            self.container.changeEvent(QEvent(QEvent.ApplicationPaletteChange))
            self.container.changeEvent(QEvent(QEvent.ThemeChange))
            self.assertEqual(refresh.call_count, 2)

    def test_application_palette_event_does_not_recurse(self):
        with patch.object(self.container, "apply_theme", wraps=self.container.apply_theme) as refresh:
            self.container.changeEvent(QEvent(QEvent.ApplicationPaletteChange))
            app.processEvents()
            self.assertEqual(refresh.call_count, 1)

    def test_controller_ignores_local_palette_changes(self):
        with patch.object(self.container, "apply_theme") as refresh:
            for event_type in (QEvent.PaletteChange, QEvent.StyleChange):
                self.assertFalse(plugin.MultiViewController.eventFilter(
                    self.controller, self.window, QEvent(event_type)))
            refresh.assert_not_called()
            self.controller.update_toolbar_state.assert_not_called()
            for event_type in (QEvent.ApplicationPaletteChange, QEvent.ThemeChange):
                self.assertFalse(plugin.MultiViewController.eventFilter(
                    self.controller, self.window, QEvent(event_type)))
            self.assertEqual(refresh.call_count, 2)
            self.assertEqual(self.controller.update_toolbar_state.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
