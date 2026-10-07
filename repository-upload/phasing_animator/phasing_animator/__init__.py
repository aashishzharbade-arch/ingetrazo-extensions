# SPDX-License-Identifier: GPL-3.0-or-later
"""Phasing Animator V1.0 — original open-source IngeTrazo extension."""
from .engine import KEY, TITLE, VERSION


def setup(app):
    from .ui import Controller
    if not hasattr(app.window, '_phasing_animator'):
        app.window._phasing_animator = Controller(app)
