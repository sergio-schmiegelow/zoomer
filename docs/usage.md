# Usage

## Starting

```bash
zoomer [--config PATH]
```

`--config` selects the application preferences file (default `./zoomer.cfg`).
On start Zoomer opens the last project when **Options > Auto open last
project** is enabled; otherwise the **New project** dialog is shown.
Opening or recovering a project shows an animated **Loading project** banner
until its project file and images have loaded.

The window title shows the current project name.

## Menus

| Menu | Item | Description |
| --- | --- | --- |
| File | Open project (`Ctrl+O`) | Load a `.zmr` file |
| File | Save project (`Ctrl+S`) | Write the current project to its named `.zmr` file |
| File | Save project as | Save under a new name (`.zmr` is enforced) |
| File | New project | Ask for a name and the video settings, then a file |
| Edit | Undo / Redo (`Ctrl+Z` / `Ctrl+Y`) | Last 10 project edits |
| Video | | Output format, video size, frame rate, pauses, zooming duration and interpolation |
| Export | | Choose an output AVI file and render the project |
| Options | Frame crosshair | Show the frame centre; dragging it moves the frame |
| Options | Marker thickness | Set colored alignment strokes and each outline edge to 1–10 pixels (default 2) |
| Options | Auto open last project | Reopen the previous project on start |

## Workflow

1. **Add images.** Drop files on the list or use *Add files*. Non-image files
   are refused. Reorder by dragging; select an image and press `Del` to
   remove it. A new image gets the largest centred frame that matches the
   video aspect ratio and a random starting triangle of markers.
2. **Edit a pair.** The bottom area edits two consecutive images; their
   names are bold in the list. Use *Previous pair* / *Next pair* to move.
   - Drag the markers (red, green, blue) onto the same three features in
     both images. The left editor edits `next_points`, the right one
     `prev_points`.
   - Drag the frame by its edges to move it; drag the corners to resize it
     while keeping the video aspect ratio.
   - Mouse wheel zooms, dragging empty space pans. The buttons next to each
     editor fit everything, the markers or the frame.
   - *Find alignment points* proposes markers using SIFT feature matching.
     A banner shows progress and can be interrupted; the project changes only
     when the search succeeds.
3. **Tune the blend.** *Fusion step* previews any point of the transition;
   *Alpha range* sets where in the transition the cross-fade starts and ends
   (before the range only the first image shows, after it only the second).
4. **Check the result.** The preview tabs show the selected image, the fusion
   of the current pair, and the whole **Video preview** with play, pause,
   start/end and single-frame controls. Playback never exceeds the project
   frame rate. A calculation problem, such as markers that make the zoom
   shrink between images, is reported on the preview canvas.
   Removing images updates the previews; fusion and video are unavailable
   when fewer than two images remain.

Every change is written to `autosave.zmr` immediately for crash recovery.
Use **File > Save project** or `Ctrl+S` to write the changes to the named
project file; **Save project as** chooses a new named project file.
The window title displays `*` while changes are unsaved to the named project.
Closing a modified project asks whether to **Save**, **Discard**, or **Cancel**;
Cancel keeps the editor open, and Discard removes the recovery snapshot.
The window title shows `*` while changes have not been saved to the named
project. Closing while modified prompts to **Save**, **Discard**, or **Cancel**.
Discard removes the recovery snapshot; Cancel leaves the application open.

## Crash recovery

At startup, if `autosave.zmr` exists, Zoomer asks whether to recover it. The
recovered data is treated as unsaved: use **Save project as** (or `Ctrl+S`,
which opens Save As when no named project is active) to write a named project.
Choosing not to recover removes that stale recovery file, then startup
continues with the configured last project or New Project flow.

`autosave.zmr` is stored next to the selected `zoomer.cfg`. It is separate
from the named project and cannot be selected as a named project file.

## Exporting a video

1. Select **Export** and choose the output filename. Zoomer enforces the
   `.avi` extension.
2. Zoomer switches to the **Video preview** tab and shows an
   **Exporting video file** banner with the current frame count. Each frame
   is displayed as it is written.
3. Use **Interrupt** to stop after the current frame. The writer is closed
   and the AVI contains the frames completed so far. The project controls and
   video-preview scrubber are restored when export ends.

The output format selected in **Video** is used for export, and the extension
is corrected to match it. Formats are offered only when the current OpenCV
build can open a writer and encode a probe frame for that container/codec.
The available list can differ across platforms and OpenCV builds.

Set **Pause before** and **Pause after** in **Video** to hold the first and
last zoom frames. **Zooming duration** controls the transition itself; both
pauses default to zero and are also shown in the video preview.

Export renders as quickly as frame generation permits; the playback FPS
limit applies to preview playback, not file export. If the writer cannot be
opened, frame generation fails, or export is interrupted, the result may be
a partial or empty file; an error message is shown for failures.
