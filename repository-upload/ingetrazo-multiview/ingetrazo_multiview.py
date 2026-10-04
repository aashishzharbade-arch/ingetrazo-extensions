# SPDX-License-Identifier: GPL-3.0-or-later
# IngeTrazo MultiView Extension
"""
IngeTrazo MultiView — 4-Viewport CAD Layout for IngeTrazo.
Provides Top, Perspective, Front, and Right viewports in a synchronized 2x2 grid,
with Double-Spacebar enlarge/restore, and a native dockable & floatable QToolBar.
Fully theme-adaptive: automatically matches IngeTrazo Light and Dark UI themes.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer, QObject, QEvent, QCoreApplication
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPolygonF, QIcon, QPixmap,
    QKeySequence, QAction, QCursor, QVector3D, QFont, QPalette
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QToolButton, QPushButton, QMenu, QLabel,
    QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QSizePolicy
)

from views.viewport import Viewport

DISPLAY_NAME = "IngeTrazo MultiView"
TOOLBAR_NAME = "ingetrazo_multiview_toolbar"
KEY = "ingetrazo_multiview"
VERSION = "1.0.5"

# Diagnostic log. Errors are always written; set INGETRAZO_MULTIVIEW_DEBUG=1
# to log every event too. It lives in the per-user application data folder on
# every system (LOCALAPPDATA only exists on Windows: elsewhere the old path
# fell back to the folder IngeTrazo was started from) and is capped in size.
_DEBUG = os.environ.get("INGETRAZO_MULTIVIEW_DEBUG", "") == "1"
_LOG_MAX_BYTES = 256 * 1024
_ERROR_WORDS = ("ERROR", "Error", "CRITICAL", "Failed", "Traceback")


def _log_path() -> Path:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    return Path(base or Path.home()) / "multiview.log"


def _log(msg: str):
    if not _DEBUG and not any(w in msg for w in _ERROR_WORDS):
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _LOG_MAX_BYTES:
            path.replace(path.with_suffix(".log.old"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ==============================================================================
# Dynamic UI Theme Detection & Styling
# ==============================================================================

def is_dark_ui(widget: QWidget | None = None) -> bool:
    """Detects whether IngeTrazo is currently in Dark or Light mode."""
    # 1. Native IngeTrazo theme detector (views.theme.saved_theme & is_dark)
    try:
        from views.theme import saved_theme, is_dark
        from PySide6.QtGui import QGuiApplication
        scheme = QGuiApplication.styleHints().colorScheme()
        res = bool(is_dark(saved_theme(), scheme))
        _log(f"is_dark_ui: {res} (views.theme mode='{saved_theme()}', scheme={scheme})")
        return res
    except Exception:
        pass

    # 2. Direct QSettings lookup
    try:
        from PySide6.QtCore import QSettings
        mode = str(QSettings().value("general/theme", "dark") or "dark").lower()
        if mode == "light":
            _log("is_dark_ui: False (QSettings general/theme='light')")
            return False
        if mode == "dark":
            _log("is_dark_ui: True (QSettings general/theme='dark')")
            return True
    except Exception:
        pass

    # 3. Fallback to palette luminance
    try:
        pal = widget.palette() if widget is not None else QApplication.palette()
        bg = pal.color(QPalette.Window)
        res = bg.value() < 128
        _log(f"is_dark_ui: {res} (palette Window val={bg.value()})")
        return res
    except Exception:
        return False


def get_theme_colors(widget: QWidget | None = None) -> dict:
    """Returns theme color tokens matching the user's selected UI theme (Light or Dark)."""
    dark = is_dark_ui(widget)
    if dark:
        return {
            "is_dark": True,
            "header_bg": "#252526",
            "header_border": "#333333",
            "header_text": "#e0e0e0",
            "header_btn_hover": "#3e3e42",
            "header_btn_hover_text": "#ffffff",
            "max_btn": "#888888",
            "menu_bg": "#252526",
            "menu_text": "#cccccc",
            "menu_border": "#3e3e42",
            "cell_bg": "#1e1e1e",
            "cell_border_inactive": "#333333",
            "cell_border_active": "#f37329",
            "splitter_handle": "#2b2b2b",
            "splitter_handle_hover": "#f37329",
            "container_bg": "#1e1e1e",
            "icon_ink": "#e0e0e0",
            "icon_grid": "#78909c",
        }
    else:
        return {
            "is_dark": False,
            "header_bg": "#e6e6e6",
            "header_border": "#d0d0d0",
            "header_text": "#2c3e50",
            "header_btn_hover": "#d8d8d8",
            "header_btn_hover_text": "#111111",
            "max_btn": "#555555",
            "menu_bg": "#ffffff",
            "menu_text": "#2c3e50",
            "menu_border": "#d0d0d0",
            "cell_bg": "#f5f5f5",
            "cell_border_inactive": "#d0d0d0",
            "cell_border_active": "#f37329",
            "splitter_handle": "#d0d0d0",
            "splitter_handle_hover": "#f37329",
            "container_bg": "#f0f0f0",
            "icon_ink": "#2c3e50",
            "icon_grid": "#607d8b",
        }


# ==============================================================================
# Crisp Vector Icons for Native Toolbar (Adaptive Theme Ink)
# ==============================================================================

def make_quad_icon(active: bool = False, dark: bool = False, two: bool = False) -> QIcon:
    """Draws a crisp CAD 4-quadrant layout symbol."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    border_color = "#f37329" if active else ("#e0e0e0" if dark else "#2c3e50")
    border_pen = QPen(QColor(border_color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    bg_color = QColor("#f37329" if active else ("#ffffff" if dark else "#000000"))
    bg_color.setAlpha(35 if active else 12)
    p.setPen(border_pen)
    p.setBrush(QBrush(bg_color))
    p.drawRoundedRect(6, 6, 52, 52, 6, 6)

    grid_color = "#f37329" if active else ("#78909c" if dark else "#607d8b")
    p.setPen(QPen(QColor(grid_color), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(32, 8, 32, 56)
    if not two:
        p.drawLine(8, 32, 56, 32)

    persp_col = QColor("#f37329" if active else "#1e88e5")
    persp_col.setAlpha(160 if active else 90)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(persp_col))
    p.drawRoundedRect(34, 8, 22, 48 if two else 22, 3, 3)

    p.end()
    return QIcon(pix)


def make_max_restore_icon(maximized: bool = False, dark: bool = False) -> QIcon:
    """Draws Enlarge or Restore symbol."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    pen_color = "#e0e0e0" if dark else "#2c3e50"
    p.setPen(QPen(QColor(pen_color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    if not maximized:
        p.drawRoundedRect(8, 8, 48, 48, 6, 6)
        accent_pen = QPen(QColor("#f37329"), 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(accent_pen)
        p.drawLine(16, 26, 16, 16)
        p.drawLine(16, 16, 26, 16)
        p.drawLine(48, 38, 48, 48)
        p.drawLine(48, 48, 38, 48)
    else:
        p.drawRoundedRect(18, 18, 38, 38, 4, 4)
        p.setPen(QPen(QColor("#f37329"), 3.5, Qt.SolidLine, Qt.RoundCap))
        p.drawRoundedRect(8, 8, 36, 36, 4, 4)

    p.end()
    return QIcon(pix)


def make_view_top_icon() -> QIcon:
    """Draws Top View (Plan) symbol with blueprint grid and badge."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    p.setPen(QPen(QColor("#e05656"), 3, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(QBrush(QColor(224, 86, 86, 25)))
    p.drawRoundedRect(8, 8, 48, 48, 6, 6)

    p.setPen(QPen(QColor("#e05656"), 2, Qt.DashLine))
    p.drawLine(8, 32, 56, 32)
    p.drawLine(32, 8, 32, 56)

    p.setPen(QColor("#e05656"))
    font = p.font()
    font.setPixelSize(14)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(8, 14, 48, 36), Qt.AlignCenter, "TOP")

    p.end()
    return QIcon(pix)


def make_view_persp_icon() -> QIcon:
    """Draws 3D Perspective symbol with isometric cube faces."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(QPen(QColor("#1e88e5"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(QColor(30, 136, 229, 60)))
    poly_top = QPolygonF([QPointF(32, 12), QPointF(52, 22), QPointF(32, 32), QPointF(12, 22)])
    p.drawPolygon(poly_top)

    p.setBrush(QBrush(QColor(30, 136, 229, 120)))
    poly_left = QPolygonF([QPointF(12, 22), QPointF(32, 32), QPointF(32, 52), QPointF(12, 42)])
    p.drawPolygon(poly_left)

    p.setBrush(QBrush(QColor(30, 136, 229, 170)))
    poly_right = QPolygonF([QPointF(32, 32), QPointF(52, 22), QPointF(52, 42), QPointF(32, 52)])
    p.drawPolygon(poly_right)

    p.setPen(QPen(QColor("#f37329"), 2.5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(32, 32, 32, 52)

    p.end()
    return QIcon(pix)


def make_view_front_icon() -> QIcon:
    """Draws Front Elevation symbol."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(QPen(QColor("#43a047"), 3, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(QBrush(QColor(67, 160, 71, 25)))
    p.drawRoundedRect(8, 8, 48, 48, 6, 6)

    p.setPen(QPen(QColor("#43a047"), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(10, 48, 54, 48)

    p.setPen(QPen(QColor("#43a047"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    facade = QPolygonF([
        QPointF(18, 48), QPointF(18, 30), QPointF(32, 20), QPointF(46, 30), QPointF(46, 48)
    ])
    p.drawPolyline(facade)

    p.end()
    return QIcon(pix)


def make_view_right_icon() -> QIcon:
    """Draws Right Elevation symbol."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(QPen(QColor("#fb8c00"), 3, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(QBrush(QColor(251, 140, 0, 25)))
    p.drawRoundedRect(8, 8, 48, 48, 6, 6)

    p.setPen(QPen(QColor("#fb8c00"), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(10, 48, 54, 48)

    p.setPen(QPen(QColor("#fb8c00"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    profile = QPolygonF([
        QPointF(18, 48), QPointF(18, 26), QPointF(36, 26), QPointF(46, 36), QPointF(46, 48)
    ])
    p.drawPolyline(profile)

    p.end()
    return QIcon(pix)


def make_zoom_all_icon(dark: bool = False) -> QIcon:
    """Draws Zoom Extents All symbol."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    pen_color = "#e0e0e0" if dark else "#2c3e50"
    p.setPen(QPen(QColor(pen_color), 3.5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(12, 22, 12, 12)
    p.drawLine(12, 12, 22, 12)
    p.drawLine(42, 12, 52, 12)
    p.drawLine(52, 12, 52, 22)
    p.drawLine(12, 42, 12, 52)
    p.drawLine(12, 52, 22, 52)
    p.drawLine(42, 52, 52, 52)
    p.drawLine(52, 52, 52, 42)

    p.setPen(QPen(QColor("#f37329"), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QBrush(QColor(243, 115, 41, 100)))
    poly_cube = QPolygonF([QPointF(32, 22), QPointF(42, 28), QPointF(32, 34), QPointF(22, 28)])
    p.drawPolygon(poly_cube)
    p.drawLine(32, 34, 32, 44)
    p.drawLine(22, 28, 22, 38)
    p.drawLine(42, 28, 42, 38)
    p.drawLine(22, 38, 32, 44)
    p.drawLine(42, 38, 32, 44)

    p.end()
    return QIcon(pix)


# ==============================================================================
# Global Event Filter for Double Space & Shortcut Detection
# ==============================================================================

class DoubleSpaceFilter(QObject):
    """
    Application-wide event filter to detect Double-Spacebar anywhere in IngeTrazo.
    When in MultiView layout, double-tapping Space enlarges the hovered/active viewport.
    Double-tapping Space again restores the 4-view layout.
    """

    def __init__(self, controller: MultiViewController):
        super().__init__()
        self.controller = controller
        self.last_space_time: float = 0.0

    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.KeyPress:
                # F4 toggle shortcut
                if event.key() == Qt.Key_F4 and not event.isAutoRepeat():
                    _log("F4 key detected in event filter!")
                    self.controller.toggle()
                    return True

                # Space key detection
                if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                    # Ignore if the user is typing inside a text input field (e.g., measurement VCB)
                    focus_w = QApplication.focusWidget()
                    if isinstance(focus_w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
                        return False
                    if isinstance(watched, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
                        return False

                    now = time.monotonic()
                    diff = now - self.last_space_time

                    if self.controller.is_active and self.controller.container is not None:
                        if diff < 0.45:
                            # Double-Space detected!
                            self.last_space_time = 0.0
                            _log(f"DOUBLE SPACE DETECTED! diff={diff:.3f}s. Toggling maximize.")

                            # Find target cell: hovered viewport, focused viewport, or current active
                            cursor_pos = QCursor.pos()
                            target = None
                            for cell in self.controller.container.all_cells:
                                if cell.isVisible() and cell.rect().contains(cell.mapFromGlobal(cursor_pos)):
                                    target = cell
                                    break

                            if target is None:
                                for cell in self.controller.container.all_cells:
                                    if cell.viewport.hasFocus() or cell.hasFocus():
                                        target = cell
                                        break

                            if target is None:
                                target = self.controller.container.get_target_cell()

                            self.controller.container.toggle_maximize(target)
                            return True  # Consume second Space

                    self.last_space_time = now
        except Exception:
            _log(f"Error in DoubleSpaceFilter: {traceback.format_exc()}")
        return False


# ==============================================================================
# Cell Header & Container Widgets (Theme-Adaptive)
# ==============================================================================

class QuadCellHeader(QFrame):
    """Clean CAD header bar for each viewport (Title, Menu, Maximize/Restore)."""

    def __init__(self, cell: QuadCell, title: str):
        super().__init__(cell)
        self.cell = cell
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        # Title button with dropdown menu
        self.title_btn = QPushButton(f"{title} ▾", self)
        self.title_btn.setCursor(Qt.PointingHandCursor)
        self._menu = QMenu(self)
        self._build_menu()
        self.title_btn.setMenu(self._menu)
        layout.addWidget(self.title_btn)

        layout.addStretch()

        # Maximize / Restore button in header
        self.btn_max = QPushButton("🗖", self)
        self.btn_max.setToolTip("Maximize / Restore (Double Space)")
        self.btn_max.setCursor(Qt.PointingHandCursor)
        self.btn_max.clicked.connect(lambda: self.cell.container.toggle_maximize(self.cell))
        layout.addWidget(self.btn_max)

        self.apply_theme(get_theme_colors(self))

    def apply_theme(self, colors: dict):
        """Applies dynamic light or dark theme styling."""
        self.setStyleSheet(f"""
            QuadCellHeader {{
                background-color: {colors["header_bg"]};
                border-bottom: 1px solid {colors["header_border"]};
            }}
        """)
        self.title_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {colors["header_text"]};
                font-weight: bold;
                font-size: 11px;
                padding: 2px 6px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {colors["header_btn_hover"]};
                border-radius: 2px;
                color: {colors["header_btn_hover_text"]};
            }}
        """)
        self._menu.setStyleSheet(f"""
            QMenu {{
                background-color: {colors["menu_bg"]};
                color: {colors["menu_text"]};
                border: 1px solid {colors["menu_border"]};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 5px 22px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: #f37329;
                color: #ffffff;
            }}
        """)
        self.btn_max.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {colors["max_btn"]};
                font-size: 12px;
                padding: 2px 5px;
            }}
            QPushButton:hover {{
                background-color: {colors["header_btn_hover"]};
                border-radius: 2px;
                color: {colors["header_btn_hover_text"]};
            }}
        """)

    def set_title(self, text: str):
        self.title_btn.setText(f"{text} ▾")

    def mouseDoubleClickEvent(self, event):
        """Double clicking cell header toggles maximize/restore."""
        if event.button() == Qt.LeftButton:
            self.cell.container.toggle_maximize(self.cell)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        self.cell.container.set_active_cell(self.cell)
        super().mousePressEvent(event)

    def _build_menu(self):
        views = [
            ("Top View", "top", False),
            ("Perspective", "iso", True),
            ("Front View", "front", False),
            ("Right View", "right", False),
            ("Isometric", "iso", True),
            ("Bottom View", "bottom", False),
            ("Back View", "back", False),
            ("Left View", "left", False),
        ]
        for name, key, persp in views:
            act = self._menu.addAction(name)
            act.triggered.connect(lambda _c=False, n=name, k=key, p=persp: self._apply_view(n, k, p))

        self._menu.addSeparator()
        act_max = self._menu.addAction("Enlarge / Restore Viewport (Double Space)")
        act_max.triggered.connect(lambda: self.cell.container.toggle_maximize(self.cell))

    def _apply_view(self, name: str, key: str, perspective: bool):
        vp = self.cell.viewport
        vp.camera.perspective = perspective
        vp.camera.set_view(key)
        vp.update()
        self.set_title(name.replace(" View", ""))
        if self.cell.container.controller.toolbar:
            self.cell.container.controller.update_toolbar_state()


class QuadCell(QFrame):
    """Wrapper frame containing the header bar and the Viewport."""

    def __init__(self, container: MultiViewContainer, title: str, viewport: Viewport, is_main: bool = False):
        super().__init__(container)
        self.container = container
        self.viewport = viewport
        self.is_main = is_main
        self.is_active = False
        self._colors = get_theme_colors(self)

        self.setFrameShape(QFrame.NoFrame)
        self.setLineWidth(0)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(50, 50)
        self.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewport.setMinimumSize(50, 50)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.header = QuadCellHeader(self, title)
        layout.addWidget(self.header)
        layout.addWidget(self.viewport, stretch=1)

        self.set_active(False)

        self.filter = ViewportInputFilter(self)
        self.viewport.installEventFilter(self.filter)
        self.installEventFilter(self.filter)

    def apply_theme(self, colors: dict):
        self._colors = colors
        self.header.apply_theme(colors)
        self.set_active(self.is_active)

    def _apply_view(self, name: str, key: str, perspective: bool):
        self.header._apply_view(name, key, perspective)

    def set_active(self, active: bool):
        self.is_active = active
        colors = self._colors or get_theme_colors(self)
        if active:
            # Active viewport gets IngeTrazo orange highlight border
            self.setStyleSheet(f"""
                QuadCell {{
                    border: 2px solid {colors["cell_border_active"]};
                    background-color: {colors["cell_bg"]};
                }}
            """)
        else:
            # Inactive border matches theme (light grey in light mode, dark grey in dark mode)
            self.setStyleSheet(f"""
                QuadCell {{
                    border: 1px solid {colors["cell_border_inactive"]};
                    background-color: {colors["cell_bg"]};
                }}
            """)


class ViewportInputFilter(QObject):
    """Filters mouse and focus events on individual viewports, ensuring pan and tools work everywhere."""

    def __init__(self, cell: QuadCell):
        super().__init__(cell)
        self.cell = cell
        self._middle_pan_active = False

    def eventFilter(self, watched, event):
        etype = event.type()
        if not self.cell.container.controller.is_active:
            return False
        vp = self.cell.viewport
        is_ortho = not getattr(vp.camera, "perspective", True)

        if etype == QEvent.Enter:
            self.cell.container.set_hovered_cell(self.cell)
            self._sync_tools()
        elif etype == QEvent.MouseButtonPress:
            self.cell.container.set_active_cell(self.cell)
            vp.setFocus()
            self._sync_tools()

        # Handle Middle-Button Pan in 2D Orthographic Views (Top, Front, Right)
        # Standard CAD convention: MMB pans directly in 2D without needing Shift.
        # Holding Ctrl or Alt allows 3D orbit instead.
        if is_ortho:
            if etype == QEvent.MouseButtonPress and event.button() == Qt.MiddleButton:
                mods = event.modifiers()
                if not (mods & (Qt.ControlModifier | Qt.AltModifier)):
                    self._middle_pan_active = True
                    vp._last_pos = event.position().toPoint()
                    vp._pan_mode = True
                    vp._pan_depth = None
                    from views.icons import tool_cursor
                    cur = tool_cursor("pan")
                    if cur is not None:
                        vp.setCursor(cur)
                    return True  # Consume press so Viewport doesn't overwrite _pan_mode

            elif etype == QEvent.MouseMove and self._middle_pan_active:
                if event.buttons() & Qt.MiddleButton:
                    p = event.position().toPoint()
                    if vp._last_pos is not None:
                        dx = p.x() - vp._last_pos.x()
                        dy = p.y() - vp._last_pos.y()
                        vp._last_pos = p
                        vp.camera.pan(dx, dy, vp.height())
                        vp.update()
                    return True
                else:
                    self._middle_pan_active = False
                    vp._last_pos = None
                    vp._pan_mode = False
                    vp.unsetCursor()
                    vp.update()

            elif etype == QEvent.MouseButtonRelease and event.button() == Qt.MiddleButton:
                if self._middle_pan_active:
                    self._middle_pan_active = False
                    vp._last_pos = None
                    vp._pan_mode = False
                    vp.unsetCursor()
                    vp.update()
                    return True

        return False

    def _sync_tools(self):
        """Keep tool, scene, undo history, and nav mode (Pan/Zoom/Orbit) in sync."""
        try:
            main_vp = self.cell.container.controller.main_vp
            vp = self.cell.viewport
            if vp is not main_vp:
                vp.scene = main_vp.scene
                vp.history = main_vp.history

                # Synchronize navigation mode (Pan tool / Orbit / Zoom)
                if vp.nav_mode != main_vp.nav_mode:
                    vp.set_nav_mode(main_vp.nav_mode)

                # Synchronize active drawing tool
                if main_vp.nav_mode is None and vp.active_tool != main_vp.active_tool:
                    vp.active_tool = main_vp.active_tool
        except Exception:
            pass


class MultiViewContainer(QWidget):
    """2x2 synchronized splitters container holding the 4 viewports."""

    def __init__(self, controller: MultiViewController):
        super().__init__(controller.window)
        self.controller = controller
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.is_maximized = False
        self.maximized_cell = None
        self.active_cell = None
        self.hovered_cell = None
        self._syncing_splitters = False
        self.two_views = False

        self._saved_main_sizes = [500, 500]
        self._saved_top_sizes = [500, 500]
        self._saved_bottom_sizes = [500, 500]

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Vertical splitter (top vs bottom row)
        self.main_splitter = QSplitter(Qt.Vertical, self)
        self.main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_splitter.setHandleWidth(4)

        # Top row: Top View + Perspective
        self.top_splitter = QSplitter(Qt.Horizontal, self.main_splitter)
        self.top_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.top_splitter.setHandleWidth(4)

        # Bottom row: Front View + Right View
        self.bottom_splitter = QSplitter(Qt.Horizontal, self.main_splitter)
        self.bottom_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bottom_splitter.setHandleWidth(4)

        # Cells
        self.cell_top = QuadCell(self, "Top", self.controller.top_vp)
        self.cell_persp = QuadCell(self, "Perspective", self.controller.main_vp, is_main=True)
        self.cell_front = QuadCell(self, "Front", self.controller.front_vp)
        self.cell_right = QuadCell(self, "Right", self.controller.right_vp)

        self.all_cells = [self.cell_top, self.cell_persp, self.cell_front, self.cell_right]

        self.top_splitter.addWidget(self.cell_top)
        self.top_splitter.addWidget(self.cell_persp)
        self.top_splitter.setStretchFactor(0, 1)
        self.top_splitter.setStretchFactor(1, 1)

        self.bottom_splitter.addWidget(self.cell_front)
        self.bottom_splitter.addWidget(self.cell_right)
        self.bottom_splitter.setStretchFactor(0, 1)
        self.bottom_splitter.setStretchFactor(1, 1)

        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.main_splitter, 1)

        # Synchronize horizontal splitters (4-way cross-junction feel)
        self.top_splitter.splitterMoved.connect(self._on_top_splitter_moved)
        self.bottom_splitter.splitterMoved.connect(self._on_bottom_splitter_moved)

        self.apply_theme()
        self.set_active_cell(self.cell_persp)

    def apply_theme(self):
        """Applies dynamic Light or Dark theme styling to splitters and cells."""
        colors = get_theme_colors(self.window())
        splitter_css = f"""
            QSplitter::handle {{
                background-color: {colors["splitter_handle"]};
            }}
            QSplitter::handle:hover {{
                background-color: {colors["splitter_handle_hover"]};
            }}
        """
        self.main_splitter.setStyleSheet(splitter_css)
        self.top_splitter.setStyleSheet(splitter_css)
        self.bottom_splitter.setStyleSheet(splitter_css)

        self.setStyleSheet(f"MultiViewContainer {{ background-color: {colors['container_bg']}; }}")

        for c in self.all_cells:
            c.apply_theme(colors)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.ThemeChange):
            self.apply_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.controller._reposition_sidebar_handle()

    def _on_top_splitter_moved(self, pos: int, index: int):
        if not self._syncing_splitters and not self.is_maximized:
            self._syncing_splitters = True
            self.bottom_splitter.setSizes(self.top_splitter.sizes())
            self._syncing_splitters = False

    def _on_bottom_splitter_moved(self, pos: int, index: int):
        if not self._syncing_splitters and not self.is_maximized:
            self._syncing_splitters = True
            self.top_splitter.setSizes(self.bottom_splitter.sizes())
            self._syncing_splitters = False

    def set_active_cell(self, cell: QuadCell):
        self.active_cell = cell
        for c in self.all_cells:
            c.set_active(c is cell)
        if self.controller.toolbar:
            self.controller.update_toolbar_state()

    def set_hovered_cell(self, cell: QuadCell):
        self.hovered_cell = cell

    def get_target_cell(self) -> QuadCell:
        if self.is_maximized and self.maximized_cell is not None:
            return self.maximized_cell
        if self.hovered_cell and self.hovered_cell.isVisible():
            return self.hovered_cell
        if self.active_cell and self.active_cell.isVisible():
            return self.active_cell
        return self.cell_persp

    def set_two_views(self, enabled):
        if self.is_maximized:
            self.toggle_maximize()
        self.two_views = bool(enabled)
        self.bottom_splitter.setVisible(not self.two_views)
        if self.two_views:
            self.hovered_cell = None
            self.set_active_cell(self.cell_persp)
        self.update_all_viewports()
        self.controller.update_toolbar_state()

    def toggle_maximize(self, target_cell=None):
        if self.is_maximized:
            # Restore 4-viewport layout
            self.top_splitter.show()
            self.bottom_splitter.setVisible(not self.two_views)
            for c in self.all_cells:
                c.show()
                c.header.btn_max.setText("🗖")
                c.header.btn_max.setToolTip("Maximize (Double Space)")

            self.main_splitter.setSizes(self._saved_main_sizes)
            self.top_splitter.setSizes(self._saved_top_sizes)
            self.bottom_splitter.setSizes(self._saved_bottom_sizes)

            self.is_maximized = False
            self.maximized_cell = None

            self.controller.main_vp.flash_status("MultiView layout restored", 2000)
        else:
            if target_cell is None:
                target_cell = self.get_target_cell()

            self._saved_main_sizes = self.main_splitter.sizes()
            self._saved_top_sizes = self.top_splitter.sizes()
            self._saved_bottom_sizes = self.bottom_splitter.sizes()

            self.is_maximized = True
            self.maximized_cell = target_cell

            # Hide non-selected cells and splitters
            for c in self.all_cells:
                if c is not target_cell:
                    c.hide()
                else:
                    c.show()

            if target_cell in (self.cell_top, self.cell_persp):
                self.bottom_splitter.hide()
                self.top_splitter.show()
            else:
                self.top_splitter.hide()
                self.bottom_splitter.show()

            target_cell.header.btn_max.setText("🗗")
            target_cell.header.btn_max.setToolTip("Restore 4 Views (Double Space)")
            self.set_active_cell(target_cell)

            title = target_cell.header.title_btn.text().replace(" ▾", "")
            self.controller.main_vp.flash_status(
                f"{title} maximized (Double Space / Click to restore)",
                2500
            )

        self.update_all_viewports()
        if self.controller.toolbar:
            self.controller.update_toolbar_state()

    def update_all_viewports(self):
        for c in self.all_cells:
            if c.isVisible():
                c.viewport.update()


# ==============================================================================
# IngeTrazo MultiView Controller with Native QToolBar
# ==============================================================================

class MultiViewController(QObject):
    """Manages the IngeTrazo MultiView 4-viewport system, native QToolBar, and Double Space."""

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.window = app.window
        self.main_vp = app.viewport
        self.is_active = False

        self.top_vp = None
        self.front_vp = None
        self.right_vp = None
        self.container = None

        # Build native dockable and floatable QToolBar
        self.toolbar = None
        self.act_toggle = None
        self.act_max = None
        self.act_top = None
        self.act_persp = None
        self.act_front = None
        self.act_right = None
        self.act_zoom_all = None

        self._build_native_toolbar()

        # Hook set_nav_mode so Pan tool, Orbit, and Zoom synchronize across all viewports
        self._hook_nav_mode()

        # Global event filter for Double-Space, F4, and Theme Changes
        self._space_filter = DoubleSpaceFilter(self)
        QCoreApplication.instance().installEventFilter(self._space_filter)
        _log("DoubleSpaceFilter installed globally on QCoreApplication.")

        # Window event filter to catch runtime theme changes
        self.window.installEventFilter(self)

        try:
            self.app.on_document_changed(self._on_doc_changed)
        except Exception:
            _log(f"Failed to hook on_document_changed: {traceback.format_exc()}")

    def eventFilter(self, watched, event):
        """Catches runtime theme / palette flips in IngeTrazo."""
        if watched is self.window and event.type() in (
            QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.ThemeChange
        ):
            _log("Theme change event detected! Refreshing theme styles...")
            if self.container is not None:
                self.container.apply_theme()
            self.update_toolbar_state()
        return False

    def _hook_nav_mode(self):
        """Broadcasts set_nav_mode (Pan, Orbit, Zoom) to all viewports when selected from toolbars/menus."""
        try:
            orig_set_nav_mode = self.main_vp.set_nav_mode
            def synced_set_nav_mode(mode: str | None):
                orig_set_nav_mode(mode)
                if self.is_active and self.container is not None:
                    for c in self.container.all_cells:
                        if c.viewport is not self.main_vp:
                            c.viewport.set_nav_mode(mode)
            self.main_vp.set_nav_mode = synced_set_nav_mode
            _log("Successfully hooked main_vp.set_nav_mode for universal Pan/Nav sync.")
        except Exception:
            _log(f"Failed to hook nav mode: {traceback.format_exc()}")

    def _build_native_toolbar(self):
        """Constructs a native Qt QToolBar that docks at the top and floats natively."""
        _log(f"Building native {DISPLAY_NAME} QToolBar...")
        self.toolbar = QToolBar(DISPLAY_NAME, self.window)
        self.toolbar.setObjectName(TOOLBAR_NAME)
        self.toolbar.setMovable(True)
        self.toolbar.setFloatable(True)
        self.toolbar.setAllowedAreas(Qt.AllToolBarAreas)

        from views.icons import toolbar_icon_px, style_overflow_button
        try:
            px = toolbar_icon_px()
        except Exception:
            px = 28
        self.toolbar.setIconSize(QSize(px, px))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar.setToolTip("Drag dotted grip to float or dock this toolbar.")

        dark = is_dark_ui(self.window)

        # 1. Toggle MultiView (Checkable)
        self.act_toggle = QAction(make_quad_icon(False, dark), f"{DISPLAY_NAME} (F4)", self.window)
        self.act_toggle.setCheckable(True)
        self.act_toggle.setChecked(False)
        self.act_toggle.setToolTip(f"{DISPLAY_NAME} (F4)\nToggle between 4-Viewport layout (Top, Persp, Front, Right) and Single View")
        self.act_toggle.setStatusTip("Toggle between 4-Viewport layout (Top, Persp, Front, Right) and Single View")
        self.act_toggle.triggered.connect(self.toggle)
        self.toolbar.addAction(self.act_toggle)

        self.act_two = QAction(make_quad_icon(False, dark, two=True), "2 Views", self.window)
        self.act_two.setCheckable(True)
        self.act_two.setToolTip("Two views side by side; click again for four views")
        self.act_two.triggered.connect(self.toggle_two_views)
        self.toolbar.addAction(self.act_two)

        # 2. Enlarge / Restore Active Viewport (Double Space)
        self.act_max = QAction(make_max_restore_icon(False, dark), "Enlarge / Restore (Double Space)", self.window)
        self.act_max.setEnabled(False)
        self.act_max.setToolTip("Enlarge / Restore Viewport (Double Space)\nMaximize active viewport to 100% or restore 4 views")
        self.act_max.setStatusTip("Maximize active viewport to 100% or restore 4 views")
        self.act_max.triggered.connect(lambda: self.toggle_maximize())
        self.toolbar.addAction(self.act_max)

        self.toolbar.addSeparator()

        # 3. Top View
        self.act_top = QAction(make_view_top_icon(), "Top View", self.window)
        self.act_top.setToolTip("Top View (Plan)\nSwitch active viewport camera to Top view")
        self.act_top.setStatusTip("Switch active viewport camera to Top view")
        self.act_top.triggered.connect(lambda: self.apply_preset_view("top", perspective=False))
        self.toolbar.addAction(self.act_top)

        # 4. Perspective View
        self.act_persp = QAction(make_view_persp_icon(), "Perspective View", self.window)
        self.act_persp.setToolTip("Perspective View (3D)\nSwitch active viewport camera to 3D Perspective")
        self.act_persp.setStatusTip("Switch active viewport camera to 3D Perspective")
        self.act_persp.triggered.connect(lambda: self.apply_preset_view("iso", perspective=True))
        self.toolbar.addAction(self.act_persp)

        # 5. Front View
        self.act_front = QAction(make_view_front_icon(), "Front View", self.window)
        self.act_front.setToolTip("Front View (Elevation)\nSwitch active viewport camera to Front view")
        self.act_front.setStatusTip("Switch active viewport camera to Front view")
        self.act_front.triggered.connect(lambda: self.apply_preset_view("front", perspective=False))
        self.toolbar.addAction(self.act_front)

        # 6. Right View
        self.act_right = QAction(make_view_right_icon(), "Right View", self.window)
        self.act_right.setToolTip("Right View (Elevation)\nSwitch active viewport camera to Right view")
        self.act_right.setStatusTip("Switch active viewport camera to Right view")
        self.act_right.triggered.connect(lambda: self.apply_preset_view("right", perspective=False))
        self.toolbar.addAction(self.act_right)

        self.toolbar.addSeparator()

        # 7. Zoom Extents All
        self.act_zoom_all = QAction(make_zoom_all_icon(dark), "Zoom Extents (All)", self.window)
        self.act_zoom_all.setToolTip("Zoom Extents (All Viewports)\nFrame geometry across all viewports")
        self.act_zoom_all.setStatusTip("Frame geometry across all viewports")
        self.act_zoom_all.triggered.connect(self.zoom_extents_all)
        self.toolbar.addAction(self.act_zoom_all)

        # Dock into IngeTrazo's top toolbar area
        self.window.addToolBar(Qt.TopToolBarArea, self.toolbar)
        try:
            style_overflow_button(self.toolbar)
        except Exception:
            pass

        _log(f"Native {DISPLAY_NAME} QToolBar docked successfully.")

    def _reposition_sidebar_handle(self):
        """Keep the sidebar handle at the right edge of the central container."""
        try:
            btn = getattr(self.window, "_sidebar_handle", None)
            if btn is not None and self.is_active and self.container is not None:
                edge_x = self.container.width()
                x = edge_x - btn.width() // 2
                x = max(0, min(x, self.window.width() - btn.width()))
                y = (self.container.height() - btn.height()) // 2
                btn.move(x, max(0, y))
                btn.raise_()
        except Exception:
            pass

    def update_toolbar_state(self):
        """Updates toolbar icons, checked state, and tooltips."""
        if not self.toolbar:
            return

        dark = is_dark_ui(self.window)
        self.act_toggle.setChecked(self.is_active)
        self.act_two.setChecked(bool(self.is_active and self.container and self.container.two_views))
        self.act_two.setIcon(make_quad_icon(self.act_two.isChecked(), dark, two=True))
        self.act_toggle.setIcon(make_quad_icon(self.is_active, dark))
        self.act_zoom_all.setIcon(make_zoom_all_icon(dark))

        if self.is_active:
            self.act_max.setEnabled(True)
            is_max = self.container.is_maximized if self.container else False
            self.act_max.setIcon(make_max_restore_icon(is_max, dark))
            if is_max:
                self.act_max.setToolTip("Restore layout (Double Space)")
            else:
                self.act_max.setToolTip("Enlarge Viewport (Double Space)")
        else:
            self.act_max.setEnabled(False)
            self.act_max.setIcon(make_max_restore_icon(False, dark))

    def toggle_two_views(self, checked):
        if not self.is_active:
            self.activate()
        if self.is_active and self.container:
            self.container.set_two_views(checked)

    def toggle_maximize(self):
        """Toggles maximize/restore of the active/hovered cell."""
        if self.is_active and self.container is not None:
            self.container.toggle_maximize()
            self.update_toolbar_state()

    def apply_preset_view(self, view_key: str, perspective: bool):
        """Applies a camera view preset to the active viewport (or main viewport if single view)."""
        _log(f"Applying preset view: {view_key}, perspective={perspective}")
        if self.is_active and self.container is not None:
            cell = self.container.get_target_cell()
            names = {
                "top": "Top",
                "iso": "Perspective" if perspective else "Isometric",
                "front": "Front",
                "right": "Right",
            }
            name = names.get(view_key, view_key.capitalize())
            cell._apply_view(name, view_key, perspective)
        else:
            vp = self.main_vp
            vp.camera.perspective = perspective
            vp.camera.set_view(view_key)
            vp.update()

    def zoom_extents_all(self):
        """Frames geometry across all active viewports."""
        _log("Zoom Extents All triggered.")
        try:
            bounds = self.main_vp.scene.bounds()
            figs = getattr(self.window, "_figure_bounds", lambda: None)()
            if figs is not None:
                lo, hi = figs
                if bounds[0] is not None:
                    lo = QVector3D(min(lo.x(), bounds[0].x()), min(lo.y(), bounds[0].y()), min(lo.z(), bounds[0].z()))
                    hi = QVector3D(max(hi.x(), bounds[1].x()), max(hi.y(), bounds[1].y()), max(hi.z(), bounds[1].z()))
                bounds = (lo, hi)

            if bounds[0] is not None:
                targets = [self.main_vp]
                if self.is_active and self.container is not None:
                    targets = [c.viewport for c in self.container.all_cells if c.isVisible()]
                for vp in targets:
                    if hasattr(vp.camera, "fit_box"):
                        vp.camera.fit_box(bounds[0], bounds[1])
                    vp.update()
        except Exception:
            _log(f"Error in zoom_extents_all: {traceback.format_exc()}")

    def _create_secondary_viewport(self, view_name: str, perspective: bool) -> Viewport:
        """Instantiates a secondary Viewport sharing the main scene and undo history."""
        _log(f"Creating secondary viewport: {view_name} (perspective={perspective})")
        vp = Viewport(self.window)
        vp.scene = self.main_vp.scene
        vp.history = self.main_vp.history
        # Viewport construction binds units to its temporary empty document.
        from core import units
        units.bind_scene(self.main_vp.scene)
        vp.active_tool = self.main_vp.active_tool
        vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vp.setMinimumSize(50, 50)

        # Sync nav mode if main viewport is currently in pan/zoom/orbit mode
        if self.main_vp.nav_mode is not None:
            vp.set_nav_mode(self.main_vp.nav_mode)

        # Sync edit rest mode safely
        if hasattr(self.main_vp, "_edit_rest_mode") and hasattr(vp, "set_edit_rest_mode"):
            try:
                vp.set_edit_rest_mode(self.main_vp.edit_rest_mode)
            except Exception:
                pass

        # Configure Camera
        vp.camera.perspective = perspective
        vp.camera.set_view(view_name)
        vp.camera.target = QVector3D(self.main_vp.camera.target)
        vp.camera.distance = max(self.main_vp.camera.distance, 15.0)

        # Connect scene version signal
        vp.sceneVersionChanged.connect(lambda _v: self._on_sub_version_changed(vp))
        return vp

    def _on_doc_changed(self):
        """Called whenever the document changes in IngeTrazo."""
        for vp in (self.top_vp, self.front_vp, self.right_vp):
            if vp is not None and (vp.scene is not self.main_vp.scene or
                                   vp.history is not self.main_vp.history):
                vp.reset_document_caches()
                vp.scene, vp.history = self.main_vp.scene, self.main_vp.history
                vp._edges_version = -1
                vp.last_snap = None
        if self.is_active and self.container is not None:
            self.container.update_all_viewports()

    def _on_sub_version_changed(self, sender_vp: Viewport):
        """Called if a tool in a secondary viewport modifies the scene."""
        if not self.is_active:
            return
        if self.main_vp is not None:
            self.main_vp.update()
        for vp in (self.top_vp, self.front_vp, self.right_vp):
            if vp is not None and vp is not sender_vp:
                vp.update()

    def toggle(self):
        """Toggles between single viewport and MultiView 4-viewport layout."""
        _log(f"Toggling MultiView. Currently is_active={self.is_active}")
        try:
            if self.is_active:
                self.deactivate()
            else:
                self.activate()
        except Exception as e:
            _log(f"ERROR in toggle:\n{traceback.format_exc()}")

    def _prepare_viewport_move(self, vp):
        """Invalidate uploads while the old GL context is still valid.

        Qt may recreate a QOpenGLWidget context when its parent changes.
        The host rebuilds buffers, but retains the CPU 'already uploaded'
        cache. Identical geometry would then skip uploading into new buffers.
        This changes render caches only; no geometry or history is changed.
        """
        vp.reset_document_caches()
        vp._vbo_parts.clear()
        vp._edges_version = -1
        if vp.isValid():
            vp.makeCurrent()
            try:
                vp._scene_fbo = None
            finally:
                vp.doneCurrent()

    def activate(self):
        if self.is_active:
            return
        if self.window.centralWidget() is not self.main_vp:
            self.main_vp.flash_status("Close the current extension workspace before enabling MultiView", 4000)
            return
        _log(f"Activating {DISPLAY_NAME}...")

        if self.top_vp is None:
            self.top_vp = self._create_secondary_viewport("top", perspective=False)
            self.front_vp = self._create_secondary_viewport("front", perspective=False)
            self.right_vp = self._create_secondary_viewport("right", perspective=False)

        for vp in (self.main_vp, self.top_vp, self.front_vp, self.right_vp):
            self._prepare_viewport_move(vp)

        # Safely detach main viewport without destroying it
        _log(f"Detaching central widget: {self.window.centralWidget()}")
        if hasattr(self.window, "takeCentralWidget"):
            old_cw = self.window.takeCentralWidget()
            _log(f"takeCentralWidget succeeded: {old_cw}")
        else:
            win_layout = self.window.layout()
            if win_layout is not None and self.window.centralWidget() is self.main_vp:
                win_layout.removeWidget(self.main_vp)
            self.main_vp.setParent(None)

        self.main_vp.setMinimumSize(50, 50)
        self.main_vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Reuse one container and its event filters across toggle cycles.
        # Rebuilding left old cells/filters referring to reparented viewports.
        first_open = self.container is None
        if first_open:
            self.container = MultiViewContainer(self)
        else:
            self.container.cell_persp.layout().addWidget(self.main_vp, stretch=1)
        self.window.setCentralWidget(self.container)
        self.container.show()
        self.main_vp.show()
        _log(f"Central widget successfully set to container: {self.window.centralWidget()}")

        self.is_active = True
        self.main_vp.flash_status(f"{DISPLAY_NAME}: Top, Persp, Front, Right (Double Space / F4)", 3500)
        _log(f"{DISPLAY_NAME} successfully activated!")

        # Equal 50/50 initial split
        if first_open:
            QTimer.singleShot(50, self._initial_split_balance)
        self.update_toolbar_state()
        self._reposition_sidebar_handle()

    def _initial_split_balance(self):
        if self.is_active and self.container:
            w = self.container.width()
            h = self.container.height()
            _log(f"_initial_split_balance with container dimensions: {w}x{h}")
            if w > 100 and h > 100:
                self.container.main_splitter.setSizes([h // 2, h // 2])
                self.container.top_splitter.setSizes([w // 2, w // 2])
                self.container.bottom_splitter.setSizes([w // 2, w // 2])
            self.container.update_all_viewports()
        self._reposition_sidebar_handle()

    def deactivate(self):
        if not self.is_active:
            return
        _log(f"Deactivating {DISPLAY_NAME}...")

        for vp in (self.main_vp, self.top_vp, self.front_vp, self.right_vp):
            self._prepare_viewport_move(vp)

        if self.container:
            if self.container.is_maximized:
                self.container.toggle_maximize()

            # Detach self.main_vp from cell_persp layout before restoring
            if hasattr(self.container, "cell_persp") and self.container.cell_persp.layout():
                self.container.cell_persp.layout().removeWidget(self.main_vp)
            self.container.hide()
            self.main_vp.setParent(self.window)

            if hasattr(self.window, "takeCentralWidget"):
                self.window.takeCentralWidget()
            else:
                win_layout = self.window.layout()
                if win_layout is not None and self.window.centralWidget() is self.container:
                    win_layout.removeWidget(self.container)
            # Park the inactive container as a hidden child, never as an orphan
            # top-level window. Qt owns it until the main window is destroyed.
            self.container.setParent(self.window)
            self.container.hide()

        self.main_vp.setMinimumSize(640, 480)
        self.main_vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.window.setCentralWidget(self.main_vp)
        self.main_vp.show()
        self.main_vp.update()

        self.is_active = False
        self.main_vp.flash_status("Single Viewport restored", 2000)
        _log("Single Viewport successfully restored.")
        self.update_toolbar_state()

        if hasattr(self.window, "_place_sidebar_handle"):
            self.window._place_sidebar_handle()


# ==============================================================================
# Plugin Entry Point
# ==============================================================================

_multiview_controller: MultiViewController | None = None

def setup(app) -> None:
    """Plugin entry point called by IngeTrazo when the main window is created."""
    global _multiview_controller
    _log(f"=== Loading {KEY}.py with Theme-Adaptive UI & Native QToolBar ===")
    try:
        _multiview_controller = MultiViewController(app)

        # Register Extensions menu actions
        menu = app.add_menu(DISPLAY_NAME)
        if menu is not None:
            act_tog = menu.addAction("Toggle MultiView (F4)", _multiview_controller.toggle)
            act_tog.setStatusTip("Toggle between 4-Viewport layout and Single Viewport (F4)")

            act_m = menu.addAction("Enlarge / Restore Viewport (Double Space)", _multiview_controller.toggle_maximize)
            act_m.setStatusTip("Maximize active viewport to 100% or restore 4 views (Double Space)")

            act_z = menu.addAction("Zoom Extents All", _multiview_controller.zoom_extents_all)
            act_z.setStatusTip("Frame geometry across all viewports")

            menu.addSeparator()
            menu.addAction("Top View (Plan)", lambda: _multiview_controller.apply_preset_view("top", perspective=False))
            menu.addAction("Perspective View (3D)", lambda: _multiview_controller.apply_preset_view("iso", perspective=True))
            menu.addAction("Front View (Elevation)", lambda: _multiview_controller.apply_preset_view("front", perspective=False))
            menu.addAction("Right View (Elevation)", lambda: _multiview_controller.apply_preset_view("right", perspective=False))

            menu.addSeparator()
            toggle_tb = _multiview_controller.toolbar.toggleViewAction()
            toggle_tb.setText(f"Show {DISPLAY_NAME} Toolbar")
            menu.addAction(toggle_tb)

        _log("setup(app) completed successfully.")
    except Exception as e:
        _log(f"CRITICAL ERROR in setup(app):\n{traceback.format_exc()}")
        raise
