# Development and source availability

This release contains the editable Python source for IngeTrazo Kitchen Maker.
It was developed in this project with AI assistance. A user-supplied kitchen
extension was inspected to understand its workflow before implementation;
this was not a clean-room development process.

The implementation uses Python, native IngeTrazo mesh/group/history APIs and a
PySide6 interface. Cabinet presets are generated from parameters in the source.
Toolbar icons are drawn by code. Example models and screenshots are generated
from this plugin. The supplied reference extension's files, catalog JSON,
textures, thumbnails and branding are not included in this release.

The package audit compares file hashes against the previously extracted reference files,
checks substantial exact source-line matches, and checks for reference-specific
identifiers. These checks have a limited scope: they are not proof of universal
originality, a legal clearance, or a guarantee about every possible similarity.
Inspecting another implementation remains part of this project's history.

## License

The plugin source is distributed under **GPL-3.0-or-later**. The complete GPL v3
text is included in LICENSE, and the source carries its SPDX identifier. License
notices remain intact; removing them would not make the software more original.

## Runtime dependencies

The plugin imports IngeTrazo 0.5.7 APIs, PySide6 and NumPy from the host runtime.
Those dependencies are not bundled in this ZIP and keep their own licenses.
This release does not claim authorship of those libraries or of the GPL text.

No activation service, license key, analytics or network calls are implemented
in the plugin source. CSV export writes only to the destination chosen by the
user; modeling actions use the host document and command history.

Version 1.0.2 changes packaging/provenance documentation only, plus the internal
version number. The categorized library from 1.0.1 remains available. It is a
source distribution; publication to a public Git repository is a separate step.
