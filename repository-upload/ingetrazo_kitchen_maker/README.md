# IngeTrazo Kitchen Maker V.1

Version 1.0.2 · Target: IngeTrazo **0.5.7** · English UI · millimetres.

A native Python kitchen-design plugin with parametric cabinets, a categorized
library, placement tools and cost reports. Full editable source is included
under GPL-3.0-or-later. See DEVELOPMENT.md for development provenance and runtime
dependencies.

## Install on Windows

1. Close IngeTrazo.
2. Download the Python file, or extract the repository ZIP.
3. Copy **ingetrazo_kitchen_maker.py** into
   `%APPDATA%\ingetrazo\plugins` (create the folder if necessary).
4. Restart IngeTrazo. Open **Extensions → IngeTrazo Kitchen Maker V.1**,
   or use its toolbar.

Only that one Python file needs installation. The example model, previews and
documentation can stay in your Downloads folder. No pip installation is needed;
the plugin uses Qt and NumPy already used by IngeTrazo. It can coexist with Stair
Maker and the architectural toolkit because it has its own filename and data key.

## Included

- 48 original starting presets across Base, Wall, Tall, High, Base corner,
  Wall corner and Filler families. Presets remain dimensionally editable.
- Single/double doors, drawers, drawer plus doors, open shelves, glass doors,
  empty appliance niches and left/right blind corners.
- Width, depth, height, panel thickness, plinth, shelf count, drawer count,
  front gap, handles, hinge side and opening amount.
- Six solid-colour front finishes and three solid-colour worktop finishes.
- Per-cabinet worktops, front overhang and optional backsplash.
- Live shaded preview and IngeTrazo Tutorials watermark in the UI only.
- Seven dedicated toolbar buttons: Library, Add next, Edit, Open/close,
  Swap hinge, Finishes and Cost report.
- Movable, floating and dockable toolbar; use its grip to move it. Its visibility
  can be restored from the plugin menu. IngeTrazo manages saved toolbar layout.
- Undo/Redo, editable recipes stored in `.igz`, and CSV cost reports.

## Create and place a cabinet

In **Library**, choose a **Category**, then use **Cabinet preset** to select one
of that category's cabinets. Changing category loads its first preset; selecting
another preset replaces the cabinet settings. Opening an existing cabinet for
editing keeps its custom settings until you explicitly choose a preset.

Adjust **Cabinet** and **Details**, then choose a
**Placement** method:

- **Click to place:** click the model to place the cabinet's local origin using
  IngeTrazo snapping. Esc cancels. Rotation is set before placement. The clicked
  point controls the elevation; the disabled coordinate fields do not apply.
- **Exact coordinates:** enter X/Y/Z in mm and rotation about Z in degrees.
  A wall-cabinet preset suggests Z = 1500 mm when selected from the library.
- **Next to selected (+X):** select an existing Kitchen Maker cabinet. The new
  cabinet inherits its actual orientation, scale and elevation, then starts
  after its width plus the entered gap. Rotation/XYZ fields do not apply.

Local +X is the cabinet width, +Y points towards its back, and −Y is the front.
Height includes the plinth but excludes the worktop and backsplash.
Tall defaults to 2100 mm; High to 2400 mm. Both can be resized.

Changing Family alone does not reset dimensions. Use a Library preset for
sensible starting dimensions. Wall cabinets require zero plinth and no worktop.
The editor reports invalid combinations before creating geometry.

## Edit and arrange

Select an intact cabinet at the top level of the model, then **Edit**. Its
placement is preserved while its parts are regenerated. You can move, rotate or
copy it with IngeTrazo's normal tools and still edit its parameters afterwards.
Manual changes made inside a generated cabinet are replaced by regeneration.
Close any group-editing session before using these plugin actions.

**Open/close** toggles selected cabinets between closed and 90° doors; drawers
extend proportionally. For a custom amount use the editor (0–110). **Swap hinge**
changes a single door's hinge, or swaps a blind corner's blank side. Symmetric
double doors keep opposite hinges. **Finishes** changes the selected cabinets'
front colour in one undo step. Worktop finish is available in the editor.

Blind corners have rectangular carcasses and a fixed blank front section equal
to the cabinet depth. Build perpendicular runs using exact coordinates/rotation
or the host Move/Rotate tools; Add next creates a straight run, not an automatic
corner turn. Check door clearance in the model.

## Worktops and reports

Worktop ends are flush with the cabinet's sides so adjacent cabinets do not get
overlapping slabs. Front overhang is adjustable. Each cabinet retains its own
worktop; there is no run-level union, corner mitre, sink or hob cutout generator.

Enter the **complete cabinet's unit price** and currency label in Details. Price
starts at zero and includes any worktop/fittings you chose; it is not calculated
from materials. Cost report counts cabinets, including nested group instances,
groups identical configurations, and totals each currency separately. Export
CSV uses decimal-cent rounding and includes dimensions, finish and quantities.
Taxes, labour, installation and wastage are not calculated. This is a planning
cost report, not a supplier invoice or a CNC cutting list.

## Files and limitations

- `example-kitchen.igz`: seven editable cabinets; open in IngeTrazo to try them.
- `example-cost-report.csv`: the example report, with zero prices ready to fill.
- `example-kitchen.png`, `editor-preview.png`, `toolbar.png`: visual previews.
- `DEVELOPMENT.md`: source provenance, audit scope and runtime dependencies.

This version does not include diagonal/L-shaped corner
carcasses, lift-up fronts, appliance/sink models, textured materials, interactive
resize handles, collision checking, cut lists or hardware/manufacturing details.
Glass is a simple transparent panel and hinges are conceptual pivots.

Validated with **76 automated tests** against IngeTrazo 0.5.7 source: category filtering,
preserving custom settings when opening the editor, closed solid
geometry, opening/closing, placement, updates, copying, persistence, Undo/Redo,
reports, plugin discovery and toolbar flags. The actual IngeTrazo MainWindow
class was also used for an offscreen integration check. The packaged desktop app
and physical mouse dragging/docking still need your local trial.

License: GPL-3.0-or-later; see LICENSE.


## Publication preparation

The owner confirmed IngeTrazo 0.5.7 as the installed test version.
The publishing preparation checks syntax, packaging and catalog metadata; it does not rerun the historical test suites described above.
