# Display Scale for IngeTrazo

Version: 1.2.0. Tested with IngeTrazo 0.5.8 by the author.
License: GPL-3.0-or-later, as declared in display_scale.py.

Adjust IngeTrazo's interface size to gain workspace or make controls easier to read. Includes 720p, 1080p, QHD and UHD workspace presets, a custom interface scale from 40% to 300%, independent icon and text multipliers, and Focus Mode to hide and restore visible side panels.

The presets simulate workspace sizes by changing UI scale; they do not change monitor resolution or add physical pixels.

## Install

1. Download `display_scale.py` from the tagged release.
2. In IngeTrazo, choose **Extensions > Open plugins folder**.
3. Close IngeTrazo, copy `display_scale.py` into that folder, and restart.
4. Remove older duplicate copies of this extension. Keep the original filename.

Only the Python file is required. It uses IngeTrazo's `tools.base.Tool` and the host's PySide6 installation; it is not a standalone Python application.

## Use

Open the monitor toolbar button or **Extensions > Display Scale...**.

- **Apply now:** changes fonts and supported icon/button sizes immediately. Live scaling is approximate; fixed-size widgets can retain their original dimensions.
- **Restart at true scale:** asks for confirmation, closes the current window through the host's normal close/save flow, then launches IngeTrazo with `QT_SCALE_FACTOR` in the new process environment. Save your work before trying this feature.
- **Reset:** resets the saved live interface, icon and text settings. If a true Qt scale is active, restart at 100% as well. Remove a persistent environment override separately if you set one.
- **Focus Mode:** hides visible dock panels; invoke again to restore them.
- **Display Scale: Toolbar:** toggles the dockable toolbar.

Preferences are stored locally with QSettings under organization `ingetrazo-plugins`, application `display_scale`. Automatic application at startup can be disabled in the dialog.

## External behavior and limits

The source contains no network operations or file deletion calls. It writes local preferences. The optional restart uses `subprocess.Popen` to launch the current IngeTrazo executable/Python entry point with an adjusted environment.

The dialog displays and copies a command for a persistent Qt scale; it does not execute that command. On Windows its suggested `setx QT_SCALE_FACTOR ...` command changes the user's environment and may affect other Qt applications started afterward. Prefer the live mode or an IngeTrazo-specific launcher when possible.

Workspace size is an estimate based on the active screen. Multi-monitor behavior, docking, display scaling and restart handling should be checked on each supported platform.
