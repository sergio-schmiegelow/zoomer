# Zoomer

Zoomer builds "infinite zoom" videos from a series of images. For each pair
of consecutive images you mark the same three features in both pictures and
choose the video frame (crop) for each image. Zoomer scales and blends the
pair so that the camera appears to dive from one image into the next, and
chains all the pairs into a single video.

## Features

- Desktop editor built with PyQt6.
- Image list with drag-and-drop, "Add files" and `Del` to remove; images are
  shown with their EXIF orientation applied.
- Pair editor: two synchronized marker editors (left image: `next_points`,
  right image: `prev_points`) with a draggable video frame, three draggable
  markers, zoom/pan and "zoom to all / points / frame" shortcuts.
- **Find alignment points**: SIFT feature matching proposes the markers for a
  pair. It runs in the background and can be interrupted. The result is
  discarded, with a warning, when the correlation of the two aligned images
  is below the **Correlation threshold** option.
- New images start with a fixed triangle of markers inside the frame (at
  least 10% of the frame's smaller side from the edges).
- Live previews: input image, fusion preview (with fusion step and alpha
  range sliders) and a **video preview** with a scrubber, play controls and
  a label with the current zoom relative to the first frame (e.g. `3.28x`).
  The fusion preview keeps its zoom/pan while you edit and resets only when
  you change pair.
- **Recommended alpha range bar** under the alpha range slider: green where
  both images fill the video frame, gray elsewhere. With **Auto alpha
  range** enabled (Options menu or the "Auto" checkbox next to the bar) the
  alpha range is set to the largest green range, or the full range when
  there is none.
- Tooltips on the image list, video settings, Options menu, fusion
  controls, recommended range bar and *Find alignment points*.
- Zoom interpolation is currently always logarithmic.
- A sample project is included in `project_examples/trunk_example/`.
- AVI export from the File menu's **Export** action, with per-frame progress
  shown in the Video preview tab and an interrupt button.
- Runtime-probed output format choices (such as AVI, MP4, MOV, MKV, WebM and
  other containers supported by the installed OpenCV codecs).
- Undo/redo (`Ctrl+Z`, `Ctrl+Y`) of the last 10 project edits.
- Changes are continuously written to `autosave.zmr` for crash recovery.
- Named `.zmr` project files are saved explicitly with **Save project**,
  **Save project as**, or `Ctrl+S`.
- At startup, Zoomer offers to recover `autosave.zmr`; declining removes the
  stale recovery snapshot and continues normal startup.
- Application preferences (`zoomer.cfg`): frame crosshair, auto open last
  project, alignment-marker thickness (1–10 pixels, default 2), auto alpha
  range (default on) and correlation threshold (0.0–1.0, default 0.20).
- **Options > Marker thickness** adjusts both colored marker strokes and
  their animated outline together; the default is 2 pixels.

## Installation

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .            # runtime dependencies: PyQt6, numpy, opencv-python
pip install -e ".[dev]"     # adds pytest and ruff for development
```

## Running

```bash
zoomer                      # console script installed by pip
python -m zoomer            # equivalent
zoomer --config ~/zoomer.cfg
```

The application config defaults to `./zoomer.cfg` (the current directory).
If no project is opened automatically, the **New project** dialog appears.
See [docs/usage.md](docs/usage.md) for the full workflow.

## Project layout

```
pyproject.toml
README.md
docs/                 user and developer documentation
project_examples/     sample project (trunk_example)
src/zoomer/
    __init__.py
    __main__.py       python -m zoomer
    backend.py        image model, project I/O, alignment, video generation
    widgets.py        reusable Qt widgets
    gui.py            main window, history, preferences, entry point
tests/                pytest suite (runs headless)
```

Image folders, `.zmr`/`.json` project files and generated videos are user
data and live outside the package.

## Tests and linting

```bash
pytest                                  # Qt runs with the offscreen platform
ruff format . && ruff check .
```

## Documentation

- [Usage guide](docs/usage.md)
- [Project file and config formats](docs/project-format.md)
- [Architecture](docs/architecture.md)
- [Development guide](docs/development.md)

## License

Zoomer is free software, released under the GNU General Public License,
version 3 or (at your option) any later version. See [LICENSE](LICENSE).
PyQt6 is itself GPL-licensed, which is compatible with this choice.

## Known limitations

- Available containers and codecs depend on the local OpenCV build. Zoomer
  probes its supported candidate formats; OpenCV does not expose a complete
  enumeration of every possible muxer extension.
- Interrupt is checked between frames. The current frame finishes writing
  before the partial AVI is closed.
