# Taper Tool for IngeTrazo V1.0

Independent, original GPL-3.0-or-later mesh taper extension for IngeTrazo 0.5.7.
No Rhino API, SDK, source code or assets are included or required.

## Install

Close IngeTrazo. Back up the previous Taper plugin outside the plugins folder.
Replace its `ingetrazo_taper.py` with this release's file in
`%APPDATA%\ingetrazo\plugins\`. Keep only one Taper Tool installation (including
any older Taper subfolders). Restart IngeTrazo. Use Extensions > Taper Tool for
IngeTrazo V1.0 or the movable, floating/dockable toolbar.

## Workflow

1. Select mesh groups or a complete loose mesh object. Exit group editing first.
2. Open Taper Tool for IngeTrazo V1.0 and click the axis start, then axis end in the model. Use geometry
   snaps to define a 3D axis.
3. Click away from the axis to establish the reference distance and Flat direction.
4. Move the pointer to preview the target distance, then click to apply.
   Alternatively enter Reference/Target distances in the dialog (millimetres)
   and click Apply. After the reference pick, viewport numeric input followed
   by Enter also applies a target distance; use an explicit suffix such as `500mm`.

Copy preserves the originals. Flat scales only in the reference direction.
Rigid translates each selected group using its bounding-box centre and preserves
its shape. Infinite extrapolates the scale beyond the axis endpoints; disabling
it clamps the scale before and after the axis. Axial divisions controls mesh
refinement within the axis interval. Esc, Cancel, window close or changing tools
discards the draft. Apply creates one Undo/Redo operation.

## Scope and limits

This is a mesh implementation, not a NURBS taper engine. The reference workflow
does not imply identical Rhino results. Faces are triangulated and subdivided;
curved deformation is an approximation. Orange preview transforms sampled
original edges; the final tessellation can look different. Axis-normal distance
picking is easiest from an oblique view; an edge-on view may require orbiting or
entering a numeric distance.

Results are independent world-space mesh groups. Nested group structure,
component instancing and procedural extension recipes are baked into geometry;
Undo restores the original objects. Group material/layer/IFC and face attributes
are retained, but this release does not promise preservation of every specialised
entity feature. Rigid treats all selected loose geometry as one object.
Billboards, partial connected-face selections, collapse/reversal, and results
over 200,000 faces are rejected. Use copies of important models for initial trials.

## Verification

`tests/check.py` exercises the real IngeTrazo 0.5.7 classes offscreen: plugin
discovery, four picks, numerical input, cancellation, Copy, transformed groups,
loose faces, Undo/Redo, stale document handling, Flat, finite taper, tilted axes,
Rigid and closed-box topology. Set INGETRAZO_SOURCE to the host source directory
and run with Python, PySide6 and the host dependencies available.
These checks do not replace an interactive GPU test in the installed application.

See LICENSE for the complete GPL terms.
