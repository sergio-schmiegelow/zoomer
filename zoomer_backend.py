import cv2 as cv
import numpy as np
from scipy.optimize import minimize, OptimizeResult, shgo, least_squares
import json
from pathlib import Path
import time

NUM_FRAMES = 100
CROSS_SIZE = 10
CROSS_THICKNESS = 2
CROSS_COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]  # Red, Green, Blue
FRAME_COLOR = [255, 0, 0]  # Blue
FRAME_THICKNESS = 2
BLEND_RANGE_DETECTION_RESOLUTION = 0.01
#-------------------------------------------------------------------------
def polygonIsInsidePolygon(innerPolygon:np.ndarray, outerPolygon:np.ndarray)->bool:
    # Check if all points of the inner polygon are inside the outer polygon.
    for point in innerPolygon:
        if cv.pointPolygonTest(outerPolygon, (point[0], point[1]), False) < 0:
            return False
    return True
#-------------------------------------------------------------------------
class imageClass:
    #---------------------------------------------------------------------
    def __init__(self, filename:str):
        self.imagePath = Path(filename)
        if not self.imagePath.exists():
            raise ValueError(f"Image file does not exist: {filename}")
        self.imagePath = self.imagePath.resolve()
        self.cvImage = cv.imread(str(self.imagePath))
        self.qtImage = None
    #---------------------------------------------------------------------
    def getImagePath(self)->str:
        return self.imagePath
    #---------------------------------------------------------------------
    def getCvImage(self)->np.ndarray:
        return self.cvImage
    #---------------------------------------------------------------------
    def getQtImage(self):
        return self.qtImage
    #---------------------------------------------------------------------
    def setQtImage(self, qtImage):
        self.qtImage = qtImage
#-------------------------------------------------------------------------
def loadConfig(filename:str)->dict:
    with open(filename, 'r') as f:
        cfgDict = json.load(f)
    for imageData in cfgDict['images_data']:
        imageData['image'] = imageClass(str(imageData['image']))
    return cfgDict
#-------------------------------------------------------------------------
def saveConfig(filename:str, cfgDict:dict)->None:
    cfgDictCopy = dict(cfgDict)
    cfgDictCopy['images_data'] = []
    for imageData in cfgDict['images_data']:
        imageDataCopy = dict(imageData)
        imageObject = imageDataCopy['image']
        if isinstance(imageObject, imageClass):
            imageDataCopy['image'] = str(imageObject.getImagePath())
        cfgDictCopy['images_data'].append(imageDataCopy)
    with open(filename, 'w') as f:
        json.dump(cfgDictCopy, f, indent=2)
    return
#-------------------------------------------------------------------------
class affineTransformerClass:
    #---------------------------------------------------------------------
    def __init__(self, startPoints:np.ndarray, endPoints:np.ndarray)->None:
        #print(f'DEBUG - startPoints: \n{startPoints}')
        #print(f'DEBUG - endPoints:   \n{endPoints}')
        self.startPoints = startPoints
        self.endPoints = endPoints
        self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def setStartPoints(self, startPoints:np.ndarray)->None:
        self.startPoints = startPoints
        self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def setEndPoints(self, endPoints:np.ndarray)->None:
        self.endPoints = endPoints
        self.calculateTransformMatrix()
    #---------------------------------------------------------------------
    def calculateTransformMatrix(self)->None:
        # Calculate the affine transformation matrix based on the start and end points.
        self.transformMatrix = cv.getAffineTransform(self.startPoints.astype(np.float32), self.endPoints.astype(np.float32))
    #---------------------------------------------------------------------
    def transformedImageFillsOutputSize(self, image:np.ndarray, outputSize:np.ndarray)->bool:
        # Check it the transformed image will not leave any blank areas in the output frame of the specified size.
        # Get the corners of the image
        h, w = image.shape[:2]
        originalImgCornersPolygon = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        # Transform the corners
        transformedImgCornersPolygon = cv.transform(np.array([originalImgCornersPolygon]), self.transformMatrix)[0]
        videoCornersPolygon = np.array([[0, 0], [outputSize[0], 0], [outputSize[0], outputSize[1]], [0, outputSize[1]]], dtype=np.float32)
        # Check if videoCornersPolygon is inside transformedImgCornersPolygon
        return polygonIsInsidePolygon(videoCornersPolygon, transformedImgCornersPolygon)
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
    #print(f'DEBUG - points: \n{points}')
    #print(f'DEBUG - frame: \n{frame}')
    #print(f'DEBUG - videoDims: \n{videoDims}')
    #print(f'DEBUG - outPoints: \n{outPoints}')
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
def convertImgPointsToVideoDimensions(points:np.ndarray, frame:np.ndarray, videoDims:np.ndarray)->np.ndarray:
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
def convertVideoPointsToImageDimensions(points:np.ndarray, frame:np.ndarray, videoDims:np.ndarray)->np.ndarray:
    # Convert points from the video frame to the source image frame using an affine transformation.
    videoDimsAffinePoints = np.array([[0, 0], 
                                      [videoDims[0], 0], 
                                      videoDims], dtype=np.float32)
    frameAffinePoints = np.array([frame[0], 
                                 [frame[1][0], frame[0][1]], 
                                 frame[1]], dtype=np.float32)
    transformMatrix = cv.getAffineTransform(videoDimsAffinePoints, frameAffinePoints)
    transformedPoints = cv.transform(np.array([points], dtype=np.float32), transformMatrix)
    return transformedPoints[0]
#-------------------------------------------------------------------------
def extractVideoFrameFromImage(img:np.ndarray, frame:np.ndarray, videoDims:np.ndarray)->np.ndarray:
    # Extract the video frame from the source image using an affine transformation.
    videoDimsAffinePoints = np.array([[0, 0], 
                                      [videoDims[0], 0], 
                                      videoDims], dtype=np.float32)
    frameAffinePoints = np.array([frame[0], 
                                 [frame[1][0], frame[0][1]], 
                                 frame[1]], dtype=np.float32)
    transformMatrix = cv.getAffineTransform(frameAffinePoints, videoDimsAffinePoints)
    videoFrame = cv.warpAffine(img, transformMatrix, (videoDims[0], videoDims[1]))
    return videoFrame
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
def interpolatePointsLinear(points0:np.ndarray, points1:np.ndarray, alpha:float)->np.ndarray:
    # Interpolate between two sets of points linearly based on the alpha value.
    return (1 - alpha) * points0 + alpha * points1
#-------------------------------------------------------------------------
def interpolatePointsLog(points0:np.ndarray, points1:np.ndarray, alpha:float)->np.ndarray:
    # Interpolate between two sets of points based on the specified interpolation method.
    #Calculate the relative size of the two sets of points
    sizeRatio = pointsMeanSizeRatio(points0, points1)
    logSizeRatio = np.log(sizeRatio)
    interpolatedLogSize = alpha * logSizeRatio
    linearSizeRatio = np.exp(interpolatedLogSize)
    pgAlpha = (linearSizeRatio - 1) / (sizeRatio - 1) if sizeRatio != 1 else alpha
    #print(f'DEBUG - sizeRatio: {sizeRatio}, alpha: {alpha}, linearSizeRatio: {linearSizeRatio}, pgAlpha: {pgAlpha}')
    return (1 - pgAlpha) * points0 + pgAlpha * points1
#-------------------------------------------------------------------------
def interpolatePoints(points0:np.ndarray, points1:np.ndarray, alpha:float, interpolationMethod:str='log')->np.ndarray:
    if interpolationMethod == 'linear':
        return interpolatePointsLinear(points0, points1, alpha)
    elif interpolationMethod == 'log':
        return interpolatePointsLog(points0, points1, alpha)
    else:
        raise ValueError(f"Unknown interpolation method: {interpolationMethod}")
#-------------------------------------------------------------------------
def createIntermediateFrame(videoSize:np.ndarray, 
                            img0:np.ndarray, points0:np.ndarray, frame0:np.ndarray,
                                             points1:np.ndarray, frame1:np.ndarray,
                            sizeAlpha:float, checkFill:bool=False,
                            interpolationMethod:str='log')->np.ndarray:
    #Convert the points0 to frame0 coordinates
    videoTransformedPoints0 = convertImgPointsToVideoDimensions(points0, frame0, videoSize)
    #Convert the points1 to frame1 coordinates
    videoTransformedPoints1 = convertImgPointsToVideoDimensions(points1, frame1, videoSize)
    #Interpolate the points between the two frames
    interpolatedPoints = interpolatePoints(videoTransformedPoints0, videoTransformedPoints1, sizeAlpha, interpolationMethod)
    #Create an affine transformer for the first image
    imgTransformer = affineTransformerClass(points0, interpolatedPoints)
    if checkFill:
        return imgTransformer.transformedImageFillsOutputSize(img0, videoSize)
    #Transform the first image to the intermediate frame
    intermediateFrame = imgTransformer.transformImage(img0, videoSize)
    return intermediateFrame
#-------------------------------------------------------------------------
def getBlendAlphaRange(videoSize:np.ndarray, 
                       img0:np.ndarray, points0:np.ndarray, frame0:np.ndarray,
                       img1:np.ndarray, points1:np.ndarray, frame1:np.ndarray)->tuple:
    #Scan the sizeAlpha to find the range where both images can fill the output frame
    minSizeAlphaForBlending = 1.0
    maxSizeAlphaForBlending = 0.0
    for testSizeAlpha in np.linspace(0, 1, num=int(1/BLEND_RANGE_DETECTION_RESOLUTION)+1):
        intermediateFrame0Fills = createIntermediateFrame(videoSize, img0, points0, frame0, points1, frame1, testSizeAlpha, checkFill=True)
        intermediateFrame1Fills = createIntermediateFrame(videoSize, img1, points1, frame1, points0, frame0, 1-testSizeAlpha, checkFill=True)
        print(f"DEBUG - testSizeAlpha = {testSizeAlpha}, intermediateFrame0Fills = {intermediateFrame0Fills}, intermediateFrame1Fills = {intermediateFrame1Fills}")
        if intermediateFrame0Fills and intermediateFrame1Fills:
            if testSizeAlpha < minSizeAlphaForBlending:
                minSizeAlphaForBlending = testSizeAlpha
            if testSizeAlpha > maxSizeAlphaForBlending:
                maxSizeAlphaForBlending = testSizeAlpha
    return minSizeAlphaForBlending, maxSizeAlphaForBlending
#-------------------------------------------------------------------------
def createBlendedFrame(configData:dict, index:int, sizeAlpha:float, blendAlpha:float, interpolationMethod:str='log')->np.ndarray:
    videoSize = np.array(configData['video_data']['size'], dtype=np.int32)
    
    imgPrev =                 configData['images_data'][index]['image'].getCvImage()
    framePrev  =     np.array(configData['images_data'][index]['frame'], dtype=np.float32)
    prevNextPoints = np.array(configData['images_data'][index]['next_points'], dtype=np.float32)

    imgNext =                 configData['images_data'][index + 1]['image'].getCvImage()
    frameNext  =     np.array(configData['images_data'][index + 1]['frame'], dtype=np.float32)
    nextPrevPoints = np.array(configData['images_data'][index + 1]['prev_points'], dtype=np.float32)
    
    intermediateFrame0 = createIntermediateFrame(videoSize, imgPrev, prevNextPoints, framePrev, nextPrevPoints, frameNext, sizeAlpha,  interpolationMethod=interpolationMethod)
    intermediateFrame1 = createIntermediateFrame(videoSize, imgNext, nextPrevPoints, frameNext, prevNextPoints, framePrev, 1-sizeAlpha, interpolationMethod=interpolationMethod )
    print(f'DEBUG - frames correlation: {calculateFramesCorrelation(intermediateFrame0, intermediateFrame1)}')
    #Blend the two intermediate frames
    blendedFrame = cv.addWeighted(intermediateFrame0, 1-blendAlpha, intermediateFrame1, blendAlpha, 0)
    return blendedFrame
#-------------------------------------------------------------------------
def calculateFramesCorrelation(frame0:np.ndarray, frame1:np.ndarray)->float:
    redCorrelation =   np.corrcoef(frame0[:,:,0].flatten(), frame1[:,:,0].flatten())[0,1]
    greenCorrelation = np.corrcoef(frame0[:,:,1].flatten(), frame1[:,:,1].flatten())[0,1]
    blueCorrelation =  np.corrcoef(frame0[:,:,2].flatten(), frame1[:,:,2].flatten())[0,1]
    correlation = (redCorrelation + greenCorrelation + blueCorrelation) / 3
    print(f'DEBUG - correlation: {correlation}')
    return correlation
#-------------------------------------------------------------------------
def autoAlignImages(configData:dict, index:int, useOnlyFrame = True)->np.ndarray:
    # Perform alignment for the image at the given index in the configData.
    # Returns the aligned points as a numpy array of shape (3, 2).
    img0 = configData['images_data'][index    ]['image'].getCvImage()
    img1 = configData['images_data'][index + 1]['image'].getCvImage()
    if useOnlyFrame:
        videoDims = configData['video_data']['size']
        frame0 = configData['images_data'][index    ]['frame']
        frame1 = configData['images_data'][index + 1]['frame']
        img0 = extractVideoFrameFromImage(img0, frame0, videoDims)
        img1 = extractVideoFrameFromImage(img1, frame1, videoDims)
    
    img0_next_points, img1_prev_points = siftAlignment(img0, img1)
        
    if useOnlyFrame:
        img0_next_points = convertVideoPointsToImageDimensions(img0_next_points, frame0, videoDims)
        img1_prev_points = convertVideoPointsToImageDimensions(img1_prev_points, frame1, videoDims)
    configData['images_data'][index]['next_points'] = img0_next_points
    configData['images_data'][index + 1]['prev_points'] = img1_prev_points
    return True
#-------------------------------------------------------------------------
def siftAlignment(img0, img1)->np.ndarray:
    #Perform SIFT feature detection and matching between img0 and img1.
    #Return the matched points for alignment or none if not enough matches are found.
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

    img0_first_point =  kp0[matches[0][0].queryIdx].pt
    img1_first_point =  kp1[matches[0][0].trainIdx].pt
    img0_second_point = kp0[matches[1][0].queryIdx].pt
    img1_second_point = kp1[matches[1][0].trainIdx].pt
    img0_third_point =  kp0[matches[2][0].queryIdx].pt
    img1_third_point =  kp1[matches[2][0].trainIdx].pt

    img0_next_points = np.array([img0_first_point, img0_second_point, img0_third_point], dtype=np.float32)
    img1_prev_points = np.array([img1_first_point, img1_second_point, img1_third_point], dtype=np.float32)

    return img0_next_points, img1_prev_points
#-------------------------------------------------------------------------
def orbAlignment(img0, img1)->np.ndarray:
    # Perform ORB feature detection and matching between img0 and img1.
    # Return the matched points for alignment or none if not enough matches are found.
    orb = cv.ORB_create()

    kp0, des0 = orb.detectAndCompute(img0, None)
    kp1, des1 = orb.detectAndCompute(img1, None)

    matcher = cv.DescriptorMatcher_create(cv.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
    matches = matcher.match(des0, des1, None)

    if len(matches) < 3:
        print("DEBUG - Not enough matches found.")
        return None, None
    print(f"DEBUG - Total matches found: {len(matches)}")
    matches = sorted(matches, key=lambda x: x.distance)

    img0_first_point =  kp0[matches[0].queryIdx].pt
    img1_first_point =  kp1[matches[0].trainIdx].pt
    img0_second_point = kp0[matches[1].queryIdx].pt
    img1_second_point = kp1[matches[1].trainIdx].pt
    img0_third_point =  kp0[matches[2].queryIdx].pt
    img1_third_point =  kp1[matches[2].trainIdx].pt

    img0_next_points = np.array([img0_first_point, img0_second_point, img0_third_point], dtype=np.float32)
    img1_prev_points = np.array([img1_first_point, img1_second_point, img1_third_point], dtype=np.float32)

    return img0_next_points, img1_prev_points
#-------------------------------------------------------------------------
def calculateZoomArray(configData:dict)->tuple:
    currentZoom = 1.0
    imgZooms = [1.0]
    videoDims = np.array(configData['video_data']['size'], dtype=np.int32)
    for i in range(len(configData['images_data']) - 1):
        img0 = configData['images_data'][i]['image']
        frame0 = np.array(configData['images_data'][i]['frame'], dtype=np.float32)
        nextPoints0 = np.array(configData['images_data'][i]['next_points'], dtype=np.float32)

        img1 = configData['images_data'][i + 1]['image']
        frame1 = np.array(configData['images_data'][i + 1]['frame'], dtype=np.float32)
        prevPoints1 = np.array(configData['images_data'][i + 1]['prev_points'], dtype=np.float32)

        convertedPoints0 = convertImgPointsToVideoDimensions(nextPoints0, frame0, videoDims)
        convertedPoints1 = convertImgPointsToVideoDimensions(prevPoints1, frame1, videoDims)

        pairRatio = pointsMeanSizeRatio(convertedPoints0, convertedPoints1)
        currentZoom *= pairRatio
        imgZooms.append(currentZoom)
        print(f"DEBUG - Pair ratio for images {i} and {i+1}: {pairRatio}")
        print(f"Zoom for image {i}:{currentZoom}")
    #if imgZooms is not an increase sequence, return error
    if not np.all(np.diff(imgZooms) >= 0):
        errorMsg = "Image zooms are not in increasing order"
        print(f"ERROR - {errorMsg}")
        return None, errorMsg
    imgZooms = np.array(imgZooms)
    print("Image zooms:", imgZooms)
    return imgZooms, None
#-------------------------------------------------------------------------
def calculateFramesFusionAndSizeAlpha(configData:dict):
    zoomArray, errorMsg = calculateZoomArray(configData)
    if errorMsg is not None:
        return None, errorMsg
    logZoomArray = np.log(zoomArray)
    totalFrames = int(configData['video_data']['FPS'] * configData['video_data']['duration'])
    framesLogsZooms = np.linspace(0, logZoomArray[-1], num=totalFrames)
    print("DEBUG - Frames logs zooms:", framesLogsZooms)
    indexesStepsList = []
    for frameLogZoom in framesLogsZooms:
        if frameLogZoom <= logZoomArray[0]:
            indexesStepsList.append((0, 0.0))
            continue
        #Find the index of the logZoomArray less or equal to frameLogZoom
        firstIndex = np.searchsorted(logZoomArray, frameLogZoom, side='left') - 1
        step = (frameLogZoom - logZoomArray[firstIndex]) / (logZoomArray[firstIndex + 1] - logZoomArray[firstIndex])
        indexesStepsList.append((firstIndex, step))
    return indexesStepsList, None
#-------------------------------------------------------------------------
class videoGeneratorClass:
    #---------------------------------------------------------------------
    def __init__(self, configData:dict, filename:str):
        self.configData = configData
        self.filename = filename
    #---------------------------------------------------------------------
    def openvideo(self):
        self.videoWriter = cv.VideoWriter(self.filename, cv.VideoWriter_fourcc(*'XVID'), 
                                          int(self.configData['video_data']['FPS']), 
                                          tuple(np.array(self.configData['video_data']['size'], dtype=np.int32)))
        if not self.videoWriter.isOpened():
            print("ERROR - Failed to open video writer")
            return False
        return True
    #---------------------------------------------------------------------
    def saveVideoFrame(self, frame):
        if hasattr(self, 'videoWriter') and self.videoWriter.isOpened():
            self.videoWriter.write(frame)
    #---------------------------------------------------------------------
    def closevideo(self):
        if hasattr(self, 'videoWriter') and self.videoWriter.isOpened():
            self.videoWriter.release()
    #---------------------------------------------------------------------
    def performVideoCalculations(self):
        self.indexesSizeAlphasList, errorMsg = calculateFramesFusionAndSizeAlpha(self.configData)
        if errorMsg:
            print("ERROR -", errorMsg)
            return False, errorMsg
        return True, None
    #---------------------------------------------------------------------
    def getTotalFrames(self):
        return len(self.indexesSizeAlphasList)
    #---------------------------------------------------------------------
    def generateVideoFrameOnPosition(self, position):
        if position < 0 or position >= len(self.indexesSizeAlphasList):
            print("ERROR - Invalid position")
            return None
        firstIndex, sizeAlpha = self.indexesSizeAlphasList[position]
        return self.generateVideoFrame(firstIndex, sizeAlpha)
    #---------------------------------------------------------------------
    def generateVideoFrame(self, firstIndex, sizeAlpha):
        print(f"DEBUG - Frame first index: {firstIndex}, sizeAlpha: {sizeAlpha}")
        interpolationMethod = self.configData['video_data'].get('interpolation_method', 'log')
        blendAlphaRange = self.configData['images_data'][firstIndex].get('alpha_range', (0.0, 1.0))
        blendAlpha = (sizeAlpha - blendAlphaRange[0]) / (blendAlphaRange[1] - blendAlphaRange[0])
        blendAlpha = np.clip(blendAlpha, 0.0, 1.0)
        return createBlendedFrame(self.configData, index=firstIndex, sizeAlpha=sizeAlpha, blendAlpha=blendAlpha, interpolationMethod=interpolationMethod)
    #---------------------------------------------------------------------
    def generateFullVideo(self):
        success, errorMsg = self.performVideoCalculations()
        if not success:
            return False, errorMsg
        if not self.openvideo():
            return False, "Failed to open video"
        for firstIndex, sizeAlpha in self.indexesSizeAlphasList:
            videoFrame = self.generateVideoFrame(firstIndex, sizeAlpha)
            self.saveVideoFrame(videoFrame)
        return True, None
#-------------------------------------------------------------------------
if __name__ == "__main__": 
    cfgFile = 'seed.zmr'
    cfgDict = loadConfig(cfgFile)
    videoGenerator = videoGeneratorClass(cfgDict, "seed.avi")
    videoGenerator.generateFullVideo()
    quit()


    cfgFile = 'prat.json'
    cfgDict = loadConfig(cfgFile)
    saveConfig("out.json", cfgDict)

    
    videoDims = np.array(cfgDict['video_data']['size'], dtype=np.int32)
    
    #Extract the first images pair data from the configuration dictionary
    img0 = cfgDict['images_data'][0]['image']
    frame0 = np.array(cfgDict['images_data'][0]['frame'], dtype=np.float32)
    nextPoints0 = np.array(cfgDict['images_data'][0]['next_points'], dtype=np.float32)
    
    img1 = cfgDict['images_data'][1]['image']
    frame1 = np.array(cfgDict['images_data'][1]['frame'], dtype=np.float32)
    prevPoints1 = np.array(cfgDict['images_data'][1]['prev_points'], dtype=np.float32)

    minBlendAlpha, maxBlendAlpha = getBlendAlphaRange(videoDims, img0.getCvImage(), nextPoints0, frame0, img1.getCvImage(), prevPoints1, frame1)
    print(f"DEBUG - blendAlphaRange = {minBlendAlpha} to {maxBlendAlpha}")
    for sizeAlpha in np.linspace(0, 1, num=NUM_FRAMES):
        blendAlpha = (sizeAlpha - minBlendAlpha) / (maxBlendAlpha - minBlendAlpha) 
        blendAlpha = np.clip(blendAlpha, 0.0, 1.0)
        print(f"DEBUG - sizeAlpha = {sizeAlpha}, blendAlpha = {blendAlpha}")
        blendedFrame = createBlendedFrame(cfgDict, 0, sizeAlpha, blendAlpha)

        cv.imshow(f'Blended Frame', blendedFrame)
        cv.waitKey(1)

    cv.waitKey(0)
    cv.destroyAllWindows()
    quit()
    
    #Convert the second image's previous points to the video dimensions using an affine transformation
    videoTransformedPrevPoints1 = convertImgPointsToVideoDimensions(prevPoints1, frame1, videoDims)
    
    img0FrameTransformer = affineTransformerClass(nextPoints0, videoTransformedPrevPoints1)
    
    videoFrame0 = img0FrameTransformer.transformImage(img0.getCvImage(), videoDims)
    markedVideoFrame0 = generateImageWithMarkers(videoFrame0, 
                                                [[0, 0],videoFrame0.shape[:2][::-1]], 
                                                None, 
                                                videoTransformedPrevPoints1)
    cv.imshow('MarkedVideoFrame0', markedVideoFrame0)
    cv.waitKey(0)
    cv.destroyAllWindows()
