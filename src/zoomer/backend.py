import json
import tempfile
from functools import lru_cache
from pathlib import Path

import cv2 as cv
import numpy as np

NUM_FRAMES = 100
CROSS_SIZE = 10
CROSS_THICKNESS = 2
CROSS_COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]  # Red, Green, Blue
FRAME_COLOR = [255, 0, 0]  # Blue
FRAME_THICKNESS = 2
BLEND_RANGE_DETECTION_RESOLUTION = 0.01

VIDEO_FORMAT_CANDIDATES = (
    ("avi", "AVI", ("XVID", "MJPG", "DIVX", "HFYU")),
    ("mp4", "MP4", ("mp4v",)),
    ("m4v", "M4V", ("mp4v",)),
    ("mov", "QuickTime MOV", ("mp4v",)),
    ("mkv", "Matroska MKV", ("XVID", "mp4v", "MJPG")),
    ("webm", "WebM", ("VP80", "VP90")),
    ("wmv", "Windows Media WMV", ("WMV2", "WMV1")),
    ("flv", "Flash Video FLV", ("FLV1",)),
    ("ts", "MPEG Transport Stream", ("MP2V",)),
    ("mts", "AVCHD MTS", ("MP2V",)),
    ("3gp", "3GPP", ("mp4v",)),
    ("mjpeg", "Motion JPEG", ("MJPG",)),
    ("mpg", "MPEG Program Stream", ("PIM1",)),
    ("mpeg", "MPEG Video", ("PIM1",)),
    ("vob", "DVD Video VOB", ("MP2V",)),
    ("asf", "Advanced Systems Format", ("WMV2",)),
    ("nut", "NUT Container", ("FFV1",)),
    ("dv", "DV Video", ("DVSD",)),
    ("y4m", "YUV4MPEG2", ("I420",)),
)


@lru_cache(maxsize=1)
def get_supported_video_formats() -> tuple[tuple[str, str, str], ...]:
    """Return common container formats this OpenCV build can encode."""
    logging = getattr(getattr(cv, "utils", None), "logging", None)
    previous_log_level = logging.getLogLevel() if logging else None
    if logging:
        logging.setLogLevel(logging.LOG_LEVEL_SILENT)
    supported_formats = []
    try:
        for extension, label, fourcc_options in VIDEO_FORMAT_CANDIDATES:
            fourcc = _probe_video_format(extension, fourcc_options)
            if fourcc:
                supported_formats.append(
                    (extension, f"{label} (*.{extension})", fourcc)
                )
    finally:
        if logging:
            logging.setLogLevel(previous_log_level)
    return tuple(supported_formats)


def _probe_video_format(extension: str, fourcc_options: tuple[str, ...]):
    for fourcc in fourcc_options:
        writer = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                filename = Path(directory) / f"probe.{extension}"
                writer = cv.VideoWriter(
                    str(filename),
                    cv.VideoWriter_fourcc(*fourcc),
                    25,
                    (32, 32),
                )
                if not writer.isOpened():
                    continue
                writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
                writer.release()
                writer = None
                if filename.is_file() and filename.stat().st_size > 0:
                    return fourcc
        except (OSError, cv.error):
            pass
        finally:
            if writer is not None:
                writer.release()
    return None


# -------------------------------------------------------------------------
def _polygon_is_inside_polygon(
    inner_polygon: np.ndarray, outer_polygon: np.ndarray
) -> bool:
    # Check if all points of the inner polygon are inside the outer polygon.
    for point in inner_polygon:
        if cv.pointPolygonTest(outer_polygon, (point[0], point[1]), False) < 0:
            return False
    return True


# -------------------------------------------------------------------------
class ImageClass:
    # ---------------------------------------------------------------------
    def __init__(self, filename: str):
        self._image_path = Path(filename)
        if not self._image_path.exists():
            raise ValueError(f"Image file does not exist: {filename}")
        self._image_path = self._image_path.resolve()
        self._cv_image = cv.imread(str(self._image_path))
        self._qt_image = None

    # ---------------------------------------------------------------------
    def get_image_path(self) -> str:
        return self._image_path

    # ---------------------------------------------------------------------
    def get_cv_image(self) -> np.ndarray:
        return self._cv_image

    # ---------------------------------------------------------------------
    def get_qt_image(self):
        return self._qt_image

    # ---------------------------------------------------------------------
    def set_qt_image(self, qt_image):
        self._qt_image = qt_image


# -------------------------------------------------------------------------
def load_config(filename: str) -> dict:
    with open(filename, "r") as f:
        proj_data = json.load(f)
    for image_data in proj_data["images_data"]:
        image_data["image"] = ImageClass(str(image_data["image"]))
    return proj_data


# -------------------------------------------------------------------------
def save_config(filename: str, proj_data: dict) -> None:
    proj_data_copy = dict(proj_data)
    proj_data_copy["images_data"] = []
    for image_data in proj_data["images_data"]:
        image_data_copy = dict(image_data)
        image_object = image_data_copy["image"]
        if isinstance(image_object, ImageClass):
            image_data_copy["image"] = str(image_object.get_image_path())
        proj_data_copy["images_data"].append(image_data_copy)
    with open(filename, "w") as f:
        json.dump(proj_data_copy, f, indent=2)
    return


# -------------------------------------------------------------------------
class _AffineTransformer:
    # ---------------------------------------------------------------------
    def __init__(
        self, start_points: np.ndarray, end_points: np.ndarray
    ) -> None:
        # print(f'DEBUG - start_points: \n{start_points}')
        # print(f'DEBUG - end_points:   \n{end_points}')
        self._start_points = start_points
        self._end_points = end_points
        self.calculate_transform_matrix()

    # ---------------------------------------------------------------------
    def set_start_points(self, start_points: np.ndarray) -> None:
        self._start_points = start_points
        self.calculate_transform_matrix()

    # ---------------------------------------------------------------------
    def set_end_points(self, end_points: np.ndarray) -> None:
        self._end_points = end_points
        self.calculate_transform_matrix()

    # ---------------------------------------------------------------------
    def calculate_transform_matrix(self) -> None:
        # Calculate the affine transformation matrix based on the start
        # and end points.
        self._transform_matrix = cv.getAffineTransform(
            self._start_points.astype(np.float32),
            self._end_points.astype(np.float32),
        )

    # ---------------------------------------------------------------------
    def transformed_image_fills_output_size(
        self, image: np.ndarray, output_size: np.ndarray
    ) -> bool:
        # Check it the transformed image will not leave any blank areas in
        # the output frame of the specified size.
        # Get the corners of the image
        h, w = image.shape[:2]
        original_img_corners_polygon = np.array(
            [[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32
        )
        # Transform the corners
        transformed_img_corners_polygon = cv.transform(
            np.array([original_img_corners_polygon]), self._transform_matrix
        )[0]
        video_corners_polygon = np.array(
            [
                [0, 0],
                [output_size[0], 0],
                [output_size[0], output_size[1]],
                [0, output_size[1]],
            ],
            dtype=np.float32,
        )
        # Check if video_corners_polygon is inside
        # transformed_img_corners_polygon
        return _polygon_is_inside_polygon(
            video_corners_polygon, transformed_img_corners_polygon
        )

    # ---------------------------------------------------------------------
    def transform_image(
        self, image: np.ndarray, output_size: np.ndarray
    ) -> np.ndarray:
        # Apply the affine transformation to an image.
        self.calculate_transform_matrix()
        transformed_image = cv.warpAffine(
            image, self._transform_matrix, (output_size[0], output_size[1])
        )
        return transformed_image

    # ---------------------------------------------------------------------
    def transform_points(self, points: np.ndarray) -> np.ndarray:
        # Apply the affine transformation to a set of points.
        self.calculate_transform_matrix()
        transformed_points = cv.transform(
            np.array([points], dtype=np.float32), self._transform_matrix
        )
        return transformed_points[0]


# -------------------------------------------------------------------------
def convert_3_points_and_frame_to_video_coordinates(
    points: np.ndarray, frame: np.ndarray, video_dims: np.ndarray
) -> np.ndarray:
    out_points = np.zeros(points.shape, dtype=np.float32)
    # print(f'DEBUG - points: \n{points}')
    # print(f'DEBUG - frame: \n{frame}')
    # print(f'DEBUG - video_dims: \n{video_dims}')
    # print(f'DEBUG - out_points: \n{out_points}')
    out_points[:, 0] = (points[:, 0] - frame[0][0]) * (
        video_dims[0] / (frame[1][0] - frame[0][0])
    )
    out_points[:, 1] = (points[:, 1] - frame[0][1]) * (
        video_dims[1] / (frame[1][1] - frame[0][1])
    )
    return out_points


# -------------------------------------------------------------------------
def generate_image_with_markers(
    img: np.ndarray, frame, prev_points: np.ndarray, next_points: np.ndarray
) -> np.ndarray:
    if prev_points is not None:
        for idx, point in enumerate(prev_points):
            # draw a "plus sign" at the previous points
            color = CROSS_COLORS[idx]  # Alternate colors for previous points
            cv.line(
                img,
                (int(point[0]) - CROSS_SIZE, int(point[1])),
                (int(point[0]) + CROSS_SIZE, int(point[1])),
                color,
                CROSS_THICKNESS,
            )
            cv.line(
                img,
                (int(point[0]), int(point[1]) - CROSS_SIZE),
                (int(point[0]), int(point[1]) + CROSS_SIZE),
                color,
                CROSS_THICKNESS,
            )
    if next_points is not None:
        for idx, point in enumerate(next_points):
            # draw a "X sign" at the next points
            color = CROSS_COLORS[idx]  # Alternate colors for next points
            cv.line(
                img,
                (int(point[0]) - CROSS_SIZE, int(point[1]) - CROSS_SIZE),
                (int(point[0]) + CROSS_SIZE, int(point[1]) + CROSS_SIZE),
                color,
                CROSS_THICKNESS,
            )
            cv.line(
                img,
                (int(point[0]) - CROSS_SIZE, int(point[1]) + CROSS_SIZE),
                (int(point[0]) + CROSS_SIZE, int(point[1]) - CROSS_SIZE),
                color,
                CROSS_THICKNESS,
            )
    # plot the frame rectangle
    frame_points = np.array(
        [
            frame[0],
            [frame[1][0], frame[0][1]],
            frame[1],
            [frame[0][0], frame[1][1]],
        ],
        dtype=np.int32,
    )
    cv.polylines(
        img,
        [frame_points],
        isClosed=True,
        color=FRAME_COLOR,
        thickness=FRAME_THICKNESS,
    )
    return img


# -------------------------------------------------------------------------
def _convert_img_points_to_video_dimensions(
    points: np.ndarray, frame: np.ndarray, video_dims: np.ndarray
) -> np.ndarray:
    # Convert points from the source frame to the destination frame using
    # an affine transformation.
    frame_affine_points = np.array(
        [frame[0], [frame[1][0], frame[0][1]], frame[1]], dtype=np.float32
    )
    video_dims_affine_points = np.array(
        [[0, 0], [video_dims[0], 0], video_dims], dtype=np.float32
    )
    transform_matrix = cv.getAffineTransform(
        frame_affine_points, video_dims_affine_points
    )
    transformed_points = cv.transform(
        np.array([points], dtype=np.float32), transform_matrix
    )
    return transformed_points[0]


# -------------------------------------------------------------------------
def _convert_video_points_to_image_dimensions(
    points: np.ndarray, frame: np.ndarray, video_dims: np.ndarray
) -> np.ndarray:
    # Convert points from the video frame to the source image frame using
    # an affine transformation.
    video_dims_affine_points = np.array(
        [[0, 0], [video_dims[0], 0], video_dims], dtype=np.float32
    )
    frame_affine_points = np.array(
        [frame[0], [frame[1][0], frame[0][1]], frame[1]], dtype=np.float32
    )
    transform_matrix = cv.getAffineTransform(
        video_dims_affine_points, frame_affine_points
    )
    transformed_points = cv.transform(
        np.array([points], dtype=np.float32), transform_matrix
    )
    return transformed_points[0]


# -------------------------------------------------------------------------
def _extract_video_frame_from_image(
    img: np.ndarray, frame: np.ndarray, video_dims: np.ndarray
) -> np.ndarray:
    # Extract the video frame from the source image using an affine
    # transformation.
    video_dims_affine_points = np.array(
        [[0, 0], [video_dims[0], 0], video_dims], dtype=np.float32
    )
    frame_affine_points = np.array(
        [frame[0], [frame[1][0], frame[0][1]], frame[1]], dtype=np.float32
    )
    transform_matrix = cv.getAffineTransform(
        frame_affine_points, video_dims_affine_points
    )
    video_frame = cv.warpAffine(
        img, transform_matrix, (video_dims[0], video_dims[1])
    )
    return video_frame


# -------------------------------------------------------------------------
def _interpolate_points(
    points0: np.ndarray, points1: np.ndarray, alpha: float
) -> np.ndarray:
    # Interpolate between two sets of points based on the alpha value.
    return (1 - alpha) * points0 + alpha * points1


# -------------------------------------------------------------------------
def _points_mean_size(points: np.ndarray) -> float:
    # Calculate the mean size of a triangle formed by three points.
    return np.mean(
        [
            np.linalg.norm(points[0] - points[1]),
            np.linalg.norm(points[1] - points[2]),
            np.linalg.norm(points[2] - points[0]),
        ]
    )


# -------------------------------------------------------------------------
def _points_mean_size_ratio(points0: np.ndarray, points1: np.ndarray) -> float:
    # Calculate the ratio of the mean sizes of two triangles formed by three
    # points each.
    mean_size0 = _points_mean_size(points0)
    mean_size1 = _points_mean_size(points1)
    return mean_size1 / mean_size0 if mean_size0 != 0 else float("inf")


# -------------------------------------------------------------------------
def _interpolate_points_linear(
    points0: np.ndarray, points1: np.ndarray, alpha: float
) -> np.ndarray:
    # Interpolate between two sets of points linearly based on the alpha value.
    return (1 - alpha) * points0 + alpha * points1


# -------------------------------------------------------------------------
def _interpolate_points_log(
    points0: np.ndarray, points1: np.ndarray, alpha: float
) -> np.ndarray:
    # Interpolate between two sets of points based on the specified
    # interpolation method.
    # Calculate the relative size of the two sets of points
    size_ratio = _points_mean_size_ratio(points0, points1)
    log_size_ratio = np.log(size_ratio)
    interpolated_log_size = alpha * log_size_ratio
    linear_size_ratio = np.exp(interpolated_log_size)
    pg_alpha = (
        (linear_size_ratio - 1) / (size_ratio - 1)
        if size_ratio != 1
        else alpha
    )
    # print(f'DEBUG - size_ratio: {size_ratio}, alpha: {alpha}, '
    #       f'linear_size_ratio: {linear_size_ratio}, pg_alpha: {pg_alpha}')
    return (1 - pg_alpha) * points0 + pg_alpha * points1


# -------------------------------------------------------------------------
def _interpolate_points(
    points0: np.ndarray,
    points1: np.ndarray,
    alpha: float,
    interpolation_method: str = "log",
) -> np.ndarray:
    if interpolation_method == "linear":
        return _interpolate_points_linear(points0, points1, alpha)
    elif interpolation_method == "log":
        return _interpolate_points_log(points0, points1, alpha)
    else:
        raise ValueError(
            f"Unknown interpolation method: {interpolation_method}"
        )


# -------------------------------------------------------------------------
def _create_intermediate_frame(
    video_size: np.ndarray,
    img0: np.ndarray,
    points0: np.ndarray,
    frame0: np.ndarray,
    points1: np.ndarray,
    frame1: np.ndarray,
    size_alpha: float,
    check_fill: bool = False,
    interpolation_method: str = "log",
) -> np.ndarray:
    # Convert the points0 to frame0 coordinates
    video_transformed_points0 = _convert_img_points_to_video_dimensions(
        points0, frame0, video_size
    )
    # Convert the points1 to frame1 coordinates
    video_transformed_points1 = _convert_img_points_to_video_dimensions(
        points1, frame1, video_size
    )
    # Interpolate the points between the two frames
    interpolated_points = _interpolate_points(
        video_transformed_points0,
        video_transformed_points1,
        size_alpha,
        interpolation_method,
    )
    # Create an affine transformer for the first image
    img_transformer = _AffineTransformer(points0, interpolated_points)
    if check_fill:
        return img_transformer.transformed_image_fills_output_size(
            img0, video_size
        )
    # Transform the first image to the intermediate frame
    intermediate_frame = img_transformer.transform_image(img0, video_size)
    return intermediate_frame


# -------------------------------------------------------------------------
def get_blend_alpha_range(
    video_size: np.ndarray,
    img0: np.ndarray,
    points0: np.ndarray,
    frame0: np.ndarray,
    img1: np.ndarray,
    points1: np.ndarray,
    frame1: np.ndarray,
) -> tuple:
    # Scan the size_alpha to find the range where both images can fill the
    # output frame
    min_size_alpha_for_blending = 1.0
    max_size_alpha_for_blending = 0.0
    for test_size_alpha in np.linspace(
        0, 1, num=int(1 / BLEND_RANGE_DETECTION_RESOLUTION) + 1
    ):
        intermediate_frame0_fills = _create_intermediate_frame(
            video_size,
            img0,
            points0,
            frame0,
            points1,
            frame1,
            test_size_alpha,
            check_fill=True,
        )
        intermediate_frame1_fills = _create_intermediate_frame(
            video_size,
            img1,
            points1,
            frame1,
            points0,
            frame0,
            1 - test_size_alpha,
            check_fill=True,
        )
        print(
            f"DEBUG - test_size_alpha = {test_size_alpha}, "
            f"intermediate_frame0_fills = {intermediate_frame0_fills}, "
            f"intermediate_frame1_fills = {intermediate_frame1_fills}"
        )
        if intermediate_frame0_fills and intermediate_frame1_fills:
            if test_size_alpha < min_size_alpha_for_blending:
                min_size_alpha_for_blending = test_size_alpha
            if test_size_alpha > max_size_alpha_for_blending:
                max_size_alpha_for_blending = test_size_alpha
    return min_size_alpha_for_blending, max_size_alpha_for_blending


# -------------------------------------------------------------------------
def create_blended_frame(
    proj_data: dict,
    index: int,
    size_alpha: float,
    blend_alpha: float,
    interpolation_method: str = "log",
) -> np.ndarray:
    video_size = np.array(proj_data["video_data"]["size"], dtype=np.int32)

    img_prev = proj_data["images_data"][index]["image"].get_cv_image()
    frame_prev = np.array(
        proj_data["images_data"][index]["frame"], dtype=np.float32
    )
    prev_next_points = np.array(
        proj_data["images_data"][index]["next_points"], dtype=np.float32
    )

    img_next = proj_data["images_data"][index + 1]["image"].get_cv_image()
    frame_next = np.array(
        proj_data["images_data"][index + 1]["frame"], dtype=np.float32
    )
    next_prev_points = np.array(
        proj_data["images_data"][index + 1]["prev_points"], dtype=np.float32
    )

    intermediate_frame0 = _create_intermediate_frame(
        video_size,
        img_prev,
        prev_next_points,
        frame_prev,
        next_prev_points,
        frame_next,
        size_alpha,
        interpolation_method=interpolation_method,
    )
    intermediate_frame1 = _create_intermediate_frame(
        video_size,
        img_next,
        next_prev_points,
        frame_next,
        prev_next_points,
        frame_prev,
        1 - size_alpha,
        interpolation_method=interpolation_method,
    )
    correlation = _calculate_frames_correlation(
        intermediate_frame0, intermediate_frame1
    )
    print(f"DEBUG - frames correlation: {correlation}")
    # Blend the two intermediate frames
    blended_frame = cv.addWeighted(
        intermediate_frame0,
        1 - blend_alpha,
        intermediate_frame1,
        blend_alpha,
        0,
    )
    return blended_frame


# -------------------------------------------------------------------------
def _calculate_frames_correlation(
    frame0: np.ndarray, frame1: np.ndarray
) -> float:
    red_correlation = np.corrcoef(
        frame0[:, :, 0].flatten(), frame1[:, :, 0].flatten()
    )[0, 1]
    green_correlation = np.corrcoef(
        frame0[:, :, 1].flatten(), frame1[:, :, 1].flatten()
    )[0, 1]
    blue_correlation = np.corrcoef(
        frame0[:, :, 2].flatten(), frame1[:, :, 2].flatten()
    )[0, 1]
    correlation = (red_correlation + green_correlation + blue_correlation) / 3
    print(f"DEBUG - correlation: {correlation}")
    return correlation


# -------------------------------------------------------------------------
def auto_align_images(
    proj_data: dict, index: int, use_only_frame=True
) -> np.ndarray:
    # Perform alignment for the image at the given index in the proj_data.
    # Returns the aligned points as a numpy array of shape (3, 2).
    img0 = proj_data["images_data"][index]["image"].get_cv_image()
    img1 = proj_data["images_data"][index + 1]["image"].get_cv_image()
    if use_only_frame:
        video_dims = proj_data["video_data"]["size"]
        frame0 = proj_data["images_data"][index]["frame"]
        frame1 = proj_data["images_data"][index + 1]["frame"]
        img0 = _extract_video_frame_from_image(img0, frame0, video_dims)
        img1 = _extract_video_frame_from_image(img1, frame1, video_dims)

    img0_next_points, img1_prev_points = sift_alignment(img0, img1)

    if use_only_frame:
        img0_next_points = _convert_video_points_to_image_dimensions(
            img0_next_points, frame0, video_dims
        )
        img1_prev_points = _convert_video_points_to_image_dimensions(
            img1_prev_points, frame1, video_dims
        )
    proj_data["images_data"][index]["next_points"] = img0_next_points
    proj_data["images_data"][index + 1]["prev_points"] = img1_prev_points
    return True


# -------------------------------------------------------------------------
def sift_alignment(img0, img1) -> np.ndarray:
    # Perform SIFT feature detection and matching between img0 and img1.
    # Return the matched points for alignment or none if not enough matches
    # are found.
    sift = cv.SIFT_create()

    kp0, des0 = sift.detectAndCompute(img0, None)
    kp1, des1 = sift.detectAndCompute(img1, None)

    matcher = cv.BFMatcher()
    matches = matcher.knnMatch(des0, des1, k=2)
    if len(matches) < 3:
        print("DEBUG - Not enough matches found.")
        return None, None
    print(f"DEBUG - Total matches found: {len(matches)}")
    # Sort matches based on distance, best matches first
    matches = sorted(matches, key=lambda x: x[0].distance)

    img0_first_point = kp0[matches[0][0].queryIdx].pt
    img1_first_point = kp1[matches[0][0].trainIdx].pt
    img0_second_point = kp0[matches[1][0].queryIdx].pt
    img1_second_point = kp1[matches[1][0].trainIdx].pt
    img0_third_point = kp0[matches[2][0].queryIdx].pt
    img1_third_point = kp1[matches[2][0].trainIdx].pt

    img0_next_points = np.array(
        [img0_first_point, img0_second_point, img0_third_point],
        dtype=np.float32,
    )
    img1_prev_points = np.array(
        [img1_first_point, img1_second_point, img1_third_point],
        dtype=np.float32,
    )

    return img0_next_points, img1_prev_points


# -------------------------------------------------------------------------
def orb_alignment(img0, img1) -> np.ndarray:
    # Perform ORB feature detection and matching between img0 and img1.
    # Return the matched points for alignment or none if not enough matches
    # are found.
    orb = cv.ORB_create()

    kp0, des0 = orb.detectAndCompute(img0, None)
    kp1, des1 = orb.detectAndCompute(img1, None)

    matcher = cv.DescriptorMatcher_create(
        cv.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING
    )
    matches = matcher.match(des0, des1, None)

    if len(matches) < 3:
        print("DEBUG - Not enough matches found.")
        return None, None
    print(f"DEBUG - Total matches found: {len(matches)}")
    matches = sorted(matches, key=lambda x: x.distance)

    img0_first_point = kp0[matches[0].queryIdx].pt
    img1_first_point = kp1[matches[0].trainIdx].pt
    img0_second_point = kp0[matches[1].queryIdx].pt
    img1_second_point = kp1[matches[1].trainIdx].pt
    img0_third_point = kp0[matches[2].queryIdx].pt
    img1_third_point = kp1[matches[2].trainIdx].pt

    img0_next_points = np.array(
        [img0_first_point, img0_second_point, img0_third_point],
        dtype=np.float32,
    )
    img1_prev_points = np.array(
        [img1_first_point, img1_second_point, img1_third_point],
        dtype=np.float32,
    )

    return img0_next_points, img1_prev_points


# -------------------------------------------------------------------------
def _calculate_zoom_array(proj_data: dict) -> tuple:
    current_zoom = 1.0
    img_zooms = [1.0]
    video_dims = np.array(proj_data["video_data"]["size"], dtype=np.int32)
    for i in range(len(proj_data["images_data"]) - 1):
        frame0 = np.array(
            proj_data["images_data"][i]["frame"], dtype=np.float32
        )
        next_points0 = np.array(
            proj_data["images_data"][i]["next_points"], dtype=np.float32
        )

        frame1 = np.array(
            proj_data["images_data"][i + 1]["frame"], dtype=np.float32
        )
        prev_points1 = np.array(
            proj_data["images_data"][i + 1]["prev_points"], dtype=np.float32
        )

        converted_points0 = _convert_img_points_to_video_dimensions(
            next_points0, frame0, video_dims
        )
        converted_points1 = _convert_img_points_to_video_dimensions(
            prev_points1, frame1, video_dims
        )

        pair_ratio = _points_mean_size_ratio(
            converted_points0, converted_points1
        )
        current_zoom *= pair_ratio
        img_zooms.append(current_zoom)
        print(f"DEBUG - Pair ratio for images {i} and {i + 1}: {pair_ratio}")
        print(f"Zoom for image {i}:{current_zoom}")
    # if img_zooms is not an increase sequence, return error
    if not np.all(np.diff(img_zooms) >= 0):
        error_msg = "Image zooms are not in increasing order"
        print(f"ERROR - {error_msg}")
        return None, error_msg
    img_zooms = np.array(img_zooms)
    print("Image zooms:", img_zooms)
    return img_zooms, None


# -------------------------------------------------------------------------
def _calculate_frames_fusion_and_size_alpha(proj_data: dict):
    zoom_array, error_msg = _calculate_zoom_array(proj_data)
    if error_msg is not None:
        return None, error_msg
    log_zoom_array = np.log(zoom_array)
    total_frames = int(
        proj_data["video_data"]["FPS"] * proj_data["video_data"]["duration"]
    )
    frames_logs_zooms = np.linspace(0, log_zoom_array[-1], num=total_frames)
    print("DEBUG - Frames logs zooms:", frames_logs_zooms)
    indexes_steps_list = []
    for frame_log_zoom in frames_logs_zooms:
        if frame_log_zoom <= log_zoom_array[0]:
            indexes_steps_list.append((0, 0.0))
            continue
        # Find the index of the log_zoom_array less or equal to frame_log_zoom
        first_index = (
            np.searchsorted(log_zoom_array, frame_log_zoom, side="left") - 1
        )
        step = (frame_log_zoom - log_zoom_array[first_index]) / (
            log_zoom_array[first_index + 1] - log_zoom_array[first_index]
        )
        indexes_steps_list.append((first_index, step))
    return indexes_steps_list, None


# -------------------------------------------------------------------------
class VideoGenerator:
    # ---------------------------------------------------------------------
    def __init__(self, proj_data: dict, filename: str):
        self.proj_data = proj_data
        self.filename = filename

    # ---------------------------------------------------------------------
    def set_video_filename(self, filename: str):
        self.filename = filename

    # ---------------------------------------------------------------------
    def open_video_writer(self):
        selected_format = self.proj_data["video_data"].get("format", "avi")
        format_info = next(
            (
                supported_format
                for supported_format in get_supported_video_formats()
                if supported_format[0] == selected_format
            ),
            None,
        )
        if format_info is None:
            raise ValueError(
                f"Video format is not supported by this OpenCV build: "
                f"{selected_format}"
            )
        _extension, _label, fourcc = format_info
        self._video_writer = cv.VideoWriter(
            self.filename,
            cv.VideoWriter_fourcc(*fourcc),
            int(self.proj_data["video_data"]["FPS"]),
            tuple(
                np.array(self.proj_data["video_data"]["size"], dtype=np.int32)
            ),
        )
        if not self._video_writer.isOpened():
            print("ERROR - Failed to open video writer")
            return False
        return True

    # ---------------------------------------------------------------------
    def save_video_frame(self, frame):
        if hasattr(self, "_video_writer") and self._video_writer.isOpened():
            self._video_writer.write(frame)

    # ---------------------------------------------------------------------
    def close_video_writer(self):
        if hasattr(self, "_video_writer") and self._video_writer.isOpened():
            self._video_writer.release()

    # ---------------------------------------------------------------------
    def perform_video_calculations(self):
        self._indexes_size_alphas_list, error_msg = (
            _calculate_frames_fusion_and_size_alpha(self.proj_data)
        )
        if error_msg:
            print("ERROR -", error_msg)
            return False, error_msg
        return True, None

    # ---------------------------------------------------------------------
    def get_total_frames(self):
        return len(self._indexes_size_alphas_list)

    # ---------------------------------------------------------------------
    def generate_video_frame_on_position(self, position):
        if position < 0 or position >= len(self._indexes_size_alphas_list):
            print("ERROR - Invalid position")
            return None
        first_index, size_alpha = self._indexes_size_alphas_list[position]
        return self.generate_video_frame(first_index, size_alpha)

    # ---------------------------------------------------------------------
    def generate_video_frame(self, first_index, size_alpha):
        print(
            f"DEBUG - Frame first index: {first_index}, "
            f"size_alpha: {size_alpha}"
        )
        interpolation_method = self.proj_data["video_data"].get(
            "interpolation_method", "log"
        )
        blend_alpha_range = self.proj_data["images_data"][first_index].get(
            "alpha_range", (0.0, 1.0)
        )
        blend_alpha = (size_alpha - blend_alpha_range[0]) / (
            blend_alpha_range[1] - blend_alpha_range[0]
        )
        blend_alpha = np.clip(blend_alpha, 0.0, 1.0)
        return create_blended_frame(
            self.proj_data,
            index=first_index,
            size_alpha=size_alpha,
            blend_alpha=blend_alpha,
            interpolation_method=interpolation_method,
        )

    # ---------------------------------------------------------------------
    def generate_full_video(self):
        success, error_msg = self.perform_video_calculations()
        if not success:
            return False, error_msg
        if not self.open_video_writer():
            return False, "Failed to open video"
        for first_index, size_alpha in self._indexes_size_alphas_list:
            video_frame = self.generate_video_frame(first_index, size_alpha)
            self.save_video_frame(video_frame)
        self.close_video_writer()
        return True, None


# -------------------------------------------------------------------------
if __name__ == "__main__":
    proj_file = "seed.zmr"
    proj_data = load_config(proj_file)
    video_generator = VideoGenerator(proj_data, "seed.avi")
    video_generator.generate_full_video()
    quit()

    proj_file = "prat.json"
    proj_data = load_config(proj_file)
    save_config("out.json", proj_data)

    video_dims = np.array(proj_data["video_data"]["size"], dtype=np.int32)

    # Extract the first images pair data from the configuration dictionary
    img0 = proj_data["images_data"][0]["image"]
    frame0 = np.array(proj_data["images_data"][0]["frame"], dtype=np.float32)
    next_points0 = np.array(
        proj_data["images_data"][0]["next_points"], dtype=np.float32
    )

    img1 = proj_data["images_data"][1]["image"]
    frame1 = np.array(proj_data["images_data"][1]["frame"], dtype=np.float32)
    prev_points1 = np.array(
        proj_data["images_data"][1]["prev_points"], dtype=np.float32
    )

    min_blend_alpha, max_blend_alpha = get_blend_alpha_range(
        video_dims,
        img0.get_cv_image(),
        next_points0,
        frame0,
        img1.get_cv_image(),
        prev_points1,
        frame1,
    )
    print(
        f"DEBUG - blend_alpha_range = {min_blend_alpha} to {max_blend_alpha}"
    )
    for size_alpha in np.linspace(0, 1, num=NUM_FRAMES):
        blend_alpha = (size_alpha - min_blend_alpha) / (
            max_blend_alpha - min_blend_alpha
        )
        blend_alpha = np.clip(blend_alpha, 0.0, 1.0)
        print(
            f"DEBUG - size_alpha = {size_alpha}, blend_alpha = {blend_alpha}"
        )
        blended_frame = create_blended_frame(
            proj_data, 0, size_alpha, blend_alpha
        )

        cv.imshow("Blended Frame", blended_frame)
        cv.waitKey(1)

    cv.waitKey(0)
    cv.destroyAllWindows()
    quit()

    # Convert the second image's previous points to the video dimensions
    # using an affine transformation
    video_transformed_prev_points1 = _convert_img_points_to_video_dimensions(
        prev_points1, frame1, video_dims
    )

    img0_frame_transformer = _AffineTransformer(
        next_points0, video_transformed_prev_points1
    )

    video_frame0 = img0_frame_transformer.transform_image(
        img0.get_cv_image(), video_dims
    )
    marked_video_frame0 = generate_image_with_markers(
        video_frame0,
        [[0, 0], video_frame0.shape[:2][::-1]],
        None,
        video_transformed_prev_points1,
    )
    cv.imshow("MarkedVideoFrame0", marked_video_frame0)
    cv.waitKey(0)
    cv.destroyAllWindows()
