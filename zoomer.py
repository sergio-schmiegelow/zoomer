import cv2 as cv
import numpy as np
import json

CROSS_SIZE = 10
CROSS_THICKNESS = 2
CROSS_COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]  # Red, Green, Blue
FRAME_COLOR = [255, 0, 0]  # Blue
FRAME_THICKNESS = 2
#-------------------------------------------------------------------------
class affineTransformerClass:
    #---------------------------------------------------------------------
    def __init__(self, startPoints:np.ndarray, endPoints:np.ndarray)->None:
        print(f'DEBUG - startPoints: \n{startPoints}')
        print(f'DEBUG - endPoints:   \n{endPoints}')
        self.startPoints = startPoints
        self.endPoints = endPoints
        self.transformMatrix = self.calculateTransformMatrix(1.0)
    #---------------------------------------------------------------------
    def calculateTransformMatrix(self, step)->None:
        # Calculate the affine transformation matrix based on the start and end points and tranformation step [0.0, 1.0].
        destPoints = self.startPoints + (self.endPoints - self.startPoints) * step
        self.transformMatrix = cv.getAffineTransform(self.startPoints.astype(np.float32), destPoints.astype(np.float32))
    #---------------------------------------------------------------------
    def transformImage(self, image:np.ndarray, step:float, outputSize:np.ndarray)->np.ndarray:
        # Apply the affine transformation to the image based on the current step.
        self.calculateTransformMatrix(step)
        transformedImage = cv.warpAffine(image, self.transformMatrix, (outputSize[0], outputSize[1]))
        return transformedImage
    #---------------------------------------------------------------------
    def transformPoints(self, points:np.ndarray, step:float)->np.ndarray:
        # Apply the affine transformation to a set of points based on the current step.
        self.calculateTransformMatrix(step)
        transformedPoints = cv.transform(np.array([points], dtype=np.float32), self.transformMatrix)
        return transformedPoints[0]
#-------------------------------------------------------------------------
def generateImageWithMarkers(img:np.ndarray, frame, prevPoints: np.ndarray, nextPoints: np.ndarray)->np.ndarray:
    if prevPoints is not None:
        for idx, point in enumerate(prevPoints):
            #draw a "plus sign" at the previous points
            color = CROSS_COLORS[idx]  # Alternate colors for previous points
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1])), (int(point[0]) + CROSS_SIZE, int(point[1])), color, CROSS_THICKNESS)
            cv.line(img, (int(point[0]), int(point[1]) - CROSS_SIZE), (int(point[0]), int(point[1]) + CROSS_SIZE), color, CROSS_THICKNESS)
    if nextPoints is not None:
        for idx, point in enumerate(nextPoints):
            #draw a "X sign" at the next points
            color = CROSS_COLORS[idx]  # Alternate colors for next points
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1]) - CROSS_SIZE), (int(point[0]) + CROSS_SIZE, int(point[1]) + CROSS_SIZE), color, CROSS_THICKNESS)
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1]) + CROSS_SIZE), (int(point[0]) + CROSS_SIZE, int(point[1]) - CROSS_SIZE), color, CROSS_THICKNESS)
    #plot the frame rectangle
    framePoints = np.array([frame[0], [frame[1][0], frame[0][1]], frame[1], [frame[0][0], frame[1][1]]], dtype=np.int32)
    cv.polylines(img, [framePoints], isClosed=True, color=FRAME_COLOR, thickness=FRAME_THICKNESS)
    return img
#-------------------------------------------------------------------------
cfgFile = 'prat.json'
cfgDict = json.load(open(cfgFile, 'r'))

img = generateImageWithMarkers(cv.imread(cfgDict['images_data'][0]['filename']),
                               cfgDict['images_data'][0]['frame'],
                               cfgDict['images_data'][0]['prev_points'], 
                               cfgDict['images_data'][0]['next_points'])
cv.imshow('Image with Markers', img)
videoDims = np.array(cfgDict['video_size'], dtype=np.int32)

img0 = cv.imread(cfgDict['images_data'][0]['filename'])
nextPoints0 = np.array(cfgDict['images_data'][0]['next_points'], dtype=np.float32)
frame0 = np.array(cfgDict['images_data'][0]['frame'], dtype=np.float32)

srcFrameAffinePoints = np.array([frame0[0], 
                                [frame0[1][0], frame0[0][1]], 
                                 frame0[1]], dtype=np.float32)
dstFrameAffinePoints = np.array([[0, 0],
                                 [videoDims[0], 0],
                                 videoDims], dtype=np.float32)
imgFrameTransformer = affineTransformerClass(srcFrameAffinePoints, dstFrameAffinePoints)

videoFrame = imgFrameTransformer.transformImage(img0, 1.0, videoDims)
transformedNextPoints = imgFrameTransformer.transformPoints(nextPoints0, 1.0)
transformedVideoFrame = generateImageWithMarkers(videoFrame, 
                                      [[0, 0],videoFrame.shape[:2][::-1]], 
                                      None, 
                                      transformedNextPoints)
cv.imshow('Transformed Image1', transformedVideoFrame)
cv.waitKey(0)
cv.destroyAllWindows()
quit()
