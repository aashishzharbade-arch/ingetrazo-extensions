# SPDX-License-Identifier: GPL-3.0-or-later
"""FPS overlay adapted from the user-supplied fps_meter.py (GPL-3.0-or-later).
Registered through the combined Presentation view toolbar, with a top-left
position. Counts viewport paint events; frame intervals are not GPU timings.
"""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget



_ATTR = "_ingetrazo_fps_meter"      # where the meter lives on the viewport
_MARGIN = 12
_REFRESH_MS = 500
_WINDOW_S = 1.0                      # FPS is averaged over the last second
_HISTORY = 40                        # samples in the mini graph (~20 s)


class _Overlay(QWidget):
    """Click-through translucent panel painted over the viewport."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.resize(176, 104)
        self.fps = 0.0
        self.lines: list[str] = []
        self.history: list[float] = []
        self.stress = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 22, 34, 185))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

        if self.fps >= 50:
            tint = QColor("#5fd38d")
        elif self.fps >= 25:
            tint = QColor("#ffbe69")
        else:
            tint = QColor("#ff6b6b")

        big = QFont("monospace", 15)
        big.setStyleHint(QFont.Monospace)
        big.setBold(True)
        p.setFont(big)
        p.setPen(tint)
        head = f"{self.fps:5.1f} FPS" if self.fps > 0 else "  idle"
        p.drawText(10, 26, head)
        if self.stress:
            small = QFont("monospace", 7)
            small.setBold(True)
            p.setFont(small)
            p.setPen(QColor("#ff6b6b"))
            p.drawText(self.width() - 46, 14, "STRESS")

        small = QFont("monospace", 8)
        small.setStyleHint(QFont.Monospace)
        p.setFont(small)
        p.setPen(QColor("#d6e2ee"))
        y = 42
        for line in self.lines:
            p.drawText(10, y, line)
            y += 13

        # Mini history graph (bars scaled to at least 60 FPS).
        gx, gy, gw, gh = 10, self.height() - 26, self.width() - 20, 18
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(gx, gy + gh, gx + gw, gy + gh)
        if self.history:
            top = max(60.0, max(self.history))
            step = gw / _HISTORY
            p.setPen(Qt.NoPen)
            p.setBrush(tint)
            for i, v in enumerate(self.history[-_HISTORY:]):
                h = max(1.0, gh * v / top) if v > 0 else 0.0
                p.drawRect(int(gx + i * step), int(gy + gh - h),
                           max(1, int(step) - 1), int(h))
        p.end()


class _Meter(QObject):
    """Counts viewport paints and keeps the overlay up to date."""

    def __init__(self, viewport):
        super().__init__(viewport)
        self.vp = viewport
        self.stamps: deque[float] = deque(maxlen=1200)
        self.history: list[float] = []
        self.overlay = _Overlay(viewport)
        self._last_wall = time.perf_counter()
        self._last_cpu = time.process_time()
        self._cpu = 0.0

        self._stress_timer = QTimer(self)
        self._stress_timer.setInterval(0)
        self._stress_timer.timeout.connect(self.vp.update)

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

        viewport.installEventFilter(self)
        self._place()
        self.overlay.show()
        self.overlay.raise_()
        self._timer.start()
        self.refresh()

    # -- stress mode ------------------------------------------------------
    @property
    def stress(self) -> bool:
        return self._stress_timer.isActive()

    def set_stress(self, on: bool):
        if on:
            self._stress_timer.start()
        else:
            self._stress_timer.stop()
        self.overlay.stress = on
        self.overlay.update()

    # -- measuring --------------------------------------------------------
    def eventFilter(self, obj, ev):
        if obj is self.vp:
            kind = ev.type()
            if kind == QEvent.Paint:
                # A repaint caused only by our own overlay is not a frame.
                if not (self.overlay.isVisible()
                        and self.overlay.geometry().contains(ev.rect())):
                    self.stamps.append(time.perf_counter())
            elif kind == QEvent.Resize:
                self._place()
        return False

    def _place(self):
        self.overlay.move(_MARGIN, _MARGIN)

    def refresh(self):
        now = time.perf_counter()
        recent = [t for t in self.stamps if now - t <= _WINDOW_S]
        fps = 0.0
        worst = 0.0
        if len(recent) >= 2:
            span = recent[-1] - recent[0]
            if span > 0:
                fps = (len(recent) - 1) / span
            worst = max(b - a for a, b in zip(recent, recent[1:])) * 1000.0
        # Process CPU (all threads; can exceed 100 % on multi-core).
        cpu_now = time.process_time()
        wall = max(1e-6, now - self._last_wall)
        self._cpu = (cpu_now - self._last_cpu) / wall * 100.0
        self._last_wall, self._last_cpu = now, cpu_now

        self.history.append(fps)
        del self.history[:-_HISTORY]

        ov = self.overlay
        ov.fps = fps
        ov.history = list(self.history)
        if fps > 0:
            ov.lines = [f"frame  {1000.0 / fps:6.1f} ms",
                        f"worst  {worst:6.1f} ms",
                        f"cpu    {self._cpu:5.0f} %"]
        else:
            ov.lines = ["no repaint in 1 s", "orbit/pan to measure",
                        f"cpu    {self._cpu:5.0f} %"]
        kids = self.vp.children()
        if kids and kids[-1] is not ov:
            ov.raise_()
        ov.update()

    # -- teardown ---------------------------------------------------------
    def close(self):
        self._timer.stop()
        self._stress_timer.stop()
        try:
            self.vp.removeEventFilter(self)
        except RuntimeError:
            pass
        self.overlay.hide()
        self.overlay.deleteLater()
        self.deleteLater()


def _meter_for(viewport, create: bool = False):
    meter = getattr(viewport, _ATTR, None)
    if meter is None and create:
        meter = _Meter(viewport)
        setattr(viewport, _ATTR, meter)
    return meter

