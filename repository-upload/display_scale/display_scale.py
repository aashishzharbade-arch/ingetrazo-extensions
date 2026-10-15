# SPDX-License-Identifier: GPL-3.0-or-later
"""Display Scale v1.2 - choose how much working space IngeTrazo gives you.

On a 1080p screen you can make IngeTrazo lay itself out as if the screen were
2K (2560 px) or 4K (3840 px): the interface gets smaller, so the viewport
and the side tray have more room. On a 4K screen you can go the other way
and make everything larger. Icons and text have their own multipliers, so
you can keep icons big while still gaining space.

Install: copy this file to your IngeTrazo plugins folder
(Extensions > Open plugins folder) and restart IngeTrazo.

Toolbar: a monitor icon opens Display Scale settings. Drag the toolbar grip
to dock it beside your other plugin icons or float it. Toggle its visibility
from Extensions > Display Scale: Toolbar or the toolbar context menu.

Extensions menu
  * Display Scale...                 the dialog (presets 720p / 1080p / 2K / 4K,
                                     custom %, icon size, text size)
  * Display Scale: Smaller (more space) / Larger     quick 10 % steps
  * Focus Mode (hide panels)         toggle: hides every side panel for a
                                     maximum viewport, press again to restore

Two ways to apply a scale
  * Apply now (live): scales the application font and the icon / button
    sizes of the running program. Instant, no restart, approximate - widgets
    with fixed pixel sizes keep them. It is re-applied automatically at
    every start (option in the dialog).
  * Restart at true scale: relaunches IngeTrazo with Qt's own scale factor
    (QT_SCALE_FACTOR), which scales EVERYTHING uniformly, the 3D viewport
    included. Your open document gets the normal "save changes?" question
    first. To make a true scale permanent, set QT_SCALE_FACTOR in your
    launcher - the dialog shows the command for your system.
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QDockWidget,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QTabBar, QToolBar, QToolButton,
                               QVBoxLayout, QWidget)

from tools.base import Tool

__version__ = "1.2.0"

AUTO_APPLY_AT_STARTUP = True      # default for the dialog checkbox
SCALE_MIN, SCALE_MAX = 0.40, 3.00
_ICON_TYPES = (QToolBar, QToolButton, QTabBar, QAbstractItemView)
_PRESETS = [                        # label, virtual workspace width (px)
    ("1280 \u00d7 720  (HD)", 1280),
    ("1920 \u00d7 1080  (Full HD)", 1920),
    ("2560 \u00d7 1440  (2K / QHD)", 2560),
    ("3840 \u00d7 2160  (4K / UHD)", 3840),
]


# --------------------------------------------------------------------------
# Settings + screen maths
# --------------------------------------------------------------------------
def _qs() -> QSettings:
    return QSettings("ingetrazo-plugins", "display_scale")


def _getf(key, default):
    try:
        return float(_qs().value(key, default))
    except (TypeError, ValueError):
        return float(default)


def _true_factor() -> float:
    """QT_SCALE_FACTOR the process runs with (1.0 when unset)."""
    try:
        return float(os.environ.get("QT_SCALE_FACTOR", "1") or 1)
    except ValueError:
        return 1.0


def _true_active() -> bool:
    return abs(_true_factor() - 1.0) > 1e-3


def screen_info(win=None):
    """(physical_w, physical_h, os_dpr) of the screen the window is on."""
    scr = None
    try:
        scr = win.screen() if win is not None else None
    except Exception:  # noqa: BLE001
        scr = None
    scr = scr or QGuiApplication.primaryScreen()
    dpr = scr.devicePixelRatio()
    size = scr.size()
    return (round(size.width() * dpr), round(size.height() * dpr),
            dpr / _true_factor())


def scale_for_workspace(virtual_w, phys_w, os_dpr) -> float:
    """UI scale that makes the screen lay out like a virtual_w-px-wide one."""
    return max(SCALE_MIN, min(SCALE_MAX, phys_w / (virtual_w * os_dpr)))


def workspace_for_scale(scale, phys_w, phys_h, os_dpr):
    return (round(phys_w / (os_dpr * scale)), round(phys_h / (os_dpr * scale)))


# --------------------------------------------------------------------------
# Live scaling
# --------------------------------------------------------------------------
class _Live(QObject):
    """Holds the base values and applies the multipliers."""

    def __init__(self):
        super().__init__()
        self.base_font: QFont | None = None
        self.scale = self.icon = self.text = 1.0
        self.active = False
        self.installed = False

    # factors actually used by the live layer
    @property
    def ui_f(self) -> float:
        return 1.0 if _true_active() else self.scale

    def apply(self, scale: float, icon: float, text: float):
        app = QApplication.instance()
        if app is None:
            return
        if self.base_font is None:
            self.base_font = QFont(app.font())
        self.scale = max(SCALE_MIN, min(SCALE_MAX, scale))
        self.icon, self.text = icon, text
        self.active = True
        if not self.installed:
            app.installEventFilter(self)
            self.installed = True
        self._apply_font(app)
        for w in app.allWidgets():
            self._apply_widget(w)

    def reset(self):
        self.apply(1.0, 1.0, 1.0)
        self.active = False

    def _apply_font(self, app):
        f = QFont(self.base_font)
        k = self.ui_f * self.text
        if f.pointSizeF() > 0:
            f.setPointSizeF(max(5.0, f.pointSizeF() * k))
        elif f.pixelSize() > 0:
            f.setPixelSize(max(6, round(f.pixelSize() * k)))
        app.setFont(f)

    def _apply_widget(self, w):
        if not isinstance(w, _ICON_TYPES):
            return
        k = self.ui_f * self.icon
        try:
            base = w.property("_dsBase")
            if base is None:
                sz = w.iconSize()
                if not sz.isValid() or sz.width() <= 0:
                    return
                base = [sz.width(), sz.height()]
                w.setProperty("_dsBase", base)
            w.setIconSize(QSize(max(8, round(base[0] * k)),
                                max(8, round(base[1] * k))))
            if isinstance(w, QToolButton) and not isinstance(w.parent(), QToolBar):
                fixed = w.property("_dsFixed")
                if fixed is None and w.minimumSize() == w.maximumSize() \
                        and 0 < w.maximumSize().width() <= 160:
                    fixed = [w.maximumSize().width(), w.maximumSize().height()]
                    w.setProperty("_dsFixed", fixed)
                if fixed:
                    w.setFixedSize(round(fixed[0] * k), round(fixed[1] * k))
        except RuntimeError:        # widget already deleted
            pass

    def eventFilter(self, obj, ev):
        if self.active and ev.type() == QEvent.Show and isinstance(obj, _ICON_TYPES):
            self._apply_widget(obj)
        return False


LIVE = _Live()


def apply_saved(win=None):
    LIVE.apply(_getf("scale", 1.0), _getf("icon", 1.0), _getf("text", 1.0))


# --------------------------------------------------------------------------
# True scale: restart with QT_SCALE_FACTOR
# --------------------------------------------------------------------------
def restart_command(scale: float):
    args = [a for a in sys.argv if a != "--new-window"]
    if getattr(sys, "frozen", False):
        cmd = [sys.executable] + args[1:]
    else:
        cmd = [sys.executable, os.path.abspath(args[0])] + args[1:]
    cmd.append("--new-window")          # skip IngeTrazo's single-instance hand-over
    env = dict(os.environ)
    if abs(scale - 1.0) < 1e-3:
        env.pop("QT_SCALE_FACTOR", None)
    else:
        env["QT_SCALE_FACTOR"] = f"{scale:.4f}"
    return cmd, env


def restart_at_scale(win, scale: float) -> bool:
    cmd, env = restart_command(scale)
    ok = QMessageBox.question(
        win, "Restart at true scale",
        f"IngeTrazo will restart with a UI scale of {round(scale * 100)} %.\n"
        "You will be asked to save any unsaved changes first.\n\nContinue?")
    if ok != QMessageBox.Yes:
        return False
    if not win.close():                  # user cancelled "save changes?"
        return False
    try:
        kwargs = {"env": env, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        QMessageBox.warning(None, "Display Scale",
                            f"Could not restart IngeTrazo:\n{exc}")
    return True


def permanent_command(scale: float) -> str:
    v = f"{scale:.2f}"
    if sys.platform.startswith("win"):
        return f"setx QT_SCALE_FACTOR {v}"
    if sys.platform == "darwin":
        return f"launchctl setenv QT_SCALE_FACTOR {v}"
    if os.environ.get("FLATPAK_ID"):
        return (f"flatpak override --user --env=QT_SCALE_FACTOR={v} "
                f"{os.environ['FLATPAK_ID']}")
    return f"QT_SCALE_FACTOR={v} ./IngeTrazo-*.AppImage"


# --------------------------------------------------------------------------
# Focus mode (hide every side panel)
# --------------------------------------------------------------------------
_focus = {"hidden": []}


def toggle_focus(win) -> bool:
    """Returns True when focus mode is now ON."""
    if _focus["hidden"]:
        for d in _focus["hidden"]:
            try:
                d.show()
            except RuntimeError:
                pass
        _focus["hidden"] = []
        return False
    docks = [d for d in win.findChildren(QDockWidget) if d.isVisible()]
    for d in docks:
        d.hide()
    _focus["hidden"] = docks
    return bool(docks)


# --------------------------------------------------------------------------
# Dialog
# --------------------------------------------------------------------------
class _Dialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Display Scale")
        self.setMinimumWidth(560)
        self.phys_w, self.phys_h, self.os_dpr = screen_info(win)
        lay = QVBoxLayout(self)

        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        form = QFormLayout()
        self.preset = QComboBox()
        self.preset.addItem("Keep my current size (100 %)", 0)
        for label, w in _PRESETS:
            self.preset.addItem(label, w)
        self.preset.addItem("Custom", -1)
        form.addRow("Work space like a screen of", self.preset)

        self.pct = QDoubleSpinBox()
        self.pct.setRange(SCALE_MIN * 100, SCALE_MAX * 100)
        self.pct.setDecimals(0)
        self.pct.setSingleStep(5)
        self.pct.setSuffix(" %")
        self.pct.setValue(_getf("scale", 1.0) * 100)
        form.addRow("Interface scale", self.pct)

        self.icon = QDoubleSpinBox()
        self.icon.setRange(0.5, 3.0)
        self.icon.setSingleStep(0.1)
        self.icon.setPrefix("\u00d7 ")
        self.icon.setValue(_getf("icon", 1.0))
        form.addRow("Toolbar icon size", self.icon)

        self.text = QDoubleSpinBox()
        self.text.setRange(0.6, 2.5)
        self.text.setSingleStep(0.1)
        self.text.setPrefix("\u00d7 ")
        self.text.setValue(_getf("text", 1.0))
        form.addRow("Text size", self.text)

        self.auto = QCheckBox("Apply automatically at every start (live mode)")
        self.auto.setChecked(str(_qs().value("auto", AUTO_APPLY_AT_STARTUP)).lower()
                             in ("true", "1"))
        form.addRow("", self.auto)
        lay.addLayout(form)

        self.result = QLabel()
        self.result.setWordWrap(True)
        lay.addWidget(self.result)

        row = QHBoxLayout()
        b_apply = QPushButton("Apply now")
        b_apply.setToolTip("Live: font and icon sizes, no restart (approximate)")
        b_true = QPushButton("Restart at true scale\u2026")
        b_true.setToolTip("Relaunch with Qt's scale factor: scales everything, "
                          "viewport included")
        b_reset = QPushButton("Reset")
        b_close = QPushButton("Close")
        for b in (b_apply, b_true, b_reset):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addLayout(row)

        self.cmd = QLineEdit()
        self.cmd.setReadOnly(True)
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.cmd.text()))
        crow = QHBoxLayout()
        crow.addWidget(self.cmd, 1)
        crow.addWidget(copy)
        hint = QLabel("To keep a true scale at every launch, set the environment "
                      "variable before starting IngeTrazo:")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addLayout(crow)

        self.preset.currentIndexChanged.connect(self._preset_changed)
        self.pct.valueChanged.connect(self._refresh)
        b_apply.clicked.connect(self._apply)
        b_true.clicked.connect(self._true)
        b_reset.clicked.connect(self._reset)
        b_close.clicked.connect(self.accept)
        self._refresh()

    def scale(self) -> float:
        return self.pct.value() / 100.0

    def _preset_changed(self):
        w = self.preset.currentData()
        if w == 0:
            self.pct.setValue(100)
        elif w and w > 0:
            self.pct.setValue(round(scale_for_workspace(
                w, self.phys_w, self.os_dpr) * 100))

    def _refresh(self):
        s = self.scale()
        ww, wh = workspace_for_scale(s, self.phys_w, self.phys_h, self.os_dpr)
        note = ""
        if _true_active():
            note = (f" A true Qt scale of {round(_true_factor() * 100)} % is active in "
                    "this session; \u201cApply now\u201d then only changes icons and text.")
        self.info.setText(
            f"Your screen: {self.phys_w} \u00d7 {self.phys_h} px (system scale "
            f"{round(self.os_dpr * 100)} %).{note}")
        self.result.setText(
            f"<b>At {round(s * 100)} % the interface lays out like a "
            f"{ww} \u00d7 {wh} px screen</b> - "
            + ("more working space, smaller controls." if s < 1 else
               "larger controls, less space." if s > 1 else "unchanged."))
        self.cmd.setText(permanent_command(s))

    def _save(self):
        s = _qs()
        s.setValue("scale", self.scale())
        s.setValue("icon", self.icon.value())
        s.setValue("text", self.text.value())
        s.setValue("auto", "true" if self.auto.isChecked() else "false")
        s.sync()

    def _apply(self):
        self._save()
        LIVE.apply(self.scale(), self.icon.value(), self.text.value())

    def _true(self):
        self._save()
        LIVE.apply(1.0, self.icon.value(), self.text.value())  # icons/text only
        if restart_at_scale(self.win, self.scale()):
            self.accept()

    def _reset(self):
        self.pct.setValue(100)
        self.icon.setValue(1.0)
        self.text.setValue(1.0)
        self.preset.setCurrentIndex(0)
        self._save()
        LIVE.reset()


# --------------------------------------------------------------------------
# Menu tools
# --------------------------------------------------------------------------
class DisplayScaleTool(Tool):
    name = "Display Scale..."
    shortcut = None

    def on_activate(self, viewport):
        _Dialog(viewport.window()).exec()

    def on_deactivate(self, viewport):
        pass


def _step(viewport, delta):
    s = round(max(SCALE_MIN, min(SCALE_MAX, _getf("scale", 1.0) + delta)), 2)
    _qs().setValue("scale", s)
    if _true_active():
        viewport.flash_status("A true scale is active - change it in Display Scale...", 4000)
        return
    LIVE.apply(s, _getf("icon", 1.0), _getf("text", 1.0))
    viewport.flash_status(f"Interface scale {round(s * 100)} %", 2500)


class ScaleSmallerTool(Tool):
    name = "Display Scale: Smaller (more space)"
    shortcut = None

    def on_activate(self, viewport):
        _step(viewport, -0.10)

    def on_deactivate(self, viewport):
        pass


class ScaleLargerTool(Tool):
    name = "Display Scale: Larger"
    shortcut = None

    def on_activate(self, viewport):
        _step(viewport, +0.10)

    def on_deactivate(self, viewport):
        pass


class FocusModeTool(Tool):
    name = "Focus Mode (hide panels)"
    shortcut = None

    def on_activate(self, viewport):
        on = toggle_focus(viewport.window())
        viewport.flash_status("Focus mode on - run it again to restore the panels"
                              if on else "Panels restored", 3000)

    def on_deactivate(self, viewport):
        pass


# --------------------------------------------------------------------------
# Apply the saved scale once the window is up
# --------------------------------------------------------------------------
def _find_main_window():
    app = QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow) and w.isVisible():
            return w
    return None


def _autoapply(tries=6):
    try:
        if str(_qs().value("auto", AUTO_APPLY_AT_STARTUP)).lower() not in ("true", "1"):
            return
        if _find_main_window() is None:
            if tries > 1:
                QTimer.singleShot(1500, lambda: _autoapply(tries - 1))
            return
        if (abs(_getf("scale", 1.0) - 1.0) > 1e-3 or abs(_getf("icon", 1.0) - 1.0) > 1e-3
                or abs(_getf("text", 1.0) - 1.0) > 1e-3):
            apply_saved()
    except Exception:  # noqa: BLE001 - never disturb app startup
        pass



# --------------------------------------------------------------------------
# Native dockable toolbar, matching the other IngeTrazo plugin toolbars
# --------------------------------------------------------------------------
_TOOLBAR_ATTR = "_ingetrazo_display_scale_toolbar"


def _display_scale_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#23516d"), 3))
    painter.setBrush(QColor("#bfe4f5"))
    painter.drawRoundedRect(7, 10, 50, 35, 4, 4)
    painter.drawLine(26, 46, 26, 53)
    painter.drawLine(38, 46, 38, 53)
    painter.drawLine(19, 54, 45, 54)
    painter.setPen(QPen(QColor("#ef922f"), 4))
    painter.drawLine(20, 34, 44, 20)
    painter.drawLine(20, 34, 20, 24)
    painter.drawLine(20, 34, 30, 34)
    painter.drawLine(44, 20, 34, 20)
    painter.drawLine(44, 20, 44, 30)
    painter.end()
    return QIcon(pixmap)


def _ensure_toolbar(win):
    toolbar = getattr(win, _TOOLBAR_ATTR, None)
    if toolbar is not None:
        return toolbar
    toolbar = QToolBar("Display Scale", win)
    toolbar.setObjectName("IngeTrazoDisplayScaleToolbarV1")
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    toolbar.setIconSize(QSize(26, 26))
    action = toolbar.addAction(_display_scale_icon(), "Display Scale settings")
    action.setToolTip("Display Scale - interface, icon and text size")
    action.triggered.connect(lambda checked=False: _Dialog(win).exec())
    win.addToolBar(Qt.TopToolBarArea, toolbar)
    setattr(win, _TOOLBAR_ATTR, toolbar)
    return toolbar


class DisplayScaleToolbarTool(Tool):
    name = "Display Scale: Toolbar"
    shortcut = None

    def on_activate(self, viewport):
        win = viewport.window()
        toolbar = getattr(win, _TOOLBAR_ATTR, None)
        if toolbar is None:
            _ensure_toolbar(win).show()
        else:
            toolbar.setVisible(not toolbar.isVisible())

    def on_deactivate(self, viewport):
        pass


def setup(app):
    """Native plugin setup hook used by the other IngeTrazo toolbars."""
    _ensure_toolbar(app.window)


def _start_toolbar(tries=6):
    win = _find_main_window()
    if win is not None:
        _ensure_toolbar(win)
    elif tries > 1:
        QTimer.singleShot(1500, lambda: _start_toolbar(tries - 1))


if QApplication.instance() is not None:
    QTimer.singleShot(2200, _autoapply)
    QTimer.singleShot(2700, _start_toolbar)
