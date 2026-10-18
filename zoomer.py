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
        self.transformMatrix = self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def setStartPoints(self, startPoints:np.ndarray)->None:
        self.startPoints = startPoints
        self.transformMatrix = self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def setEndPoints(self, endPoints:np.ndarray)->None:
        self.endPoints = endPoints
        self.transformMatrix = self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def calculateTransformMatrix(self)->None:
        # Calculate the affine transformation matrix based on the start and end points.
        self.transformMatrix = cv.getAffineTransform(self.startPoints.astype(np.float32), self.endPoints.astype(np.float32))
    #---------------------------------------------------------------------
    def transformImage(self, image:np.ndarray, outputSize:np.ndarray)->np.ndarray:
        # Apply the affine transformation to an image.
        self.calculateTransformMatrix()
        transformedImage = cv.warpAffine(image, self.transformMatrix, (outputSize[0], outputSize[1]))
        return transformedImage
    #---------------------------------------------------------------------
    def transformPoints(self, points:np.ndarray)->np.ndarray:
        # Apply the affine transformation to a set of points.
        self.calculateTransformMatrix()
        transformedPoints = cv.transform(np.array([points], dtype=np.float32), self.transformMatrix)
        return transformedPoints[0]
#-------------------------------------------------------------------------
def convert3PointsAndFrameToVideoCoordinates(points:np.ndarray, frame:np.ndarray, videoDims:np.ndarray)->np.ndarray:
    outPoints = np.zeros(points.shape, dtype=np.float32)
    print(f'DEBUG - points: \n{points}')
    print(f'DEBUG - frame: \n{frame}')
    print(f'DEBUG - videoDims: \n{videoDims}')
    print(f'DEBUG - outPoints: \n{outPoints}')
    outPoints[:, 0] = (points[:, 0] - frame[0][0]) * (videoDims[0] / (frame[1][0] - frame[0][0]))
    outPoints[:, 1] = (points[:, 1] - frame[0][1]) * (videoDims[1] / (frame[1][1] - frame[0][1]))
    return outPoints
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
def convertPointsToVideoDimensions(points:np.ndarray, frame:np.ndarray, videoDims:np.ndarray)->np.ndarray:
    # Convert points from the source frame to the destination frame using an affine transformation.
    frameAffinePoints = np.array([frame[0], 
                                 [frame[1][0], frame[0][1]], 
                                 frame[1]], dtype=np.float32)
    videoDimsAffinePoints = np.array([[0, 0], 
                                      [videoDims[0], 0], 
                                      videoDims], dtype=np.float32)
    transformMatrix = cv.getAffineTransform(frameAffinePoints, videoDimsAffinePoints)
    transformedPoints = cv.transform(np.array([points], dtype=np.float32), transformMatrix)
    return transformedPoints[0]
#-------------------------------------------------------------------------
def interpolatePoints(points0:np.ndarray, points1:np.ndarray, alpha:float)->np.ndarray:
    # Interpolate between two sets of points based on the alpha value.
    return (1 - alpha) * points0 + alpha * points1
#-------------------------------------------------------------------------
def pointsMeanSize(points:np.ndarray)->float:
    # Calculate the mean size of a triangle formed by three points.
    return np.mean([np.linalg.norm(points[0] - points[1]),
                    np.linalg.norm(points[1] - points[2]),
                    np.linalg.norm(points[2] - points[0])])
#-------------------------------------------------------------------------
def pointsMeanSizeRatio(points0:np.ndarray, points1:np.ndarray)->float:
    # Calculate the ratio of the mean sizes of two triangles formed by three points each.
    meanSize0 = pointsMeanSize(points0)
    meanSize1 = pointsMeanSize(points1)
    return meanSize1 / meanSize0 if meanSize0 != 0 else float('inf')
#-------------------------------------------------------------------------
def interpolatePointsGP(points0:np.ndarray, points1:np.ndarray, alpha:float)->np.ndarray:
    # Interpolate between two sets of points based in geometric progression on the alpha value.
    #Calculate the relative size of the two sets of points
    sizeRatio = pointsMeanSizeRatio(points0, points1)
    logSizeRatio = np.log(sizeRatio)
    interpolatedLogSize = alpha * logSizeRatio
    linearSizeRatio = np.exp(interpolatedLogSize)
    pgAlpha = (linearSizeRatio - 1) / (sizeRatio - 1) if sizeRatio != 1 else alpha
    print(f'DEBUG - sizeRatio: {sizeRatio}, alpha: {alpha}, linearSizeRatio: {linearSizeRatio}, pgAlpha: {pgAlpha}')
    return (1 - pgAlpha) * points0 + pgAlpha * points1
#-------------------------------------------------------------------------
#Function to calculate the alpha range where both transformed images fill all the video frame
def calculateBlendAlphaRange(img0:np.ndarray, points0:np.ndarray, frame0:np.ndarray, img1:np.ndarray, points1:np.ndarray, frame1:np.ndarray, videoDims:np.ndarray)->tuple:
    #Convert the points0 to frame0 coordinates
    videoTransformedPoints0 = convertPointsToVideoDimensions(points0, frame0, videoDims)
    #Convert the points1 to frame1 coordinates
    videoTransformedPoints1 = convertPointsToVideoDimensions(points1, frame1, videoDims)
    #Calculate the bounding boxes of the transformed points
    minPoint0 = np.min(videoTransformedPoints0, axis=0)
    maxPoint0 = np.max(videoTransformedPoints0, axis=0)
    minPoint1 = np.min(videoTransformedPoints1, axis=0)
    maxPoint1 = np.max(videoTransformedPoints1, axis=0)
    
    #Calculate the alpha range where both transformed images fill all the video frame
    alphaMinX = (videoDims[0] - maxPoint1[0]) / (maxPoint0[0] - maxPoint1[0]) if maxPoint0[0] != maxPoint1[0] else 0
    alphaMaxX = (videoDims[0] - minPoint1[0]) / (minPoint0[0] - minPoint1[0]) if minPoint0[0] != minPoint1[0] else 1
    alphaMinY = (videoDims[1] - maxPoint1[1]) / (maxPoint0[1] - maxPoint1[1]) if maxPoint0[1] != maxPoint1[1] else 0
    alphaMaxY = (videoDims[1] - minPoint1[1]) / (minPoint0[1] - minPoint1[1]) if minPoint0[1] != minPoint1[1] else 1
    
    alphaMin = max(0, alphaMinX, alphaMinY)
    alphaMax = min(1, alphaMaxX, alphaMaxY)
    
    return (alphaMin, alphaMax)
#-------------------------------------------------------------------------
def createIntermediateFrame(videoSize:np.ndarray, 
                            img0:np.ndarray, points0:np.ndarray, frame0:np.ndarray,
                                             points1:np.ndarray, frame1:np.ndarray,
                            sizeAlpha:float)->np.ndarray:
    #Convert the points0 to frame0 coordinates
    videoTransformedPoints0 = convertPointsToVideoDimensions(points0, frame0, videoSize)
    #Convert the points1 to frame1 coordinates
    videoTransformedPoints1 = convertPointsToVideoDimensions(points1, frame1, videoSize)
    #Interpolate the points between the two frames
    interpolatedPoints = interpolatePointsGP(videoTransformedPoints0, videoTransformedPoints1, sizeAlpha)
    #Create an affine transformer for the first image
    imgTransformer = affineTransformerClass(points0, interpolatedPoints)
    #Transform the first image to the intermediate frame
    intermediateFrame = imgTransformer.transformImage(img0, videoSize)
    return intermediateFrame
#-------------------------------------------------------------------------
if __name__ == "__main__": 
    cfgFile = 'prat.json'
    cfgDict = json.load(open(cfgFile, 'r'))
    videoDims = np.array(cfgDict['video_size'], dtype=np.int32)
    
    #Extract the first images pair data from the configuration dictionary
    img0 = cv.imread(cfgDict['images_data'][0]['filename'])
    frame0 = np.array(cfgDict['images_data'][0]['frame'], dtype=np.float32)
    nextPoints0 = np.array(cfgDict['images_data'][0]['next_points'], dtype=np.float32)
    
    img1 = cv.imread(cfgDict['images_data'][1]['filename'])
    frame1 = np.array(cfgDict['images_data'][1]['frame'], dtype=np.float32)
    prevPoints1 = np.array(cfgDict['images_data'][1]['prev_points'], dtype=np.float32)
    
    
    blendAlphaMin, blendAlphaMax = calculateBlendAlphaRange(img0, nextPoints0, frame0, img1, prevPoints1, frame1, videoDims)

    for sizeAlpha in np.linspace(0, 1, num=100):
        interpolatePointsGP(nextPoints0, prevPoints1, sizeAlpha)
        outFrame0 = createIntermediateFrame(videoDims, img0, nextPoints0, frame0, prevPoints1, frame1, sizeAlpha)
        outFrame1 = createIntermediateFrame(videoDims, img1, prevPoints1, frame1, nextPoints0, frame0, 1-sizeAlpha)
        blendedFrame = cv.addWeighted(outFrame0, 1-sizeAlpha, outFrame1, sizeAlpha, 0)
        cv.imshow(f'Intermediate Frame0', outFrame0)
        cv.imshow(f'Intermediate Frame1', outFrame1)
        cv.imshow(f'Blended Frame', blendedFrame)
        cv.waitKey(100)

    cv.destroyAllWindows()
    quit()
    
    #Convert the second image's previous points to the video dimensions using an affine transformation
    videoTransformedPrevPoints1 = convertPointsToVideoDimensions(prevPoints1, frame1, videoDims)
    
    img0FrameTransformer = affineTransformerClass(nextPoints0, videoTransformedPrevPoints1)
    
    videoFrame0 = img0FrameTransformer.transformImage(img0, videoDims)
    markedVideoFrame0 = generateImageWithMarkers(videoFrame0, 
                                                [[0, 0],videoFrame0.shape[:2][::-1]], 
                                                None, 
                                                videoTransformedPrevPoints1)
    cv.imshow('MarkedVideoFrame0', markedVideoFrame0)
    cv.waitKey(0)
    cv.destroyAllWindows()
