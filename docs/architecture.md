# Architecture

```
src/zoomer/
    backend.py   no Qt dependency: numeric and I/O code
    widgets.py   Qt widgets with no knowledge of project files
    gui.py       MainApp: owns the project data and wires everything together
```

Dependencies only point downwards: `gui` imports `widgets` and `backend`;
`widgets` imports nothing from the package (it only duck-types the image
objects it is given); `backend` imports neither.

## backend

| Item | Role |
| --- | --- |
| `ImageClass` | Image file wrapper: OpenCV pixels plus a cache slot for the Qt image |
| `load_config` / `save_config` | Read and write `.zmr` files; `save_config` converts `ImageClass` objects to paths without mutating the input |
| `create_blended_frame` | Renders the cross-fade of image `index` and `index + 1` for a `size_alpha` and `blend_alpha` |
| `auto_align_images` | Crops both frames, matches SIFT features and stores the three best matches as the pair's markers |
| `VideoGenerator` | `perform_video_calculations()` computes the cumulative zoom and the per-frame `(image index, size_alpha)` list; `get_total_frames()`, `generate_video_frame_on_position()` and `generate_full_video()` use it |

Helpers prefixed with an underscore (affine transforms, marker
interpolation, zoom computation) are internal.

Zoom chain: for each pair the zoom ratio is the mean triangle side of the
second image's `prev_points` divided by that of the first image's
`next_points`, both mapped to video coordinates. The ratios must be
non-decreasing; otherwise `perform_video_calculations()` returns an error
message. Frames are linearly spaced in `log(zoom)`.

## widgets

| Widget | Role |
| --- | --- |
| `ImageFilesOrganizer` | Image list with drag and drop, add and delete; emits `image_files_changed` |
| `PreviewArea` | Tabs: input image, fusion preview, video preview |
| `VideoPreviewWidget` | Scrubber, transport buttons and playback timer limited to the project FPS |
| `ImageFusionEditor` | Hosts two `ImageMarkersEditor`s plus the sliders and the alignment banner; emits edit requests |
| `ImageMarkersEditor` | Zoomable canvas with the draggable frame and markers; the marker outline pulses once per second |
| `FusionStepSlider`, `AlphaRangeSlider` | Painted sliders sharing one horizontal grid |
| `VideoSettingsDialog` | Video size, frame rate, duration, interpolation; also the *New project* dialog |

Widgets are decoupled from the data: they emit signals (`image_edited`,
`alpha_range_edited`, `fusion_preview_requested`, ...) and `MainApp` applies
the change.

## gui.MainApp

`MainApp` owns two dictionaries:

- `proj_data`: the project (same shape as the `.zmr` file). Names that point
  into it use the `proj_` prefix (`proj_image_entries`, `proj_filename`).
- `cfg_data`: application preferences, persisted to `zoomer.cfg`. Related
  names use the `cfg_` prefix.

Every modification goes through `save_autosave()`, which writes the project
file and schedules a 200 ms debounced `_refresh_video_preview()`.

### History

`_record_history()` pushes a snapshot onto a 10-entry deque before each edit
and clears the redo stack. Edits that arrive in a burst (a marker drag) are
coalesced into one entry by a 600 ms timer. Snapshots hold image **paths**, not
`ImageClass` objects. On undo/redo, objects still present in the current
project are reused; missing ones are recreated from the path. If a file has
vanished, the operation is aborted and the stacks are left unchanged.

### Background alignment

SIFT matching can take seconds, so `_AlignmentJob` (a `QThread`) works on
shallow copies of the two entries. The live project changes only if the job
succeeds, was not interrupted and the entries still exist. Interrupting hides
the banner; because OpenCV cannot be stopped mid-call, the thread finishes
quietly and its result is discarded.

### Start-up

`main()` reads the config (`--config` or `./zoomer.cfg`), builds `MainApp`,
and either loads the last project or shows the *New project* dialog.
