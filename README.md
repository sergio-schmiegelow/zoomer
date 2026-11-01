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
- Undo/redo (`Ctrl+Z`, `Ctrl+Y`) of the last 10 project edits.
- Projects are plain JSON files (`.zmr`) and are saved after every change.
- Application preferences (`zoomer.cfg`): frame crosshair, auto open last
  project.

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

- The **Export** menu only chooses the output file name; rendering a video
  to disk is available through `zoomer.backend.VideoGenerator` but is not yet
  connected to the interface.
- Videos are written as XVID AVI.
