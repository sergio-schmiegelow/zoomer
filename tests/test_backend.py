import json

import cv2 as cv
import numpy as np
import pytest

from conftest import IMAGE_SIZE, make_proj_data, triangle, write_images
from zoomer import backend


def test_convert_points_and_frame_to_video_coordinates():
    points = np.array([[101, 202], [103, 204], [105, 206]], dtype=np.float32)
    frame = np.array([[100, 200], [200, 400]], dtype=np.float32)
    video_dims = np.array([960, 540], dtype=np.float32)
    expected = np.array(
        [[9.6, 5.4], [28.8, 10.8], [48.0, 16.2]], dtype=np.float32
    )
    output = backend.convert_points_and_frame_to_video_coordinates(
        points, frame, video_dims
    )
    assert np.allclose(output, expected)


class TestImageClass:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            backend.ImageClass(str(tmp_path / "missing.png"))

    def test_loads_cv_image_and_resolves_path(self, tmp_path):
        path = write_images(tmp_path, 1)[0]
        image = backend.ImageClass(str(path))
        assert image.get_cv_image().shape[:2] == IMAGE_SIZE[::-1]
        assert image.get_image_path() == path.resolve()

    def test_qt_image_cache(self, tmp_path):
        image = backend.ImageClass(str(write_images(tmp_path, 1)[0]))
        assert image.get_qt_image() is None
        image.set_qt_image("cached")
        assert image.get_qt_image() == "cached"


class TestProjectFiles:
    def test_save_writes_paths_not_objects(self, tmp_path, proj_data):
        target = tmp_path / "out.zmr"
        backend.save_project(str(target), proj_data)
        saved = json.loads(target.read_text())
        assert all(isinstance(e["image"], str) for e in saved["images_data"])
        assert saved["project_name"] == "Demo"

    def test_save_does_not_mutate_input(self, tmp_path, proj_data):
        backend.save_project(str(tmp_path / "out.zmr"), proj_data)
        first = proj_data["images_data"][0]["image"]
        assert isinstance(first, backend.ImageClass)

    def test_round_trip(self, tmp_path, proj_data):
        target = tmp_path / "out.zmr"
        backend.save_project(str(target), proj_data)
        loaded = backend.load_project(str(target))
        assert len(loaded["images_data"]) == 3
        assert isinstance(
            loaded["images_data"][0]["image"], backend.ImageClass
        )
        assert (
            loaded["images_data"][1]["next_points"]
            == (proj_data["images_data"][1]["next_points"])
        )
        assert loaded["images_data"][0]["prev_points"] is None


class TestInterpolation:
    def setup_method(self):
        self.p0 = np.array(triangle(10.0), dtype=np.float32)
        self.p1 = np.array(triangle(20.0), dtype=np.float32)

    @pytest.mark.parametrize("method", ["linear", "log"])
    def test_endpoints(self, method):
        start = backend._interpolate_points(self.p0, self.p1, 0.0, method)
        end = backend._interpolate_points(self.p0, self.p1, 1.0, method)
        assert np.allclose(start, self.p0)
        assert np.allclose(end, self.p1)

    def test_log_midpoint_is_geometric_in_size(self):
        middle = backend._interpolate_points(self.p0, self.p1, 0.5, "log")
        ratio = backend._points_mean_size_ratio(self.p0, middle)
        assert ratio == pytest.approx(2**0.5, rel=1e-4)

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown interpolation"):
            backend._interpolate_points(self.p0, self.p1, 0.5, "cubic")


def test_points_mean_size_ratio():
    small = np.array(triangle(10.0), dtype=np.float32)
    assert backend._points_mean_size_ratio(small, small * 3) == pytest.approx(
        3.0
    )


class TestVideoGenerator:
    def test_supported_video_formats_include_extension_and_fourcc(self):
        formats = backend.get_supported_video_formats()
        assert formats
        assert len(
            {extension for extension, _label, _fourcc in formats}
        ) == len(formats)
        assert all(len(fourcc) == 4 for _ext, _label, fourcc in formats)

    def test_selected_video_format_opens_writer(self, tmp_path):
        proj = make_proj_data(tmp_path)
        selected_format = backend.get_supported_video_formats()[0][0]
        proj["video_data"]["format"] = selected_format
        target = tmp_path / f"selected.{selected_format}"
        generator = backend.VideoGenerator(proj, str(target))
        assert generator.open_video_writer()
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        generator.save_video_frame(frame)
        generator.close_video_writer()
        assert target.is_file() and target.stat().st_size > 0

    def test_total_frames_is_fps_times_duration(self, tmp_path):
        generator = backend.VideoGenerator(make_proj_data(tmp_path), "")
        success, error = generator.perform_video_calculations()
        assert success and error is None
        assert generator.get_total_frames() == 10

    @pytest.mark.parametrize(
        ("before", "after", "before_count", "after_count"),
        [(0, 0, 0, 0), (0.25, 0, 2, 0), (0, 0.3, 0, 3), (0.2, 0.3, 2, 3)],
    )
    def test_pause_frames_hold_zoom_endpoints(
        self, tmp_path, before, after, before_count, after_count
    ):
        proj = make_proj_data(tmp_path)
        generator = backend.VideoGenerator(proj, "")
        assert generator.perform_video_calculations() == (True, None)
        zoom_frames = generator._indexes_size_alphas_list.copy()
        proj["video_data"].update(pause_before=before, pause_after=after)
        assert generator.perform_video_calculations() == (True, None)
        frames = generator._indexes_size_alphas_list
        assert frames == (
            [zoom_frames[0]] * before_count
            + zoom_frames
            + [zoom_frames[-1]] * after_count
        )
        assert generator.get_total_frames() == 10 + before_count + after_count
        if before_count and after_count:
            assert np.array_equal(
                generator.generate_video_frame_on_position(0),
                generator.generate_video_frame_on_position(before_count),
            )
            assert np.array_equal(
                generator.generate_video_frame_on_position(len(frames) - 1),
                generator.generate_video_frame_on_position(
                    len(frames) - after_count - 1
                ),
            )

    def test_pause_durations_must_not_be_negative(self, tmp_path):
        proj = make_proj_data(tmp_path)
        proj["video_data"]["pause_before"] = -1
        generator = backend.VideoGenerator(proj, "")
        success, error = generator.perform_video_calculations()
        assert not success and "negative" in error

    def test_zoom_duration_must_produce_a_frame(self, tmp_path):
        proj = make_proj_data(tmp_path)
        proj["video_data"]["duration"] = 0.01
        generator = backend.VideoGenerator(proj, "")
        success, error = generator.perform_video_calculations()
        assert not success and "at least one frame" in error

    def test_writer_preserves_fractional_fps(self, tmp_path):
        proj = make_proj_data(tmp_path)
        proj["video_data"]["FPS"] = 12.5
        target = tmp_path / "fractional.avi"
        generator = backend.VideoGenerator(proj, str(target))
        assert generator.open_video_writer()
        generator.save_video_frame(np.zeros((90, 160, 3), dtype=np.uint8))
        generator.close_video_writer()
        video = cv.VideoCapture(str(target))
        assert video.isOpened()
        assert video.get(cv.CAP_PROP_FPS) == pytest.approx(12.5)
        video.release()

    def test_full_export_writes_pause_frames(self, tmp_path, monkeypatch):
        proj = make_proj_data(tmp_path)
        proj["video_data"].update(pause_before=0.2, pause_after=0.3)
        generator = backend.VideoGenerator(proj, "")
        written = []
        monkeypatch.setattr(generator, "open_video_writer", lambda: True)
        monkeypatch.setattr(generator, "close_video_writer", lambda: None)
        monkeypatch.setattr(
            generator,
            "generate_video_frame",
            lambda index, alpha: (index, alpha),
        )
        monkeypatch.setattr(generator, "save_video_frame", written.append)
        assert generator.generate_full_video() == (True, None)
        assert len(written) == 15
        assert written[:3] == [written[2]] * 3
        assert written[-4:] == [written[-4]] * 4
        assert written[2] != written[-4]

    def test_exported_video_contains_pauses(self, tmp_path, monkeypatch):
        proj = make_proj_data(tmp_path)
        proj["video_data"].update(pause_before=0.2, pause_after=0.3)
        target = tmp_path / "pauses.avi"
        generator = backend.VideoGenerator(proj, str(target))
        monkeypatch.setattr(
            generator,
            "generate_video_frame",
            lambda index, alpha: np.full(
                (90, 160, 3), 32 + int(75 * (index + alpha)), dtype=np.uint8
            ),
        )
        assert generator.generate_full_video() == (True, None)
        video = cv.VideoCapture(str(target))
        assert video.isOpened()
        frames = []
        while True:
            success, frame = video.read()
            if not success:
                break
            frames.append(frame)
        video.release()
        assert len(frames) == 15
        for frame in frames[:3]:
            assert np.mean(frame) == pytest.approx(32, abs=5)
        for frame in frames[-4:]:
            assert np.mean(frame) == pytest.approx(182, abs=5)

    def test_frame_has_video_size(self, tmp_path):
        generator = backend.VideoGenerator(make_proj_data(tmp_path), "")
        generator.perform_video_calculations()
        frame = generator.generate_video_frame_on_position(5)
        assert frame.shape[:2] == IMAGE_SIZE[::-1]

    def test_invalid_position_returns_none(self, tmp_path):
        generator = backend.VideoGenerator(make_proj_data(tmp_path), "")
        generator.perform_video_calculations()
        assert generator.generate_video_frame_on_position(-1) is None
        assert generator.generate_video_frame_on_position(99) is None

    def test_decreasing_zoom_is_an_error(self, tmp_path):
        proj = make_proj_data(tmp_path, growth=0.5)
        generator = backend.VideoGenerator(proj, "")
        success, error = generator.perform_video_calculations()
        assert not success
        assert "increasing" in error

    def test_generate_full_video_writes_file(self, tmp_path):
        target = tmp_path / "out.avi"
        generator = backend.VideoGenerator(
            make_proj_data(tmp_path), str(target)
        )
        success, _error = generator.generate_full_video()
        generator.close_video_writer()
        assert success
        assert target.stat().st_size > 0


def test_create_blended_frame_blend_extremes_match_inputs(tmp_path):
    proj = make_proj_data(tmp_path)
    first = backend.create_blended_frame(proj, 0, 0.0, 0.0)
    again = backend.create_blended_frame(proj, 0, 0.0, 0.0)
    assert first.shape[:2] == IMAGE_SIZE[::-1]
    assert np.array_equal(first, again)


def test_auto_align_images_finds_points_for_identical_images(tmp_path):
    paths = write_images(tmp_path, 1) * 2
    width, height = IMAGE_SIZE
    entries = [
        {
            "image": backend.ImageClass(str(p)),
            "frame": [[0, 0], [width, height]],
        }
        for p in paths
    ]
    proj = {
        "video_data": {"size": [width, height]},
        "images_data": entries,
    }
    assert backend.auto_align_images(proj, 0)
    next_points = np.asarray(entries[0]["next_points"])
    prev_points = np.asarray(entries[1]["prev_points"])
    assert next_points.shape == prev_points.shape == (3, 2)
    assert np.allclose(next_points, prev_points, atol=1.0)
