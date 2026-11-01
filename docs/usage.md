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
| Video | | Video size, frame rate, duration and interpolation method |
| Export | | Choose the output file name (rendering is not wired up yet) |
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
