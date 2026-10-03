# Development and validation

## Implementation

Single-file IngeTrazo extension using `setup(app)`, Qt toolbar/menu/overlay APIs,
native `Tool` events, `Mesh` edges with curve tags, and `Group.ext` for persisted
recipes. XYZ recipes use metres; the UI displays millimetres. New curves use
`InsertGroupCommand`; updates use a dedicated history command that replaces the
group mesh and retains its transform. Input is validated before changing the model.

Algorithms were implemented independently: de Casteljau evaluation for Bézier,
piecewise cubic evaluation, de Boor evaluation for clamped/periodic B-splines,
and recursive nonuniform interpolation for centripetal Catmull–Rom. No SciPy runtime
dependency. All toolbar icons are original QPainter drawing code.

Mathematical references:
- [SciPy B-spline definition and knots documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.BSpline.html)
- [Yuksel, Schaefer and Keyser: Catmull–Rom parameterization](https://www.cemyuksel.com/research/catmullrom_param/)

The supplied BezierSpline SketchUp ZIP was inspected read-only for its feature
inventory and origin notices. Its Ruby implementations, assets and translations
are not included. This plugin is a smaller independent implementation of the
selected drawing/editing scope, not a feature-complete replacement.

## Validation performed

34 automated checks passed against IngeTrazo 0.5.7 source:
- All five types: endpoints, closed connectivity, native curve tags, rigid transforms.
- Known Bézier midpoint, equivalent cubic/B-spline case, multi-span anchors.
- Catmull–Rom interpolation and periodic spline seam tangent checks.
- Invalid input, degenerate controls, disconnected and branched conversion rejection.
- Native history create/edit/undo/redo, copied-group isolation and `.igz` round-trip.
- Simulated point drag, cancel, numeric input recovery and draft conversion.
- Group-local coordinate mapping, changed-document guard, external mesh edit detection.
- Conversion of translated wire groups without deleting the source.

Additional native `MainWindow` integration check passed: plugin discovery, seven
movable/floatable toolbar actions, launching/closing each drawing editor, Edit action,
Apply/Undo/Redo, and example/preview generation.

Environment: Windows, IngeTrazo 0.5.7 source, PySide6 Essentials 6.11.2, offscreen Qt.
This validates code and event handlers, not a physical interactive GPU session.

Local acceptance check: install the file, draw a curve using viewport clicks, drag
one point, Apply, Undo/Redo, save/reopen an `.igz`, then select the curve and Edit.
Float and redock the toolbar. Also try converting an ordinary three-edge polyline.
