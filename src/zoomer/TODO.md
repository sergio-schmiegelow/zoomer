# TODO

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
* Clean remaining images on preview after deleting from files list
* Put numbers with the alignment markers
* Option to auto fix rotation between images
* Zoom auto
* Temporarily remove the "logarithm" option in the movie menu (until implement the alternatives)
* Option to invert the full sequence of images