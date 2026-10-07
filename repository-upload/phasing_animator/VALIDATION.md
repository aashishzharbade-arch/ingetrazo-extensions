# Validation — unified release

Checked on 2026-10-07 against IngeTrazo 0.5.7 with the actual host and Qt editor.

- Passed extension discovery, toolbar icons, 103 phase tracks, old edition metadata migration, duplicate-layer validation, phase evaluation, source isolation, object/camera keyframes, Undo/Redo, IGZ save/load and timeline mouse interactions.
- Confirmed edition selector absent, export enabled and developer credit appears without channel branding.
- Native OpenGL export passed at 1280×720 / 24 FPS and 1080×1920 / 30 FPS, with three frames each and changing animation endpoints.
- Export cancellation passed. Updated screenshots captured from the rebuilt editor.
- MP4/WebM encoding was not rerun for this branding release; its FFmpeg encoder implementation is unchanged. An installed FFmpeg is still required for video output.
