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
  pair. It runs in the background and can be interrupted.
- Live previews: input image, fusion preview (with fusion step and alpha
  range sliders) and a **video preview** with a scrubber and play controls.
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
  project, and alignment-marker thickness (1–10 pixels, default 2).
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

## Known limitations

- Available containers and codecs depend on the local OpenCV build. Zoomer
  probes its supported candidate formats; OpenCV does not expose a complete
  enumeration of every possible muxer extension.
- Interrupt is checked between frames. The current frame finishes writing
  before the partial AVI is closed.
