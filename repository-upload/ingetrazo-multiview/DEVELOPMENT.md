# IngeTrazo MultiView development

Version 1.0.2 targets the IngeTrazo 0.5.7 host inspected for this release.
Source and accompanying tests are GPL-3.0-or-later; see LICENSE.

## Structure

The plugin is a single Python module with a setup(app) entry point. It creates
a native Qt toolbar and a central four-view container with synchronized splitters.
Secondary Viewport widgets share the main document and history. Cameras remain
independent. One container is retained across activation cycles; while inactive,
it is hidden and parented to the main window.

## Regression test

Use Python with the host's dependencies (including PySide6 and NumPy). Set
INGETRAZO_SOURCE to the IngeTrazo 0.5.7 source directory, then run:

    python tests/test_toggle.py

The test uses Qt offscreen mode and isolated settings. It checks ten repeated
activate/maximize/deactivate cycles, central-widget ownership, retained container
identity, and synchronization after replacing the document and history.
It does not validate OpenGL rendering or every native/extension tool.

## Screenshots

- editor-preview.png: actual 1.0.2 Windows Qt/OpenGL test window with the bundled
  SUV model displayed with solid faces in all four views.
- toolbar.png: user-supplied close-up of the floating MultiView toolbar.

The toolbar close-up is the earlier supplied reference. The editor screenshot
was captured from the new build. Live rendering checks reproduced missing
faces with 1.0.1 and confirmed solid geometry with 1.0.2, both during MultiView
and after returning to single view. The face count stayed at 13,956 in both
versions: the defect affected GPU uploads, not model geometry.

Before reparenting, _prepare_viewport_move invalidates document render caches,
clears the differential VBO upload cache and drops the offscreen framebuffer
while its context is still valid. Otherwise the host may skip writing unchanged
geometry to buffers recreated by Qt after the viewport is reparented.

## Manual verification

After restarting IngeTrazo with the updated plugin, toggle MultiView repeatedly,
resize the application and splitters, maximize each pane, then toggle off/on.
Verify the panel fills the central area without covering menus or toolbars.
Check New/Open, editing and undo, and navigation in each pane on the target GPU.
