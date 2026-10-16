# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 aashishzharbade-arch
"""Hide/show drawing axes in IngeTrazo 0.5.8. No model changes."""
from array import array
from functools import wraps
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QToolBar

__version__ = '1.0.0'
__author__ = 'aashishzharbade-arch'


def install_axis_hook(viewport_module):
    """The 0.5.8 paint pass consumes XYZ spans from this module helper.

    Suppress only its draw counts. Keep a small valid float buffer for GL
    drivers that do not accept a zero-byte dynamic buffer allocation.
    This hook applies to the application's viewport rendering, not snapping.
    """
    state=getattr(viewport_module,'_axis_visibility_plugin_state',None)
    if state is not None:return state
    original=getattr(viewport_module,'_axes_vertices',None)
    if not callable(original):
        raise RuntimeError('Axis Visibility requires the IngeTrazo 0.5.8 axis renderer; this version is not compatible.')
    state={'hidden':False,'original':original}
    @wraps(original)
    def vertices(*args,**kwargs):
        if state['hidden']:
            return array('f',[0.0]*6),{name:(0,0) for name in ('x','y','z')}
        return original(*args,**kwargs)
    viewport_module._axes_vertices=vertices
    viewport_module._axis_visibility_plugin_state=state
    return state


def axis_icon():
    pix=QPixmap(40,40);pix.fill(Qt.transparent)
    painter=QPainter(pix);painter.setRenderHint(QPainter.Antialiasing)
    for color,end in [('#db3845',(35,31)),('#299e5c',(5,31)),('#3366c7',(20,5))]:
        painter.setPen(QPen(QColor(color),3));painter.drawLine(20,24,*end)
    painter.end();return QIcon(pix)

