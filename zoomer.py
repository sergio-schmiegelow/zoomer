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
        print(f'DEBUG - type(startPoints): {type(startPoints)}, startPoints.shape: {startPoints.shape}')
        print(f'DEBUG - type(endPoints): {type(endPoints)}, endPoints.shape: {endPoints.shape}')
        self.startPoints = startPoints
        self.endPoints = endPoints
        self.transformMatrix = self.calculateTransformMatrix(1.0)
    #---------------------------------------------------------------------
    def calculateTransformMatrix(self, step)->None:
        # Calculate the affine transformation matrix based on the start and end points and tranformation step [0.0, 1.0].
        destPoints = self.startPoints + (self.endPoints - self.startPoints) * step
        self.transformMatrix = cv.getAffineTransform(destPoints.astype(np.float32), self.endPoints.astype(np.float32))
    #---------------------------------------------------------------------
    def transformCropImage(self, image:np.ndarray, step:float, outputSize:tuple)->np.ndarray:
        # Apply the affine transformation to the image based on the current step.
        self.calculateTransformMatrix(step)
        transformedImage = cv.warpAffine(image, self.transformMatrix, (image.shape[1], image.shape[0]))
        croppedImage = cv.getRectSubPix(transformedImage, outputSize, (self.endPoints[0][0], self.endPoints[0][1]))
        return croppedImage
#-------------------------------------------------------------------------
def generateImageWithMarkers(cfgListItems):
    img = cv.imread(cfgListItems['filename'])
    if cfgListItems['prev_points'] is not None:
        for idx, point in enumerate(cfgListItems['prev_points']):
            #draw a "plus sign" at the previous points
            color = CROSS_COLORS[idx]  # Alternate colors for previous points
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1])), (int(point[0]) + CROSS_SIZE, int(point[1])), color, CROSS_THICKNESS)
            cv.line(img, (int(point[0]), int(point[1]) - CROSS_SIZE), (int(point[0]), int(point[1]) + CROSS_SIZE), color, CROSS_THICKNESS)
    if cfgListItems['next_points'] is not None:
        for idx, point in enumerate(cfgListItems['next_points']):
            #draw a "X sign" at the next points
            color = CROSS_COLORS[idx]  # Alternate colors for next points
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1]) - CROSS_SIZE), (int(point[0]) + CROSS_SIZE, int(point[1]) + CROSS_SIZE), color, CROSS_THICKNESS)
            cv.line(img, (int(point[0]) - CROSS_SIZE, int(point[1]) + CROSS_SIZE), (int(point[0]) + CROSS_SIZE, int(point[1]) - CROSS_SIZE), color, CROSS_THICKNESS)
    #plot the frame rectangle
    frame = np.array(cfgListItems['frame'], dtype=np.int32)
    print(f'DEBUG - frame: {frame}')
    framePoints = np.array([frame[0], [frame[1][0], frame[0][1]], frame[1], [frame[0][0], frame[1][1]]], dtype=np.int32)
    print(f'DEBUG - framePoints: {framePoints}')
    cv.polylines(img, [framePoints], isClosed=True, color=FRAME_COLOR, thickness=FRAME_THICKNESS)
    return img
#-------------------------------------------------------------------------
cfgFile = 'prat.json'
cfgDict = json.load(open(cfgFile, 'r'))
img = generateImageWithMarkers(cfgDict['images_data'][1])
cv.imshow('Image with Markers', img)
cv.waitKey(0)
cv.destroyAllWindows()
quit()



videoShape = np.array(cfgDict['video_size'], dtype=np.int32)[::-1]


'''
img0 = cv.imread(cfgDict['images_data'][0]['filename'])
nextPoints0 = np.array(cfgDict['images_data'][0]['next_points'], dtype=np.float32)
img1 = cv.imread(cfgDict['images_data'][1]['filename'])
prevPoints1 = np.array(cfgDict['images_data'][1]['prev_points'], dtype=np.float32)
srcFrameAffinePoints = np.array(cfgDict['images_data'][0]['frame'], dtype=np.float32)
dstFrameAffinePoints = np.array(
                                 np.array([0,0]]
                                 np.arrayvideoShape, dtype=np.float32)   
imgFrameTransformer = affineTransformerClass(srcFrameAffinePoints, videoShape)
videoFrame = imgFrameTransformer.transformCropImage(img0, 1.0, videoShape)
'''
cv.imshow('Transformed Image', videoFrame)
cv.waitKey(0)
cv.destroyAllWindows()
