# TODO

* Create a backendClass to put most of the backend methods and avoid the multiple parameter passing
* Include the following video options:
  * Continuous log (this is the current one)
    * It requires a continuous zoom in or zoom out
    * Uses log interpolation in the fusions
    * Place the video frames to form a continuos zoom rate (log) in all the video
  * Images equally distributed on time
    * Fusion options
      * linear
      * log
    * Option to spline in the zoom levels
  * Time defined on fusion
    * No more global video time
    * Select the duration in the fusion editor
    * Fusion options
      * linear
      * log
* 4 alignment points
  * Uses homographic transform instead of affine
* N (>4) alingnment points
  * Uses Delaunay Triangulation and & Voronoi Diagram (https://learnopencv.com/delaunay-triangulation-and-voronoi-diagram-using-opencv-c-python/)
* Option to auto fix rotation between images
* Option to invert the full sequence of images
* Multiplatform