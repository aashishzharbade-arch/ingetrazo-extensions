# Presentation view - V 0.5.0 Beta

One free, open-source IngeTrazo plugin with a draggable, floatable toolbar and three buttons, in order:

1. **Presentation viewer**: open the model full screen. Only 3D Gizmo, Minimize and Close are shown by default. Left-drag orbits, right/middle-drag pans, wheel zooms, Escape returns to the editor. Camera and selection remain independent of the editor.
2. **Axis visible**: checked means the editor drawing axes are visible. Click to hide/show them; preference is remembered. Snapping remains available. Presentation mode always hides drawing axes; its 3D Gizmo is a separate camera control.
3. **FPS meter**: toggle FPS, frame intervals, worst interval, process CPU and history. Displayed top left in the editor and, when enabled, the presentation window. Off by default, with no continuous-redraw stress test enabled. Reads idle when no frames arrive; paint-event intervals are not GPU render timings.

## Install
Extract this ZIP and copy only the `presentation_view` folder into the folder opened by **Extensions > Open plugins folder**. On Windows this is normally `%APPDATA%\ingetrazo\plugins`. Restart IngeTrazo.

Drag the toolbar grip to any editor edge to dock, or away from an edge to float. Restore a hidden toolbar with **Extensions > Show Presentation view toolbar**. Its stable name lets IngeTrazo save its layout. Commands are also under **Extensions > Presentation view**. The direct Presentation viewer menu action and Ctrl+Alt+P shortcut remain available.

## Compatibility and verification
Built against IngeTrazo 0.5.8 / extension API 2, source commit 8940b72dfe5755e8f140a5ec7056f4fc4893f9fa. Uses host viewport internals and the supplied axis-rendering hook; other versions may require adaptation. Close group editing before launching presentation mode.

Seven Qt offscreen checks passed: camera isolation, blocked editing, gizmo alignment, toolbar registration/docking/layout restore, all three actions, axis draw suppression/restoration, and FPS timer startup/teardown in editor and presentation view. Native OpenGL rendering, physical toolbar dragging and Windows minimize/restore still require an in-app check.

The viewer preserves the model's materials and display style; it is not a new rendering engine. Source and tests are included. No internet service is required.

## License and attribution
GPL-3.0-or-later; see LICENSE. Axis visibility is adapted from the supplied axis_visibility.py, copyright (C) 2026 aashishzharbade-arch; its copyright notice is retained. FPS functionality is adapted from the supplied GPL-licensed fps_meter.py. Presentation code integrates these into one package; the original standalone registration is removed.
