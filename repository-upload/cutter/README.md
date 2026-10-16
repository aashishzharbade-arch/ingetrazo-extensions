# Cutter for IngeTrazo

Release: 1.0.0. Tested with IngeTrazo 0.5.8 by the author.
License: GPL-3.0-or-later, as declared in cutter.py.

Slice model geometry using a two-point line or the active section plane. Includes a movable, dockable toolbar and three menu commands:

- **Cutter: Slice**: click the start and end of a cutting line.
- **Cutter: Slice & Remove**: cut and remove geometry on the right side of the directed line.
- **Cutter: Slice at Section Plane**: cut at the active section plane and remove its hidden side.

The implementation includes loose-face and recursive group/component handling and attempts to cap closed cut loops. It wraps each operation in the host's snapshot history mechanism.

## Install

Download `cutter.py`. In IngeTrazo, choose **Extensions > Open plugins folder**, close the application, copy the file into that folder, and restart. Keep the filename and remove older duplicate copies.

Only the Python file is required. It depends on IngeTrazo's internal tools, mesh, intersection, triangulation, edits and history APIs, plus its PySide6 runtime. It is not a standalone Python program.

## Before using removal commands

Save a copy of your model and verify Undo/Redo on that copy. The supplied implementation scans the entire loose mesh when removing one side, even when a subset of loose faces is selected. Therefore, do not rely on selected-only removal in this release without fixing and testing that behavior.

Test transformed/nested groups and shared component definitions carefully. The implementation can directly modify a component's underlying mesh; check whether other instances change. Non-uniform scaling and nested entity removal also need runtime verification.

## External behavior

No network access, subprocess launches or filesystem deletion calls were identified in the supplied source. Removal commands delete model geometry inside IngeTrazo, rather than files on disk. Toolbar icons are drawn in code; no image assets are required.
