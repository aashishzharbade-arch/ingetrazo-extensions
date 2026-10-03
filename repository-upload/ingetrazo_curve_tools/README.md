# IngeTrazo Curve Tools V1.0

Version 1.0.0 · Target: IngeTrazo 0.5.7 · GPL-3.0-or-later

Create and edit Bézier curves, chained cubic Bézier curves, B-splines,
centripetal Catmull–Rom splines, and polylines. Includes closed loops,
sampling controls, a coordinate editor, draggable viewport controls,
non-destructive conversion, and Undo/Redo.

## Install

1. Close IngeTrazo.
2. Copy **ingetrazo_curve_tools.py** into
   `%APPDATA%\ingetrazo\plugins\` (usually
   `C:\Users\YOUR-NAME\AppData\Roaming\ingetrazo\plugins\`).
3. Start IngeTrazo. Find **IngeTrazo Curve Tools V1.0** in the menu and toolbar.

Copy only the Python file into the plugins folder. No pip packages or external
assets are required beyond IngeTrazo's own NumPy and PySide6 dependencies.
Keep only one copy of this plugin in your scanned plugins folders.

The toolbar has five drawing buttons, **Edit**, and **Convert**. Drag its handle
to float it or dock it along another edge. The plugin menu includes its visibility
toggle. Hover over a button for its name.

## Draw

1. Choose a curve button.
2. Choose a world drawing plane (XY, XZ, YZ) and plane offset in millimetres.
   `3D / view` uses the host's normal picking/snapping; when dragging, it uses
   a camera-facing plane through the selected control.
3. Move the dialog aside. Click **Pick / drag in model**, then click points in
   the viewport. Alternatively, use **Add row** and enter exact XYZ coordinates.
4. Adjust sampling and optionally check **Closed loop**.
5. Choose **Drag points**, return to the viewport and drag an orange numbered
   point. The drawing and small preview update while you drag.
6. Click **Create curve**, or press Enter with the viewport focused.

The model changes only when you apply. Esc cancels a drag; another Esc cancels
the editor. Cancel closes the draft without changing the model. Delete/Backspace
in the viewport removes the selected row, or the last point if no row is selected.
The small dialog preview is an illustrative fixed projection, not an orbit view.

## Choose the right curve

| Type | How the points work | Sampling |
| --- | --- | --- |
| Bézier | One curve; first and last controls are endpoints, other controls shape it | Total segments |
| Cubic Bézier | Open: 4, 7, 10… controls, ordered anchor–handle–handle–anchor; closed: 3, 6, 9… | Segments per cubic span |
| B-spline | Clamped cubic spline (lower degree for 2–3 controls); open ends interpolate, interior controls usually do not | Total segments |
| Catmull–Rom | Passes through all controls; centripetal parameterization | Segments between each pair of points |
| Polyline | Straight segments through the controls | Sampling setting has no effect |

Closed B-splines are periodic and closed Catmull–Rom splines wrap through the
first point. Closed ordinary Bézier curves can have a sharp seam. For chained
cubic Bézier curves, you control tangent continuity through handle placement;
there is no automatic smooth-handle constraint in this version.

## Edit, convert, and save

- Select a generated curve group and click **Edit**, or use its context-menu
  **Edit Curve Tools curve** action. Coordinates are local to that group.
- Native group transforms are preserved. Editing one copied curve does not
  change the other copy's mesh.
- Save in `.igz` to retain the editable recipe. Reopen the file and use Edit.
- Select one connected root-level edge chain or a wire-only group and click
  **Convert**. The initial draft is a polyline through the source vertices.
  Choose another type to reshape it. A new group is created on Apply; the original
  is retained. Avoid leaving both coincident copies if you do not need both.
- **Convert draft to polyline** preserves the current sampled path. Simply
  changing the type dropdown reinterprets the controls and changes the shape.
- Apply creates one history action. Use native Ctrl+Z / Redo to reverse/reapply it.
- If you change the mesh directly with native tools, its stored control recipe
  becomes outdated. Edit detects this and asks you to Convert the current wire.

Close any group-editing session before using Curve Tools. This first version
works with root-level curves; nested editing is not supported.

## Limits

- Native sampled edges, not analytic NURBS; no weights, custom knots, surfaces,
  arc fitting, dogbones, chamfer fabrication, or animation tools.
- 2–256 sampling segments; up to 32 controls for ordinary Bézier, 128 for other
  splines, and 512 for polylines/conversion. Maximum 8,192 sampled segments.
- Native mesh welding is approximately 0.1 mm. Consecutive samples that fall
  into the same weld cell are collapsed. Extremely small curves are rejected.
- Conversion rejects branched/disconnected selections. Self-intersections can
  create welded junctions and are not automatically removed.
- Do not switch documents, enter group editing, or alter the source while an
  editor is open; close and reopen the editor after such changes.

## Included files

- `ingetrazo_curve_tools.py`: complete readable plugin source; icons drawn in code.
- `curve-examples.igz`: five open curve types and three closed examples, spaced apart.
- `editor-preview.png`, `toolbar.png`: interface previews.
- `DEVELOPMENT.md`: provenance, validation and mathematical references.
- `LICENSE`: GNU GPL version 3; this plugin is offered as GPL-3.0-or-later.

Tested against local IngeTrazo 0.5.7 source using automated geometry/UI checks
and an offscreen native main-window integration run. Physical mouse interaction
and GPU rendering in your installed application still need your local check.

## License and origin

This is a new Python implementation of standard curve mathematics, written for
IngeTrazo with AI assistance. It does not bundle or translate the supplied SketchUp
extension's code, icons, or assets. That archive was reviewed to understand feature
scope. This is not an official port and is not affiliated with its author.

The new source is open source under GPL-3.0-or-later. Keep the supplied license and
SPDX notice when sharing it. Independent implementation does not justify a blanket
guarantee about all third-party rights. No notices were stripped from the reference
archive, which is not distributed in this package.
