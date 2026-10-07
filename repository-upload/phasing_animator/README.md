# Phasing Animator V1.0

An original, open-source animation extension for **IngeTrazo 0.5.7**.
All features are available in a single open-source edition.
Developed by aashishzharbade-arch.

## Install

1. Close IngeTrazo.
2. Extract this archive to a normal folder.
3. Copy the complete **`phasing_animator` folder** into:
   `%APPDATA%\ingetrazo\plugins\`
4. The resulting path must be
   `%APPDATA%\ingetrazo\plugins\phasing_animator\__init__.py`.
5. Restart IngeTrazo and open **Extensions > Phasing Animator V1.0**.

The floating/dockable toolbar uses four icons: open editor, object/camera
keyframes, play/pause, and export. Drag its handle to move or dock it.
The previous Animation Lite extension can coexist. Its existing model data can
be imported from the **Object & camera keys** tab; the original data is retained.

Do not copy the outer release folder, tests or examples into the plugins folder.
The phasing_animator folder contains the complete plugin.

## First phasing animation

1. In the model, create layers such as Foundation, Structure, Envelope and Roof.
   Assign the appropriate groups or geometry to these layers. Exit group editing.
2. Open Phasing Animator to begin.
3. Choose a model layer in the left panel, then **Add phase track**.
4. Set the start/end times, entrance effect and after-phase behavior. Click
   **Apply phase settings**.
5. Click anywhere on the timeline ruler or track area to seek. Drag empty space
   to scrub. Enable **Hover scrub** if you want mouse movement alone to seek.
6. Drag a phase bar to move its timing; drag either end to trim it. A click on a
   bar selects it and seeks without moving it. The time field offers precise entry.
7. Press Play. Save your IngeTrazo document as **IGZ** to retain animation data.

For a faster D5-style construction sequence, select the objects installed in a
step, choose their layer, move the playhead and click **Capture construction
step**. The command creates or selects that layer's phase and records the
selected object poses at the current time. Repeat after moving the objects for
later steps. Use **Apply phase settings** to refine the visibility transition.

Open `examples/Pavilion-phasing.igz` to try the four-track demonstration.
Screenshots in this release are from the actual Qt extension, not the prototype.

## Phase behavior

Unlimited phase tracks, object/camera keyframes and PNG/MP4/WebM export are available to everyone. One phase track is supported per model layer. Saved projects from previous editions are migrated automatically.

**Show instantly** reveals a layer at its start time. **Fade in** interpolates
surface opacity from zero to the original material opacity. Edges are suppressed
during the fade, then restored. **Rise into place** begins below the final position
by the specified distance and moves along world Z to the final position. A negative
distance starts above it. Distances in the editor are millimetres.

Before a phase starts, its layer is hidden. **Keep visible** holds the completed
state. **Hide layer** hides it at and after its end time. Turning off **Enable
phase** bypasses the animation for that track. Layers or objects already hidden
in the source model stay hidden; nested layers remain subject to parent visibility.

Phase preview supports grouped, nested and loose mesh geometry. Faces with their
own layer tags receive separate temporary preview placements, allowing them to
rise without tearing shared source geometry. The source model is never scrubbed
in place. Closing the editor leaves source positions, materials and visibility
unchanged. Only explicit recording/preparation and animation-data edits affect
the document; they are undoable through the model's normal Undo/Redo.

## Object and camera keyframes

1. Select top-level groups/components and click **Add selected groups** before
   moving them. Their initial poses are recorded at time zero.
2. Move, rotate or scale them with IngeTrazo's normal tools.
3. Set **Key time** and click **Record pose**. Repeat at other times.
4. Orbit the main model viewport and click **Record camera** to record its view.
5. Return to Animation to preview the combined keyframes and layer phases.

Object positions and positive scales interpolate linearly; rotations use
shortest-path quaternion interpolation. Camera yaw uses the shortest arc.
Record intermediate angles for a complete 360-degree rotation. The first/last
key is held outside its keyed range. A recorded key replaces a key at the same time.

Object tracks target top-level containers. Nested contents follow their parent;
independent nested object keyframes, custom hinges, constraints, deformation,
mirrored/sheared/zero-scale keyframes and animated face-me billboards are not
supported. After exploding or materializing a tracked object, remove its old
track and add it again before moving. Geometry edits are not keyframed.

The editor copies the main view on opening or when that view changes. Otherwise,
middle mouse and the wheel adjust the preview camera. Camera keys override that
view during playback. **Refresh model** rebuilds the preview from current geometry.

## Export

Open **Export animation**. Available presets:

| Ratio | Output sizes |
| --- | --- |
| 16:9 landscape | 1280×720, 1920×1080, 2560×1440, 3840×2160 |
| 9:16 portrait | 720×1280, 1080×1920, 1440×2560, 2160×3840 |
| 1:1 square | 1080×1080, 2160×2160 |
| 4:3 presentation | 1440×1080, 1920×1440 |

Frame rates: **24, 25, 30, 50 or 60 FPS**. Rendering uses the host's native
**OpenGL GPU pipeline**. It is not a WebGPU renderer. The preview can run slower
than the selected FPS on complex models; export still writes every scheduled frame.

**PNG sequence** needs no extra software. For **MP4/H.264** or **WebM/VP9**, browse
to your installed FFmpeg executable. It must include the `libx264` or `libvpx-vp9`
encoder respectively. FFmpeg is optional and is not bundled in this release.
Video encoding uses those software encoders; the scene rendering is GPU-based.

Select an output folder. Each export creates a uniquely named subfolder with
numbered PNG frames and `manifest.json`; videos are placed alongside them. Existing
runs are not overwritten. Cancel stops rendering/encoding and keeps completed PNG
frames. A failed encoder also leaves the frames available. A partial video is
never renamed to the finished video name until encoding succeeds.

Export includes both visual endpoints, evenly sampled over `ceil(duration × FPS)`
frames. The encoded duration is that frame count divided by FPS. The rendering
aspect ratio follows the chosen output size, so portrait framing is narrower than
the landscape editor preview. Check the composition before a long export.

## Scope and limitations

V1.0 has one animation clip . Multiple clips, advanced easing,
audio and a dedicated WebGPU renderer remain future work. They are not implemented
or presented as working settings.

The isolated preview copies mesh geometry and materials, which uses extra memory.
Its render scope is meshes, groups/components, layers, materials, shadows and
section cuts. Terrain, map tiles, survey overlays, reference image planes,
dimensions and annotation overlays are not included. Transparent surfaces follow
IngeTrazo's existing transparency-rendering behavior. Do not use this extension
as a substitute for a full-scene export of those unsupported entities.

## Source and checks

`phasing_animator/engine.py` holds data validation, keyframes and phase evaluation.
`phasing_animator/ui.py` contains the editor, timeline, toolbar and export workflow.
No host files are patched. See `PROVENANCE.md`, `LICENSE` and `VALIDATION.md`.

With the IngeTrazo 0.5.7 source and its Python/Qt dependencies available, set
`INGETRAZO_SOURCE` to that source directory and run:

```
python tests/check.py
python tests/render_check.py
```

The second command opens a temporary test editor for real OpenGL rendering and
writes test exports/screenshots into this release directory. Use a writable copy.

The animator preview and exports hide drawing axes and guides while retaining the scene display style.
