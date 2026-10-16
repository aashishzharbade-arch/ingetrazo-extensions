# Development notes — 1.1.0

## Changes from 1.0.0

- Three toolbar actions: Curve Tools, Edit Selected, Convert Selected.
- One modeless floating Qt tool window with five curve tabs.
- Removed the secondary preview, coordinate table, mouse-mode dropdown,
  Add row button and Pick/Drag button.
- Point hit testing chooses select/drag automatically; empty-space clicks append.
- Insert mode places controls in path order; cubic spans use de Casteljau splitting.
- Selected-point removal, live overlays, plane constraints, full XYZ snaps,
  face placement, and X/Y/Z movement constraints.
- Bare axis keys are claimed before native shortcuts; Ctrl+Z/other chords remain
  available to IngeTrazo.
- Readable GPL-3.0-or-later source and original programmatically drawn icons.

## Architecture

Uses the native plugin `setup(app)` API, `Tool` callbacks, a QToolBar, menu/context
actions and an overlay. Geometry is a separate edge-only Group. The recipe lives
in `Group.ext['ingetrazo_curve_tools']` and persists in `.igz`. Local coordinates
are metres; sampling limits respect native mesh precision.

Create uses InsertGroupCommand. Edit replaces a group mesh with one history
command, preserves its placement, and checks for a stale recipe or source mesh.
Conversion creates a new group. The supplied original archive is not needed at
runtime and none of its code or artwork is distributed.

## Validation

51 automated cases passed against local IngeTrazo 0.5.7 source:
- Endpoints/connectivity/curve tags for all five curve types, open and closed.
- Known Bézier midpoint, cubic/B-spline equivalence, multi-span anchors.
- Catmull–Rom interpolation and periodic seam tangents.
- Rigid transforms, invalid inputs, and disconnected/branched rejection.
- Native history, copied-group isolation and `.igz` round-trip.
- Automatic hit/select/drag/add behavior, drag cancellation, removal and conversion.
- Full XYZ point snaps and face placement precedence.
- Axis constraints and keyboard chord preservation.
- Insertion endpoints for every type, closed insertion, cubic shape preservation,
  viewport insertion and original parameter tracking after tiny samples collapse.

Additional native MainWindow checks passed:
- Discovery imports exactly one plugin and does not instantiate helper tools.
- Three toolbar actions, all five tabs, movable/floatable flags and nonmodal dialog.
- Native keyboard dispatch claims bare Z for the tool.
- Actual host ray-to-plane calculation on a transformed face placement.
- Opening/editing a saved v1.0 curve, applying, undoing and redoing.
- Conversion preserves the source; Undo/Redo affects only the created copy.
- Example model and panel previews generated successfully.

Environment: Windows, offscreen Qt, PySide6 Essentials 6.11.2, pytest 9.1.1,
IngeTrazo v0.5.7 source. Tests simulate interaction and use native application code;
they do not certify physical mouse input or GPU rendering on every installation.

## Running the included regression checks

Use a Python environment with pytest, NumPy, PySide6 and IngeTrazo's source
dependencies available. Set `INGETRAZO_SOURCE` to the folder containing its
`core`, `views`, `tools` and `formats` packages, then run:

```powershell
$env:INGETRAZO_SOURCE = 'C:\path\to\ingetrazo-0.5.7'
python -m pytest tests/test_curve_tools.py -q
```

The tests use `QT_QPA_PLATFORM=offscreen` and never write to the installed plugin
directory. Their temporary `.igz` files are managed by pytest.

Standard mathematical references:
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.BSpline.html
- https://www.cemyuksel.com/research/catmullrom_param/

No SciPy dependency or third-party implementation was copied into the plugin.
