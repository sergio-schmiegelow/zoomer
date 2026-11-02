# Usage

## Starting

```bash
zoomer [--config PATH]
```

`--config` selects the application preferences file (default `./zoomer.cfg`).
On start Zoomer opens the last project when **Options > Auto open last
project** is enabled; otherwise the **New project** dialog is shown.

The window title shows the current project name.

## Menus

| Menu | Item | Description |
| --- | --- | --- |
| File | Open project (`Ctrl+O`) | Load a `.zmr` file |
| File | Save project | Write the project to its file |
| File | Save project as | Save under a new name (`.zmr` is enforced) |
| File | New project | Ask for a name and the video settings, then a file |
| Edit | Undo / Redo (`Ctrl+Z` / `Ctrl+Y`) | Last 10 project edits |
| Video | | Output format, video size, frame rate, duration and interpolation |
| Export | | Choose an output AVI file and render the project |
| Options | Frame crosshair | Show the frame centre; dragging it moves the frame |
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

Every change is saved to the project file immediately.

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

Export renders as quickly as frame generation permits; the playback FPS
limit applies to preview playback, not file export. If the writer cannot be
opened, frame generation fails, or export is interrupted, the result may be
a partial or empty file; an error message is shown for failures.
