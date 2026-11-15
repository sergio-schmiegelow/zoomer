import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtTest import QTest

from conftest import write_images
from zoomer import widgets
from zoomer.backend import get_supported_video_formats

POINTS = [(50.0, 40.0), (150.0, 40.0), (100.0, 110.0)]


@pytest.fixture
def image_path(tmp_path):
    return write_images(tmp_path, 1, size=(200, 150))[0]


@pytest.fixture
def editor(qapp, image_path):
    widget = widgets.ImageMarkersEditor(
        str(image_path), (0, 0), 200, 200 / 150, POINTS
    )
    widget.resize(480, 360)
    widget.show()
    widget.zoom_all()
    yield widget
    widget.close()


def mouse_event(kind, position, buttons=Qt.MouseButton.LeftButton):
    button = (
        Qt.MouseButton.LeftButton
        if kind != QEvent.Type.MouseMove
        else Qt.MouseButton.NoButton
    )
    return QMouseEvent(
        kind, position, button, buttons, Qt.KeyboardModifier.NoModifier
    )


class TestImageMarkersEditor:
    def test_rejects_wrong_point_count(self, qapp, image_path):
        with pytest.raises(ValueError, match="three points"):
            widgets.ImageMarkersEditor(
                str(image_path), (0, 0), 200, 1.0, POINTS[:2]
            )

    def test_rejects_missing_image(self, qapp, tmp_path):
        with pytest.raises(ValueError, match="Unable to load"):
            widgets.ImageMarkersEditor(
                str(tmp_path / "none.png"), (0, 0), 200, 1.0, POINTS
            )

    def test_set_points_replaces_markers(self, editor):
        editor.set_points([(1, 2), (3, 4), (5, 6)])
        assert [(p.x(), p.y()) for p in editor.points] == [
            (1, 2),
            (3, 4),
            (5, 6),
        ]

    def test_marker_thickness_is_clamped_to_supported_range(self, editor):
        editor.set_marker_thickness(7)
        assert editor.cfg_marker_thickness == 7
        editor.set_marker_thickness(0)
        assert editor.cfg_marker_thickness == 1
        editor.set_marker_thickness(11)
        assert editor.cfg_marker_thickness == 10

    def test_coordinate_round_trip(self, editor):
        point = QPointF(37.5, 80.25)
        back = editor.widget_to_image(editor.image_to_widget(point))
        assert (back.x(), back.y()) == pytest.approx((37.5, 80.25))

    def test_zoom_to_frame_fits_frame(self, editor):
        editor.zoom_to_frame()
        top_left = editor.image_to_widget(QPointF(0, 0))
        bottom_right = editor.image_to_widget(QPointF(200, 150))
        assert top_left.x() >= 0 and top_left.y() >= 0
        assert bottom_right.x() <= editor.width()
        assert bottom_right.y() <= editor.height()

    def test_zoom_to_points_is_closer_than_zoom_all(self, editor):
        editor.zoom_all()
        overview = editor.scale
        editor.zoom_to_points()
        assert editor.scale > overview

    def test_dragging_a_point_emits_new_coordinates(self, editor):
        received = []
        editor.points_changed.connect(received.append)
        start = editor.image_to_widget(editor.points[0])
        end = start + QPointF(30, 20)
        editor.mousePressEvent(
            mouse_event(QEvent.Type.MouseButtonPress, start)
        )
        editor.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, end))
        editor.mouseReleaseEvent(
            mouse_event(
                QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton
            )
        )
        expected = editor.widget_to_image(end)
        assert received[-1][0] == pytest.approx((expected.x(), expected.y()))
        assert received[-1][1:] == POINTS[1:]

    def test_dragging_empty_space_pans(self, editor):
        pan = QPointF(editor.pan)
        start = QPointF(5, 5)
        editor.mousePressEvent(
            mouse_event(QEvent.Type.MouseButtonPress, start)
        )
        editor.mouseMoveEvent(
            mouse_event(QEvent.Type.MouseMove, start + QPointF(12, 7))
        )
        assert editor.pan - pan == QPointF(12, 7)

    def test_wheel_zooms_around_cursor(self, editor):
        cursor = QPointF(200, 150)
        before = editor.widget_to_image(cursor)
        scale = editor.scale
        editor.wheelEvent(
            QWheelEvent(
                cursor,
                cursor,
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
        )
        after = editor.widget_to_image(cursor)
        assert editor.scale > scale
        assert (after.x(), after.y()) == pytest.approx(
            (before.x(), before.y())
        )

    def test_crosshair_flag_is_stored(self, editor):
        editor.cfg_frame_crosshair_enabled = False
        editor.update()
        assert editor.cfg_frame_crosshair_enabled is False

    def test_alignment_crosses_have_no_antialiased_color_pixels(
        self, qapp, tmp_path
    ):
        image_path = tmp_path / "flat.png"
        image = QImage(120, 120, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        image.save(str(image_path))
        editor = widgets.ImageMarkersEditor(
            str(image_path),
            (0, 0),
            120,
            1.0,
            [(60, 60), (20, 20), (100, 20)],
        )
        editor.resize(240, 240)
        editor.cfg_frame_crosshair_enabled = False
        editor.show()
        qapp.processEvents()
        editor._marker_animation_clock.restart()
        rendered = editor.grab().toImage()
        marker_position = editor.image_to_widget(editor.points[0])
        center_x = round(marker_position.x())
        center_y = round(marker_position.y())
        colored_pixels = []
        for y in range(center_y - 12, center_y + 13):
            for x in range(center_x - 12, center_x + 13):
                pixel = rendered.pixelColor(x, y)
                if pixel.red() > pixel.green() and pixel.red() > pixel.blue():
                    colored_pixels.append(pixel.name())
        assert colored_pixels
        assert set(colored_pixels) == {"#ff7777"}
        arm_pixels = [
            rendered.pixelColor(center_x + 5, center_y + offset)
            for offset in range(-3, 3)
        ]
        assert all(
            pixel.red() == pixel.green() == pixel.blue()
            for pixel in arm_pixels[:2] + arm_pixels[4:]
        )
        assert [pixel.name() for pixel in arm_pixels[2:4]] == [
            "#ff7777",
            "#ff7777",
        ]
        tip_pixels = [
            rendered.pixelColor(center_x + offset, center_y)
            for offset in (8, 9)
        ]
        assert all(
            pixel.red() == pixel.green() == pixel.blue()
            and pixel != QColor("white")
            for pixel in tip_pixels
        )
        assert rendered.pixelColor(center_x + 10, center_y) == QColor("white")
        editor.close()


class TestSliders:
    def test_fusion_step_clamps_and_emits(self, qapp):
        slider = widgets.FusionStepSlider()
        slider.set_range(0, 100)
        received = []
        slider.value_changed.connect(received.append)
        slider.set_value(30)
        slider.set_value(500)
        assert received == [30, 100]
        assert slider.value() == 100

    def test_alpha_range_orders_and_clamps(self, qapp):
        slider = widgets.AlphaRangeSlider()
        slider.set_values(90, 10)
        assert slider.values == (10, 90)
        slider.set_values(-5, 250)
        assert slider.values == (0, 100)


class TestImageFilesOrganizer:
    def test_accepts_images_and_refuses_other_files(self, qapp, tmp_path):
        image = write_images(tmp_path, 1)[0]
        text = tmp_path / "notes.txt"
        text.write_text("not an image")
        organizer = widgets.ImageFilesOrganizer()
        received = []
        organizer.image_files_changed.connect(received.append)
        organizer.add_image_files([str(image), str(text)])
        assert organizer.image_list.count() == 1
        assert received == [[str(image.resolve())]]

    def test_ignores_duplicates(self, qapp, tmp_path):
        image = write_images(tmp_path, 1)[0]
        organizer = widgets.ImageFilesOrganizer()
        organizer.add_image_files([str(image)])
        organizer.add_image_files([str(image)])
        assert organizer.image_list.count() == 1

    def test_delete_key_removes_selection(self, qapp, tmp_path):
        organizer = widgets.ImageFilesOrganizer()
        organizer.add_image_files([str(p) for p in write_images(tmp_path, 2)])
        received = []
        organizer.image_files_changed.connect(received.append)
        organizer.image_list.setCurrentRow(0)
        organizer.image_list.keyPressEvent(
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Delete,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        assert organizer.image_list.count() == 1
        assert len(received[-1]) == 1

    def test_highlight_makes_pair_bold(self, qapp, tmp_path):
        paths = [str(p) for p in write_images(tmp_path, 3)]
        organizer = widgets.ImageFilesOrganizer()
        organizer.add_image_files(paths)
        organizer.set_highlighted_paths(paths[:2])
        bold = [organizer.image_list.item(i).font().bold() for i in range(3)]
        assert bold == [True, True, False]


class TestVideoPreviewWidget:
    @pytest.fixture
    def preview(self, qapp):
        widget = widgets.VideoPreviewWidget()
        widget.show()
        yield widget
        widget.close()

    def test_controls_move_the_slider(self, preview):
        preview.set_video(5, 10, lambda position: None)
        preview.end_button.click()
        assert preview.slider.value() == 4
        preview.previous_button.click()
        assert preview.slider.value() == 3
        preview.next_button.click()
        assert preview.slider.value() == 4
        preview.start_button.click()
        assert preview.slider.value() == 0

    def test_requests_frame_for_slider_position(self, preview):
        requested = []
        preview.set_video(5, 10, lambda p: requested.append(p))
        preview.slider.setValue(3)
        assert requested[-1] == 3

    def test_playback_runs_to_the_end_and_stops(self, preview):
        preview.set_video(5, 50, lambda position: None)
        preview.play()
        assert preview.is_playing()
        QTest.qWait(500)
        assert preview.slider.value() == 4
        assert not preview.is_playing()

    def test_pause_stops_playback(self, preview):
        preview.set_video(100, 20, lambda position: None)
        preview.play()
        preview.pause()
        assert not preview.is_playing()

    def test_slider_is_enabled_when_export_state_clears(self, preview):
        preview.set_video(5, 10, lambda position: None)
        preview.set_exporting(True)
        assert not preview.slider.isEnabled()
        preview.set_exporting(False)
        assert preview.slider.isEnabled()
        preview.slider.setValue(3)
        assert preview.slider.value() == 3

    def test_error_disables_controls_and_shows_message(self, preview):
        preview.set_video(5, 10, lambda position: None)
        preview.set_error("broken")
        assert preview.canvas.text() == "broken"
        assert not preview.slider.isEnabled()
        assert not preview.play_button.isEnabled()


class TestVideoSettingsDialog:
    def test_returns_initial_values(self, qapp):
        selected_format = get_supported_video_formats()[0][0]
        data = {
            "format": selected_format,
            "size": (1280, 720),
            "FPS": 24,
            "duration": 5,
            "interpolation_method": "linear",
        }
        settings = widgets.VideoSettingsDialog(data).settings()
        assert settings == {
            "format": selected_format,
            "size": (1280, 720),
            "FPS": 24,
            "duration": 5.0,
            "interpolation_method": "linear",
        }

    def test_custom_size(self, qapp):
        settings = widgets.VideoSettingsDialog(
            {"size": (1000, 500)}
        ).settings()
        assert settings["size"] == (1000, 500)

    def test_project_mode_has_name_field(self, qapp):
        dialog = widgets.NewProjectDialog({}, project_name="  My zoom ")
        assert dialog.project_name() == "My zoom"
        assert isinstance(dialog.video_settings, widgets.VideoSettingsWidget)

    def test_video_settings_dialog_embeds_shared_widget(self, qapp):
        dialog = widgets.VideoSettingsDialog({})
        assert isinstance(dialog.video_settings, widgets.VideoSettingsWidget)

    def test_format_options_match_runtime_probe(self, qapp):
        expected = [entry[0] for entry in get_supported_video_formats()]
        settings = widgets.VideoSettingsWidget({})
        actual = [
            settings.video_format_combo.itemData(index)
            for index in range(settings.video_format_combo.count())
        ]
        assert actual == expected


def test_load_oriented_image_caches_qt_image(qapp, tmp_path):
    from zoomer.backend import ImageClass

    image = ImageClass(str(write_images(tmp_path, 1)[0]))
    first = widgets.load_oriented_image(image)
    assert not first.isNull()
    assert image.get_qt_image() is first
    assert widgets.load_oriented_image(image) is first
