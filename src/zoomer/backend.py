import json
import tempfile
from functools import lru_cache
from pathlib import Path

import cv2 as cv
import numpy as np
import time
from itertools import combinations

NUM_FRAMES = 100
CROSS_SIZE = 10
CROSS_THICKNESS = 2
CROSS_COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]  # Red, Green, Blue
FRAME_COLOR = [255, 0, 0]  # Blue
FRAME_THICKNESS = 2
BLEND_RANGE_DETECTION_RESOLUTION = 0.005

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
def load_project(filename: str) -> dict:
    with open(filename, "r") as f:
        proj_data = json.load(f)
    project_directory = Path(filename).resolve().parent
    for image_data in proj_data["images_data"]:
        # Relative image paths are relative to the project file
        image_path = project_directory / str(image_data["image"])
        image_data["image"] = ImageClass(str(image_path))
    return proj_data


# -------------------------------------------------------------------------
def save_project(filename: str, proj_data: dict) -> None:
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
def convert_points_and_frame_to_video_coordinates(
    points: np.ndarray, frame: np.ndarray, video_dims: np.ndarray
) -> np.ndarray:
    out_points = np.zeros(points.shape, dtype=np.float32)
    out_points[:, 0] = (points[:, 0] - frame[0][0]) * (
        video_dims[0] / (frame[1][0] - frame[0][0])
    )
    out_points[:, 1] = (points[:, 1] - frame[0][1]) * (
        video_dims[1] / (frame[1][1] - frame[0][1])
    )
    return out_points


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
def _points_mean_size(points: np.ndarray) -> float:
    # Calculate the mean of the distances between all the points
    num_points = len(points)
    distances = []
    for i in range(num_points):
        for j in range(i + 1, num_points):
            distances.append(np.linalg.norm(points[i] - points[j]))

    return np.mean(distances)

# -------------------------------------------------------------------------
def _points_mean_size_ratio(points0: np.ndarray, points1: np.ndarray) -> float:
    # Calculate the ratio of the mean sizes of two triangles formed by three
    # points each.
    mean_size0 = _points_mean_size(points0)
    mean_size1 = _points_mean_size(points1)
    return mean_size1 / mean_size0 if mean_size0 != 0 else float("inf")

# -------------------------------------------------------------------------
def _points_mean_rotation(points0: np.ndarray, points1: np.ndarray) -> float:
    # Calculate the mean rotation between two sets of points forming triangles.
    if len(points0) != len(points1):
        raise ValueError("Point sets must have the same number of points.")
    num_points = len(points0)
    ratios_vector = []
    for idx0 in range(num_points):
        for idx1 in range(idx0 + 1, num_points):
            cpx0 = points0[idx0][0] - points0[idx1][0] + 1j * (points0[idx0][1] - points0[idx1][1])
            cpx1 = points1[idx0][0] - points1[idx1][0] + 1j * (points1[idx0][1] - points1[idx1][1])
            #print(f"DEBUG angle(cpx0): {np.angle(cpx0) / np.pi * 180}, angle(cpx1): {np.angle(cpx1) / np.pi * 180}")
            #Normalize the complex numbers to get the rotation
            cpx0 /= np.abs(cpx0)
            cpx1 /= np.abs(cpx1)
            cpx_ratio = (cpx0 / cpx1)
            #print(f"DEBUG angle(cpx_ratio): {np.angle(cpx_ratio) / np.pi * 180}")
            ratios_vector.append(cpx_ratio)
    mean_diff = np.mean(ratios_vector)
    mean_diff_angle = np.angle(mean_diff)
    #print(f"Mean angle: {mean_diff_angle / np.pi * 180}")
    return mean_diff_angle

# -------------------------------------------------------------------------
def _rotate_points(points, angle):
    rotation_matrix = np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)]
    ])
    return points @ rotation_matrix.T

# -------------------------------------------------------------------------
def _interpolate_points_by_decomposition(points0: np.ndarray, points1: np.ndarray, video_size: np.ndarray, step: float, log_scale = True):
    #Split the transformation into scale, rotation, and translation components
    scale =    _points_mean_size_ratio(points0, points1)
    rotation = _points_mean_rotation(points0, points1)

    #The center of rotation is the center of the video frame
    rot_center = video_size / 2
    
    zero_centered_points0 = points0 - rot_center

    #Calculate the residual by doing the inverse transformation on points1
    zero_centered_points1 = points1 - rot_center
    rotated_points1 = _rotate_points(zero_centered_points1, -rotation)
    scaled_points1 = rotated_points1 / scale
    residual = scaled_points1 - zero_centered_points0

    step_angle = rotation * step
    if log_scale:
        step_scale = np.exp(np.log(scale) * step)
    else:
        step_scale = (scale - 1) * step + 1
    step_residual = residual * step
    rotated_points0 = _rotate_points(zero_centered_points0 + step_residual, step_angle)
    rotated_zoomed_points0 = rotated_points0 * step_scale
    return rotated_zoomed_points0 + rot_center


# -------------------------------------------------------------------------
def _interpolate_points(
    points0: np.ndarray,
    points1: np.ndarray,
    video_size: np.ndarray,
    alpha: float,
    interpolation_method: str = "log",
) -> np.ndarray:
    if interpolation_method == "linear":
        return _interpolate_points_by_decomposition(points0, points1, video_size, alpha, False)
    elif interpolation_method == "log":
        return _interpolate_points_by_decomposition(points0, points1, video_size, alpha, True)
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
        video_size,
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
    test_points = np.linspace(
        0, 1, num=int(1 / BLEND_RANGE_DETECTION_RESOLUTION), endpoint=True
    )
    simultaneous_fills_mask = np.zeros(len(test_points), dtype=bool)
    for i, test_size_alpha in enumerate(test_points):
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
        if intermediate_frame0_fills and intermediate_frame1_fills:
            simultaneous_fills_mask[i] = True
    return test_points, simultaneous_fills_mask


# -------------------------------------------------------------------------
def get_pair_blend_alpha_range(proj_data: dict, index: int) -> tuple:
    images_data = proj_data["images_data"]
    return get_blend_alpha_range(
        np.array(proj_data["video_data"]["size"], dtype=np.int32),
        images_data[index]["image"].get_cv_image(),
        np.array(images_data[index]["next_points"], dtype=np.float32),
        np.array(images_data[index]["frame"], dtype=np.float32),
        images_data[index + 1]["image"].get_cv_image(),
        np.array(images_data[index + 1]["prev_points"], dtype=np.float32),
        np.array(images_data[index + 1]["frame"], dtype=np.float32),
    )

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
def _central_valid_size_alpha(proj_data: dict, index: int) -> float:
    # Center of the largest contiguous range where both images fill the
    # video frame; 0.5 when there is no such range.
    test_points, mask = get_pair_blend_alpha_range(proj_data, index)
    best_start, best_length, start = 0, 0, None
    for i in range(len(mask) + 1):
        valid = i < len(mask) and bool(mask[i])
        if valid and start is None:
            start = i
        elif not valid and start is not None:
            if i - start > best_length:
                best_start, best_length = start, i - start
            start = None
    if best_length == 0:
        return 0.5
    return float(
        (test_points[best_start] + test_points[best_start + best_length - 1])
        / 2
    )


# -------------------------------------------------------------------------
def calculate_pair_correlation(
    proj_data: dict, index: int = 0, size_alpha: float | None = None
) -> float:
    # Correlation between the two images transformed to the same
    # intermediate frame, at the center of the valid alpha range (0.5 if
    # none). NaN (e.g. flat channels) is reported as 0.
    if size_alpha is None:
        size_alpha = _central_valid_size_alpha(proj_data, index)
    video_size = np.array(proj_data["video_data"]["size"], dtype=np.int32)
    entry0 = proj_data["images_data"][index]
    entry1 = proj_data["images_data"][index + 1]
    img0 = entry0["image"].get_cv_image()
    img1 = entry1["image"].get_cv_image()
    points0 = np.array(entry0["next_points"], dtype=np.float32)
    frame0 = np.array(entry0["frame"], dtype=np.float32)
    points1 = np.array(entry1["prev_points"], dtype=np.float32)
    frame1 = np.array(entry1["frame"], dtype=np.float32)
    intermediate0 = _create_intermediate_frame(
        video_size, img0, points0, frame0, points1, frame1, size_alpha
    )
    intermediate1 = _create_intermediate_frame(
        video_size, img1, points1, frame1, points0, frame0, 1 - size_alpha
    )
    correlation = float(
        _calculate_frames_correlation(intermediate0, intermediate1)
    )
    return 0.0 if np.isnan(correlation) else correlation


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
def select_alingment_points(matches, kp0, kp1, num_points, n_best):
    start = time.time()
    matches = sorted(matches, key=lambda x: x[0].distance)
    selected_matches = matches[:n_best]
    if len(selected_matches) < num_points:
        return None, "Not enough matches to select alignment points"
    indexes = list(range(len(selected_matches)))
    indexes_combinations = list(combinations(indexes, num_points))
    #Create one transformation for each combination of matches
    transformations = []
    for combination in indexes_combinations:
        img0_first_point  = kp0[matches[combination[0]][0].queryIdx].pt
        img1_first_point  = kp1[matches[combination[0]][0].trainIdx].pt
        img0_second_point = kp0[matches[combination[1]][0].queryIdx].pt
        img1_second_point = kp1[matches[combination[1]][0].trainIdx].pt
        img0_third_point  = kp0[matches[combination[2]][0].queryIdx].pt
        img1_third_point  = kp1[matches[combination[2]][0].trainIdx].pt
        affineTransform = cv.getAffineTransform(
            np.array([img0_first_point, img0_second_point, img0_third_point], dtype=np.float32),
            np.array([img1_first_point, img1_second_point, img1_third_point], dtype=np.float32)
        )
        transformations.append(affineTransform.flatten())
    #Iterate over all combinations, removing the one that is furthest from the average transformation until only one combination remains
    while len(indexes_combinations) > 1:
        avg_transformation = np.mean([transformations[i] for i in range(len(indexes_combinations))], axis=0)
        distances = [np.linalg.norm(transformations[i] - avg_transformation) for i in range(len(indexes_combinations))]
        furthest_index = np.argmax(distances)
        del indexes_combinations[furthest_index]
        del transformations[furthest_index]
    best_combination = indexes_combinations[0]
    #print(f"DEBUG - Time taken for select_alingment_points: {time.time() - start}")
    return [kp0[matches[i][0].queryIdx].pt for i in best_combination], [kp1[matches[i][0].trainIdx].pt for i in best_combination]


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
    #print(f"DEBUG - Total matches found: {len(matches)}")
    return select_alingment_points(matches, kp0, kp1, 3, 15)


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
    #print(f"DEBUG - Total matches found: {len(matches)}")
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
        #print(f"DEBUG - Pair ratio for images {i} and {i + 1}: {pair_ratio}")
        #print(f"Zoom for image {i}:{current_zoom}")
    # if img_zooms is not an full increasing or decreasing sequence, return error
    if not (np.all(np.diff(img_zooms) >= 0) or np.all(np.diff(img_zooms) <= 0)):
        error_msg = "Image zooms are not in full increasing or decreasing order"
        print(f"ERROR - {error_msg}")
        return None, error_msg
    img_zooms = np.array(img_zooms)
    print("Image zooms:", img_zooms)
    return img_zooms, None


# -------------------------------------------------------------------------
def _calculate_frames_fusion_and_size_alpha(proj_data: dict):
    video_data = proj_data["video_data"]
    fps = video_data["FPS"]
    pause_before = video_data.get("pause_before", 0)
    pause_after = video_data.get("pause_after", 0)
    if pause_before < 0 or pause_after < 0:
        return None, "Pause durations cannot be negative"
    total_frames = int(fps * video_data["duration"])
    if total_frames < 1:
        return None, "Zooming duration must produce at least one frame"

    zoom_array, error_msg = _calculate_zoom_array(proj_data)
    if error_msg is not None:
        return None, error_msg
    log_zoom_array = np.log(zoom_array)
    zoom_distances = np.abs(log_zoom_array - log_zoom_array[0])
    frame_distances = np.linspace(0, zoom_distances[-1], num=total_frames)
    indexes_steps_list = []
    for frame_distance in frame_distances:
        if frame_distance <= zoom_distances[0]:
            indexes_steps_list.append((0, 0.0))
            continue
        first_index = (
            np.searchsorted(zoom_distances, frame_distance, side="left") - 1
        )
        step = (frame_distance - zoom_distances[first_index]) / (
            zoom_distances[first_index + 1] - zoom_distances[first_index]
        )
        indexes_steps_list.append((first_index, step))
    before_frames = int(fps * pause_before)
    after_frames = int(fps * pause_after)
    return (
        [indexes_steps_list[0]] * before_frames
        + indexes_steps_list
        + [indexes_steps_list[-1]] * after_frames,
        None,
    )


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
            float(self.proj_data["video_data"]["FPS"]),
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
        self._image_zooms, _ = _calculate_zoom_array(self.proj_data)
        return True, None

    # ---------------------------------------------------------------------
    def get_zoom_on_position(self, position):
        # Zoom relative to the first frame, interpolated in log space
        frames = self._indexes_size_alphas_list
        if frames is None or not 0 <= position < len(frames):
            return None
        first_index, step = self._indexes_size_alphas_list[position]
        log_zooms = np.log(self._image_zooms)
        if first_index + 1 >= len(log_zooms):
            return float(np.exp(log_zooms[first_index]))
        log_zoom = log_zooms[first_index] + step * (
            log_zooms[first_index + 1] - log_zooms[first_index]
        )
        return float(np.exp(log_zoom))

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
        # Interpolation selection is temporarily disabled: always logarithmic
        interpolation_method = "log"
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


