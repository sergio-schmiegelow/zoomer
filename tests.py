import pytest
import numpy as np
from zoomer import convert3PointsAndFrameToVideoCoordinates
#-------------------------------------------------------------------------
def test_convert3PointsAndFrameToVideoCoordinates():
    points = np.array([[101, 202], 
                       [103, 204], 
                       [105, 206]], dtype=np.float32)
    frame = np.array([[100, 200], 
                      [200, 400]], dtype=np.float32)
    videoDims = np.array([960, 540], dtype=np.float32)
    expected_output = np.array([[ 9.6,  5.4], 
                                [28.8, 10.8], 
                                [48.0, 16.2]], dtype=np.float32)
    output = convert3PointsAndFrameToVideoCoordinates(points, frame, videoDims)
    assert np.allclose(output, expected_output), f"Expected {expected_output}, but got {output}"


