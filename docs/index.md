# Zoomer documentation

Zoomer creates zoom videos by fusing pairs of images.

| Page | Contents |
| --- | --- |
| [Usage](usage.md) | Installing, starting the app and the editing workflow |
| [Project format](project-format.md) | `.zmr` project files and `zoomer.cfg` |
| [Architecture](architecture.md) | Modules, data flow, threading and history |
| [Development](development.md) | Environment, tests, linting and conventions |

## How a zoom video is built

1. Every image has a **frame**: the rectangle that becomes the video picture
   when that image is on screen.
2. For each consecutive pair, three **markers** are placed on the same
   features in both images (`next_points` on the first image, `prev_points`
   on the second).
3. The markers are mapped into video coordinates. The ratio between the mean
   side length of the two marker triangles is the zoom between the images;
   the ratios are multiplied along the chain to give the cumulative zoom of
   each image.
4. Video frames are spaced evenly in `log(zoom)` and each one is produced by
   scaling the two neighbouring images to the interpolated marker positions
   and cross-fading them with the pair's **alpha range**.
