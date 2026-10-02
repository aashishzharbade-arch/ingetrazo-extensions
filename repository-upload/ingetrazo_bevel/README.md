# IngeTrazo Bevel V1.0

Version 1.0.2 · IngeTrazo 0.5.7 · GPL-3.0-or-later

### Corner fix in 1.0.1

Rounded box corners now use tessellated spherical patches instead of flat
centroid fans. The patch shares the exact boundary of the adjoining rounded
edges. Compatible co-spherical junctions receive the same treatment; other
junctions retain the conservative faceted patch.

To correct a bevel made with 1.0.0, undo it or reopen an unbeveled source copy,
then apply the updated tool. Existing saved bevel meshes do not update
automatically. Do not apply a second bevel over the old result to fix its cap.

Native Python chamfer and rounded-profile tools for both simple solids and
general closed polygon meshes. Full editable source is included. No activation
key, network service or additional package installation is required.

## Install

Close IngeTrazo. Copy **ingetrazo_bevel.py** into
`%APPDATA%\ingetrazo\plugins`, then restart. Use the **IngeTrazo Bevel V1.0**
toolbar or its submenu under Extensions. Only the Python file is installed;
the examples and documents can remain in the extracted folder.

The toolbar is movable, floating and dockable. Its visibility action is in the
plugin menu. This plugin can coexist with Kitchen Maker and Stair Maker.

## Use

1. Select one solid mesh group to bevel all edges above an angle threshold.
   Alternatively, open a group and select specific edges, or select faces to
   bevel their boundary edges. Loose geometry also works when its entire active
   mesh is a valid closed solid; isolate it in a group if unrelated geometry is
   present. Explicit selections ignore the angle threshold.
2. Enter an **offset along the adjacent faces**, in millimetres. This is not a
   universal fillet-radius measurement, especially on non-right-angle corners.
3. Choose Chamfer, or Rounded with 2–12 segments.
4. Click **Check preview**. The wireframe shows the proposed geometry without
   changing the document. Orange lines show hard edges; blue lines include
   softened subdivisions. Adjust settings and check again as needed.
5. Click **Apply**. Ctrl+Z restores the source geometry; Ctrl+Y reapplies it.

The solid retains its group placement. A whole-group operation replaces only
that instance's mesh, leaving other component instances alone. Face attributes
are carried into the rebuilt faces; bevel faces inherit an adjacent face's
attributes. Custom texture-coordinate appearance on new surfaces is not
guaranteed. The generated mesh saves normally to `.igz`.

## Supported and tested

- Single edges, connected edges and face-boundary selections on boxes.
- Chamfer and rational quadratic rounded edge profiles.
- Spherical corner tessellation for compatible rounded junctions; faceted
  corner closure for other junctions and chamfers.
- Concave L-shaped closed solids.
- Nonrectangular triangular and pentagonal prisms.
- Faceted cylindrical solids, including rounded cap rims with a 30° filter.
- Undo/Redo, material attributes, independent group instances and file saving.
- Floating/dockable toolbar, preview, stale-document protection and plugin loading.

`bevel-examples.igz` contains four finished examples. `editor-preview.png` shows
the actual dialog. Validation uses 39 automated tests against the 0.5.7 source
and an offscreen check of the actual IngeTrazo MainWindow class. Physical mouse
interaction in the packaged desktop application still needs a local trial.

## Geometry limits

This is a first implementation, not a universal bevel kernel. The mesh must be
closed, manifold, consistently outward-oriented, with planar simple faces.
Open surfaces, loose edges, face holes, inward cavity shells, and ambiguous
unequal partial-edge mitres are rejected. Nested assemblies must be opened down
to the solid being edited; they are not automatically flattened. Bake/apply group
scale first, or bevel at the appropriate local mesh level.

The minimum offset is 1 mm because IngeTrazo welds vertices on an approximately
0.1 mm grid. Narrow profiles can still collapse at high segment counts: increase
the offset or reduce the segment count. Maximum input is 6000 faces, 256 corners
per face; an estimated output budget limits costly operations.

The engine checks face orientation, local offset collision, crossing trimmed
edges, corner closure and output manifoldness. These checks are **not** an
exhaustive global self-intersection test; inspect dense concave junctions and
keep source copies for important models. Complex concave/curved combinations
may need smaller offsets, broader selections or topology cleanup.

Rounded edge strips and compatible spherical corners use polygon tessellation;
they are not analytic CAD surfaces. Other multi-edge junctions retain faceted
fills, not general rolling-ball fillets. There is no persistent live
modifier, saved original/proxy toggle, interactive drag-width tool or automatic
coplanar cleanup in this release. After saving/reopening, edit the resulting mesh
normally; a retained source copy is needed to rebuild with different settings.
For parametric Kitchen/Stair parts, regeneration by those plugins can replace
manual bevel edits, so finish their parameters first and keep a source copy.

## Development and license

The implementation was written in Python with AI assistance. Only the supplied
reference extension's readable loader, interface documents and labels were
reviewed. Its encrypted implementation was not decrypted or executed. No code,
icons, UI files, textures or activation libraries from that ZIP are distributed.
This review history is disclosed; it is not a clean-room certification or a
claim of universal originality.

The plugin's source is licensed GPL-3.0-or-later; see LICENSE. It imports
IngeTrazo, PySide6 and NumPy from the installed host. Those projects retain their
own authorship and licenses. The ZIP includes no copies of those dependencies.


## Publication preparation

The owner confirmed IngeTrazo 0.5.7 as the installed test version.
The publishing preparation checks syntax, packaging and catalog metadata; it does not rerun the historical test suites described above.
