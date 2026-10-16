# IngeTrazo Curve Tools 1.1.0

Open-source Python plugin for IngeTrazo 0.5.7. License: GPL-3.0-or-later.

## Install or upgrade

1. Close IngeTrazo.
2. Back up your existing `ingetrazo_curve_tools.py` **outside** the plugins folder.
3. Copy the new `ingetrazo_curve_tools.py` from this package into
   `%APPDATA%\ingetrazo\plugins\`, replacing the old file if present.
4. Keep only one copy of this plugin in the plugins directories. Restart IngeTrazo.

Install only the plugin Python file. Keep the documentation, tests and example
model elsewhere. No extra runtime packages are needed beyond IngeTrazo's NumPy
and PySide6 dependencies.

## Three toolbar buttons

| Button | Use |
| --- | --- |
| Curve Tools | Open the floating drawing panel. Choose one of the five curve tabs. |
| Edit Selected | Select an existing Curve Tools group in the main viewport, then reopen its saved settings and controls. |
| Convert Selected | Select an ordinary connected edge chain or wire-only group and create an editable curve copy. The original is retained. |

The toolbar is movable, floatable and dockable. Its buttons have hover labels.
The extension menu provides the same actions and a toolbar visibility toggle.
The controls panel is a separate modeless floating window. The model viewport
stays in IngeTrazo's main window; there is no preview pane in the plugin.

## Draw and move points

1. Click **Curve Tools**, then choose a tab: Bézier, Cubic Bézier, B-spline,
   Catmull–Rom, or Polyline.
2. Move the floating panel aside and click in the main viewport to add controls.
3. Click an existing orange control to select it. Drag it to move it. There is
   no Add/Drag mode selector and no Pick/Drag activation button.
4. Adjust segments or Closed loop as needed, then click **Create curve**.

The curve remains a draft until Create/Update. Cancel discards the draft. After
applying, the panel closes and the native selection tool returns. Reopen the
panel with **Edit Selected** to edit that curve later.

Clicking the Curve Tools toolbar button while a draft is open brings it forward
and reactivates viewport point editing. Finish or cancel that draft before
editing/converting a different model selection.

## Insert and remove

- **Insert point:** click the button, then click on the displayed curve between
  its endpoints. Insertion is performed in curve order, rather than appending
  to the end. The mode switches off after a successful insertion; Esc exits it.
- Open-curve endpoints remain unchanged. Ordinary Bézier, B-spline and
  Catmull–Rom insertion can reshape the middle. This is a control insertion,
  not a promise of an exact shape-preserving knot insertion.
- Cubic Bézier insertion splits the chosen span and adds an anchor with its
  handles. Its mathematical shape is preserved; the displayed polyline is
  resampled. Very near existing cubic anchors, choose a point farther inside
  the span.
- **Remove selected point:** select an orange control in the viewport, then
  use this button or Delete/Backspace. You can also select a control and use
  the context menu's **Remove selected curve control** action.
- Removing a cubic control may leave an invalid control count. Add the missing
  controls or choose another curve type before applying; the panel explains
  the required count. No model geometry is committed while the draft is invalid.

## Drawing in XYZ

**3D / Geometry** is the default. Vertex and edge snaps use the host's full XYZ
coordinates. Face placement uses IngeTrazo's face picker and world-plane ray hit,
including transformed face placements. In empty space, placement uses a
camera-facing plane through the last point (or the origin for the first point).
During dragging, the fallback plane passes through the point's original position.

**XY / XZ / YZ** constrain one world coordinate. A new empty draft starts on the
plane through the origin; a draft with points uses the plane through its last
point. Dragging uses the plane through the grabbed point. To start on an elevated
plane, first place a point with 3D / Geometry, then choose XY, XZ or YZ.

With focus in the viewport, press **X**, **Y** or **Z** to constrain movement along
that world axis. Press the same key again to unlock, or use Esc. Axis constraints
take priority over plane selection. For movement directly toward the camera,
orbit to a view where that axis is visible before dragging.

The main viewport still supports normal host navigation. XYZ snapping and drawing
are implemented in the plugin; the earlier browser prototype was only a 2D UI demo.

## Curve types and sampling

| Type | Controls | Segments setting |
| --- | --- | --- |
| Bézier | One curve; endpoints plus shaping controls | Total segments |
| Cubic Bézier | Open: 4, 7, 10… points; closed: 3, 6, 9… points | Per cubic span |
| B-spline | Clamped cubic, lower degree for 2–3 controls; periodic when closed | Total segments |
| Catmull–Rom | Centripetal interpolation through each control | Between each pair of points |
| Polyline | Straight segments through its controls | Disabled |

Changing a tab retains the controls and reinterprets them. It may change the
shape. Closed ordinary Bézier can have a sharp seam; cubic tangent continuity
depends on handle placement.

**Convert draft to polyline** captures the current sampled shape as a polyline
draft. **Convert Selected** imports model geometry into a new draft. These are
different operations. Conversion supports one connected unbranched path or loop;
it rejects disconnected/branched paths and groups containing faces or children.

## Save, reopen and Undo

Save the model as `.igz` to retain the control recipe. Curves created with version
1.0 remain editable. Select the curve group and click Edit Selected after reopening.
Native group transforms are preserved; editing a copied group does not modify
the other copy's mesh. Create/Update is one Undo/Redo action.

If a curve mesh is changed outside Curve Tools, its original control recipe may
no longer describe it. Edit detects that mismatch. Convert its current wire into
a new draft instead. Finish group editing and work at the model root before using
this release. Do not change documents or the source geometry while a draft is open.

## Limits and validation

- Sampled native edges, not analytic NURBS or surfaces. No weighted knots,
  fabrication tools, or animation.
- Sampling: 2–256; up to 32 ordinary Bézier controls, 128 other spline controls,
  and 512 polyline/conversion vertices. At most 8,192 sampled segments.
- Mesh welding is approximately 0.1 mm. Tiny consecutive samples can collapse;
  insertion retains their original parameter positions. Self-intersections may
  form welded junctions and are not removed automatically.
- 51 automated checks passed, plus integration checks in the native 0.5.7
  main-window code: loader, three actions, tabs, modeless panel, face placement,
  v1.0 compatibility, conversion, and Undo/Redo. See DEVELOPMENT.md.
- Checks ran with offscreen Qt. A physical mouse/GPU session in your installed
  application was not performed. Try the supplied example file after installation.

## Package contents and license

`ingetrazo_curve_tools.py` is the full readable plugin source. The package also
contains `LICENSE`, `DEVELOPMENT.md`, `tests/test_curve_tools.py`,
`curve-examples.igz`, and editor/toolbar preview images.

This is an independent Python implementation of standard curve mathematics,
created with AI assistance. It does not bundle or translate the reference SketchUp
extension's code or assets. It is not an official port or affiliated with its author.

You may use, study, modify and redistribute this plugin under GPL-3.0-or-later.
Keep the license and notices, and provide the corresponding source when required
by the GPL. No required notices from other work have been removed. The reference
archive is not part of this package.
