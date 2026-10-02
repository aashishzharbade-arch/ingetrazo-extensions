# IngeTrazo Stair maker V.1 — railing update

Plugin version **1.1.0**, for **IngeTrazo 0.5.7**.

## Install

1. Download `make_stair.py`, or extract the repository ZIP.
2. In IngeTrazo choose **Extensions → Open plugins folder**.
3. Replace your existing **make_stair.py** with this release's file.
4. Restart IngeTrazo.

Keep the filename `make_stair.py`; do not keep a second renamed plugin copy.
No extra dependencies or logo files are required. The branded UI, watermark,
floating/dockable toolbar and existing stair controls remain available.

## Add railings to an existing stair

1. Select the stair.
2. Open **Extensions → IngeTrazo Stair maker V.1 → Edit selected stair…**,
   or click the toolbar's Edit button.
3. Open the new **Railings** tab.
4. Choose **Glass** or **Steel**, adjust the controls, then **Update stair**.

The same tab is available when creating a stair. Choose **None** to remove
railings. Older stairs load with None by default. Each create/update is one
Undo step, including the stair and all railing parts.

## Railing styles

**Glass:** sloped glass panels between square steel posts, with a square steel
handrail. Glass thickness and opacity are adjustable. Opacity is stored on the
native faces and shown in the preview. Panels are individually closed solids.

**Steel:** square posts, a square handrail, bottom rails and vertical square
balusters. Baluster width and maximum centre spacing are adjustable.

## Shared controls

- **Sides when walking up:** Both, Left or Right. Sides follow the ascent of
  each flight, including mirrored turns.
- **Height to handrail top:** measured vertically from the tread reference
  line or landing surface, not perpendicular to the stair slope.
- **Centre inset from edge:** positions rail/post centres inside the stair.
  Validation keeps members within the side edges and separates the two sides.
- **Square post width**, **maximum post spacing**, and **square handrail size**.
  Flight posts sit on whole treads; spacing rounds down to a whole number of
  goings. Landing segments subdivide to remain within the requested spacing.
- **Continue around landings:** connects the flight railings through the
  intermediate landing and continues along optional top-landing sides.
  The upper-floor exit remains open. Turn transitions extend the upper
  sloping rail onto the intermediate landing.
- **Infill bottom gap:** vertical gap from the sloping reference line or
  landing surface to the bottom of the panel/bottom rail.

All lengths are millimetres. Glass opacity is a percentage. Controls for the
unused railing style are disabled. Invalid combinations are explained in the
dialog before any geometry is changed.

## Geometry and compatibility

Works with Straight, Straight with landing, L-shaped and U-shaped stairs.
Post, rail, glass and baluster geometry lives in the existing stair group.
Move, rotate and copy the stair normally; its saved parameters remain editable.
Save/open preserves the railing settings and glass transparency.

The railings use rectangular/square sections. Frameless glass, round pipes,
horizontal cable infill and fixings are not included in this release. Members
are separate solids, with simple joints rather than fabricated mitres. The
existing stair remains a tread/riser assembly rather than a structural design.
When no top landing is generated, the terminal posts assume the upper floor
exists at the stair destination. Dimensions are modeling inputs, not a
building-code or structural compliance assessment.

Regeneration replaces manually modified child geometry and its face colors.
Existing parent placement is preserved. The internal parameter key remains
`make_stair`, so older models remain editable.

## Verification

**120 automated tests passed** against IngeTrazo v0.5.7 source, including the
existing stair regression suite and new tests for glass/steel, all stair types,
sides, mirrored turns, outward face winding, closed native meshes, transparency,
post placement, optional landing continuation, validation, old defaults,
Undo/Redo, transform preservation, save/reopen and GUI create/edit workflows.

The Glass and Steel dialogs were rendered and visually checked in Qt offscreen.
Interactive testing in the installed app remains for the user.

The two PNGs in this download show the new Railings tab. They are previews,
not files that need to be copied into the plugins folder.

GPL-3.0-or-later. See LICENSE.


## Publication preparation

The owner confirmed IngeTrazo 0.5.7 as the installed test version.
The publishing preparation checks syntax, packaging and catalog metadata; it does not rerun the historical test suites described above.
