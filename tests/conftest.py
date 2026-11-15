"""Shared fixtures; Qt runs headless so the suite works without a display."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2 as cv  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from zoomer.backend import ImageClass, save_config  # noqa: E402

IMAGE_SIZE = (160, 90)  # (width, height); equals the video size below.


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def no_dialogs(monkeypatch):
    """Replace modal warning boxes, which would block a headless run."""
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: warnings.append(args[1:])),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Save),
    )
    return warnings


def write_images(directory, count=3, size=IMAGE_SIZE):
    """Write ``count`` blurred-noise PNGs (SIFT-friendly) and return paths."""
    paths = []
    for index in range(count):
        noise = np.random.RandomState(index).randint(
            0, 255, (size[1], size[0], 3), dtype=np.uint8
        )
        image = cv.GaussianBlur(noise, (5, 5), 0)
        path = directory / f"image{index}.png"
        cv.imwrite(str(path), image)
        paths.append(path)
    return paths


def triangle(size, center=(80.0, 45.0)):
    cx, cy = center
    return [[cx, cy - size], [cx - size, cy + size], [cx + size, cy + size]]


def make_proj_data(directory, count=3, growth=2.0):
    """Build a valid project whose zoom grows by ``growth`` per image pair."""
    paths = write_images(directory, count)
    width, height = IMAGE_SIZE
    entries = []
    for index, path in enumerate(paths):
        entries.append(
            {
                "image": ImageClass(str(path)),
                "frame": [[0, 0], [width, height]],
                "prev_points": None if index == 0 else triangle(10 * growth),
                "next_points": (
                    None if index == count - 1 else triangle(10.0)
                ),
            }
        )
    return {
        "project_name": "Demo",
        "video_data": {
            "size": [width, height],
            "FPS": 10,
            "duration": 1,
            "interpolation_method": "log",
        },
        "images_data": entries,
    }


@pytest.fixture
def proj_data(tmp_path):
    return make_proj_data(tmp_path)


@pytest.fixture
def proj_file(tmp_path, proj_data):
    path = tmp_path / "demo.zmr"
    save_config(str(path), proj_data)
    return path
