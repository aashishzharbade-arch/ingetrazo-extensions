# Source and licensing

Phasing Animator V1.0 is distributed under GPL-3.0-or-later. Its extension code,
Qt-drawn toolbar icons, sample model and tests were authored for IngeTrazo.
The keyframe math builds on the original Animation Lite implementation created
earlier in this project, with standard interpolation supplied by Qt.

The supplied SketchUp reference archive was used earlier to understand its
advertised workflow and readable loader metadata. Its encrypted implementation
was not decrypted or copied. No reference binaries, icons, audio, source files,
branding or proprietary runtime are included. No notices were stripped from
reference code or assets.

The extension imports APIs from the user's GPL-licensed IngeTrazo installation
and its existing Qt/PySide6 runtime. IngeTrazo itself is not bundled. Optional
FFmpeg is a separately supplied executable, not part of this distribution;
the user selects a build with the required video encoders.

The full GPL v3 license text is included. The “or later” choice is specified in
the source headers. Open source carries license terms; it does not mean the
absence of attribution, source-distribution or other applicable obligations.
