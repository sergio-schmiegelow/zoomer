# Development

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests

```bash
pytest
```

The suite runs headless: `tests/conftest.py` selects Qt's `offscreen`
platform. Shared fixtures build small synthetic projects (blurred-noise PNGs
in a temporary directory), so no sample data is needed.

| File | Covers |
| --- | --- |
| `tests/test_backend.py` | `ImageClass`, project I/O, interpolation, zoom chain, video generation, SIFT alignment |
| `tests/test_widgets.py` | Marker editor interaction, sliders, image list, video preview controls, settings dialog |
| `tests/test_gui.py` | Projects, preferences, start-up, undo/redo, video preview, background alignment |

## Style

```bash
ruff format .
ruff check .
```

Configuration lives in `pyproject.toml` (79 columns; pycodestyle, pyflakes,
isort and pep8-naming rules). Conventions:

- `snake_case` for functions, methods and variables; `CamelCase` for
  classes; `UPPER_CASE` for constants; a leading underscore for private
  names.
- Qt override methods keep their Qt names (`paintEvent`, ...), which is why
  `N802` is ignored for `widgets.py`.
- `proj_` prefix for data that mirrors the project file, `cfg_` prefix for
  application preferences.
- Project and config JSON keys are part of the file format and keep their
  names.

## Adding a feature

1. Put pure logic in `backend.py` (no Qt) and test it in `test_backend.py`.
2. Put UI in `widgets.py` as a widget that only emits signals.
3. Connect it in `MainApp`; route project changes through
   `_record_history()` before modifying `proj_data` and `save_autosave()`
   afterwards so undo, autosave and the video preview stay consistent.
