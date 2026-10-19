# Texture Library for IngeTrazo 1.0.0

Tested with IngeTrazo 0.5.8 by the author. GPL-3.0-or-later, as declared in texture_library.py. The release version 1.0.0 is publication metadata selected by the author; the source has no explicit version constant.

## Features

- A Textures panel with thumbnail grid, search and folder categories.
- Real-world tile width/height in m, cm, mm, inches or feet, with an aspect lock and quarter-turn rotations.
- Paint with it arms the native Paint tool. Apply to selection uses the host command/history system to paint selected faces/groups in one undo step.
- Local image or ZIP import into your texture library.
- Optional online browser for Poly Haven textures and 1K/2K/4K colour-map downloads, subject to asset availability.

PBR auxiliary-map filenames are filtered out of the browser. This extension uses colour images; it does not implement normal, roughness, displacement or ambient-occlusion shading.

## Install

Download texture_library.py. In IngeTrazo choose **Extensions > Open plugins folder**, close the application, copy this file into that folder, and restart. Keep its original filename and only one installed copy.

Only the Python file is required. It uses IngeTrazo's internal APIs and PySide6; it is not a standalone application. No textures are bundled.

Open the Textures panel or **Extensions > Texture library…** (Ctrl+Shift+T if the shortcut is available). Choose your library folder, import images, select a texture, set its size/rotation, then paint or apply to selection. The scanner lists at most 5,000 entries.

## Local writes and online access

QSettings stores your library path and unit preference. The default library is in the platform's writable generic data location under `IngeTrazo/texture_library`.

Import copies supported image files into the library. ZIP imports flatten archive member paths into a category/set folder; duplicate filenames in the same set can replace earlier files. Individual-image imports choose a numbered name if a target already exists.

When Remember size is enabled and a texture is used, tile dimensions are merged into a JSON sidecar next to that image. The sidecar is named by replacing the image suffix with `.json`; images with the same stem and different extensions share a sidecar. Use a dedicated writable library folder.

Online requests begin when you open Get online. They retrieve Poly Haven asset metadata and thumbnails; downloading a selected colour map writes it to `<library>/Poly Haven` and records its source, license and resolution in a sidecar. Downloading the same asset/extension again replaces its prior image. The HTTP helper checks requested HTTPS URLs against Poly Haven domains; downloads use urllib.request and background threads with queued Qt updates.

No subprocess launches or filesystem deletion calls were identified in the supplied source. User-selected imports and downloaded textures are written to disk; model painting goes through host history commands. Undoing a model edit does not undo library downloads, imports or sidecar writes.

## Compatibility and licensing

The source calls private host helpers `tools.paint._surface_commands` (with a fallback) and the main window's `_activate_tool` when those features are used. It does not replace or monkey-patch those helpers, but host upgrades still require compatibility testing.

The plugin code is GPL-3.0-or-later. Texture assets have their own licenses; the plugin license does not relicense your imported images. Check your assets' terms before distributing them or models containing them.

Publication preparation checked syntax and the exact file checksum only. The author reported testing on 0.5.8; online downloads and GUI behavior were not rerun during that preparation.
