# IngeTrazo MultiView

**Version:** 1.0.4  
**Target:** IngeTrazo 0.5.x (API v2)  
**License:** GPL-3.0-or-later  

**IngeTrazo MultiView** brings Rhino-style synchronized 4-viewport layout to IngeTrazo, featuring Top, Perspective, Front, and Right views in an adjustable 2×2 grid with Double-Spacebar enlarge/restore and a native dockable & floatable Qt toolbar.

## 1.0.4 toolbar icon

The Two Views button now uses a two-pane icon matching the Four Views icon.
It follows the light/dark theme and turns orange when enabled. Hover for its
tooltip. The action name remains available to assistive technology.

## 1.0.3 two-view layout

Click **2 Views** on the floating/dockable toolbar to display the Top and
Perspective panes side by side. Each pane's title menu can change its camera.
Drag the divider to resize them. Click **2 Views** again to restore four panes.
Maximize and Double Space restore the selected two- or four-view layout.
The button also opens MultiView directly into two views from single view.

## 1.0.2 rendering fix

Fixed missing solid faces after toggling MultiView. Reparenting a native Qt
viewport can recreate its OpenGL buffers while the host retains its upload
cache. The plugin now invalidates those caches before moving the viewports,
so faces and materials are uploaded again. Geometry and undo history are
not modified. Verified with the bundled SUV model in a real Windows Qt/OpenGL
window: solid faces remain visible in MultiView and after returning to single view.

## 1.0.1 fixes and validation

- Reuses one four-view container across on/off cycles, avoiding stale input filters.
- Hides and parks the inactive panel inside the main window instead of leaving an orphan window.
- Preserves splitter sizes when reopening and prevents delayed initialization from resizing an inactive panel.
- Refreshes secondary document references and caches after New/Open.
- Restores the real document's unit binding after creating secondary views.

Tested with ten repeated toggle/maximize cycles against the IngeTrazo 0.5.7
host in Qt offscreen mode. This checks widget ownership and lifecycle; it
does not verify GPU rendering or every drawing-tool interaction. Restart
IngeTrazo after replacing the plugin to clear the old containers and filters.

---

## Features

- **4 Synchronized Viewports (2×2 Grid)**:
  - **Top View**: Orthographic plan view with 2D blueprint grid.
  - **Perspective View**: Full 3D perspective viewport connected to all core tools and undo history.
  - **Front View**: Orthographic elevation view.
  - **Right View**: Orthographic elevation view.
- **Dynamic Light & Dark Theme Adaptation**:
  - Automatically matches IngeTrazo's active theme setting (`Window ▸ Preferences ▸ Theme`: Light or Dark).
  - Clean light headers (`#e6e6e6`), soft borders (`#d0d0d0`), and light splitters in Light theme—no dark bars or black borders overriding your theme.
  - Dynamically updates live when switching themes without requiring an application restart.
- **Double-Spacebar Enlarge & Restore**:
  - Double-tap <kbd>Space</kbd> (`< 0.45s`) over any viewport to instantly maximize it to **100% full screen**.
  - Double-tap <kbd>Space</kbd> again to restore the 2×2 layout with splitters preserved.
  - Single tap of <kbd>Space</kbd> continues to function normally as the **Select** tool.
  - Safe text filter: automatically ignored when typing in measurement boxes (VCB) or dialogs.
- **Native Dockable & Floatable Toolbar (`QToolBar`)**:
  - Docks seamlessly into IngeTrazo's top toolbar area alongside native toolbars.
  - Grab the dotted grip (`::`) on the left to drag it anywhere and **float natively** as a tool palette.
  - High-resolution vector CAD icons:
    - `⊞` **MultiView Toggle** (Checkable, toggles 4-view and single view).
    - `⛶` / `🗗` **Enlarge / Restore** (Maximize active viewport or restore 4 views).
    - **Top View** (Plan preset).
    - **Perspective View** (3D preset).
    - **Front View** (Elevation preset).
    - **Right View** (Elevation preset).
    - **Zoom Extents All** (Frame geometry across all viewports).
- **Rhino-Style Synchronized Splitters**:
  - Top and bottom horizontal splitters stay synchronized as you adjust columns, giving a true 4-way cross-junction feel.
- **Orthographic 2D Navigation**:
  - In 2D orthographic views (Top, Front, Right), middle-click drag **pans** by default (standard CAD convention).
  - Hold <kbd>Ctrl</kbd> or <kbd>Alt</kbd> + middle-drag to unlock free 3D orbiting in any view.
- **Extensions Menu Integration**:
  - Found under `Extensions ▸ IngeTrazo MultiView ▸`.
  - Includes a toolbar toggle action (`Show IngeTrazo MultiView Toolbar`) to show/hide the toolbar.

---

## Installation

### Method 1: Automatic (1-Click on Windows)
1. Close IngeTrazo and extract `IngeTrazo-MultiView-V1-v1.0.2.zip`.
2. Double-click `install.bat`.
3. Launch or restart **IngeTrazo**.

### Method 2: Manual Installation
1. In IngeTrazo, go to **Extensions → Open plugins folder** (or navigate to `%APPDATA%\ingetrazo\plugins\` on Windows).
2. Copy `ingetrazo_multiview.py` into this folder.
3. Restart IngeTrazo.

> [!NOTE]
> Ensure only one copy (`ingetrazo_multiview.py`) is installed in the plugins directory. No extra libraries or image assets are needed—the toolbar icons and viewport engine are 100% self-contained code.

---

## Quick Reference / Shortcuts

| Action | Shortcut / Trigger | Description |
| :--- | :--- | :--- |
| **Toggle 4-View / Single** | <kbd>F4</kbd> or toolbar `⊞` | Switches between single viewport and 4-viewport layout. |
| **Enlarge / Restore Viewport** | <kbd>Double Space</kbd> | Maximizes the hovered/active viewport to 100% or restores 4 views. |
| **Maximize via Header** | Header button `🗖` or Double-click header | Maximizes that specific cell. |
| **Switch View Angle** | Click cell title (`Top ▾`, etc.) | Menu to switch cell camera to Top, Front, Right, Iso, Bottom, Back, Left. |
| **Zoom All Viewports** | Toolbar `Zoom Extents (All)` | Simultaneously frames model in all 4 viewports. |
| **Float / Dock Toolbar** | Drag dotted handle `::` | Drag off the top bar to float; drag back to dock. |

---

## Package Contents

```text
IngeTrazo-MultiView-V1-v1.0.2/
├── ingetrazo_multiview.py    # Main extension file (self-contained)
├── install.bat               # 1-click Windows installer
├── install.ps1               # PowerShell installer script
├── README.md                 # Complete documentation & usage guide
├── LICENSE                   # GNU General Public License v3.0
├── DEVELOPMENT.md            # Architecture, checks and screenshot provenance
├── editor-preview.png        # Verified four-view SUV screenshot (1.0.2)
├── toolbar.png               # Supplied floating-toolbar screenshot
└── tests/test_toggle.py       # Native host lifecycle regression test
```

---

## Compatibility

The editor screenshot shows the actual 1.0.2 test window; the toolbar close-up
is the earlier supplied reference. See
DEVELOPMENT.md for validation details. Install
only the Python plugin (or use install.bat); keep screenshots, docs and tests
outside the plugins folder. Back up an older plugin outside that folder first.

- **IngeTrazo**: 0.5.0 or later (API Version 2).
- **Operating Systems**: Windows 10/11, Linux, macOS.
- **Framework**: Python 3.10+, PySide6 (Qt 6.x).

---

## License

This extension is licensed under the **GNU General Public License v3.0 or later** (GPL-3.0-or-later). See `LICENSE` for details.
