# File formats

## Project (`.zmr`)

A JSON document. Images are stored by path and are loaded into
`zoomer.backend.ImageClass` objects when the project is opened. Saving always
writes absolute image paths.

```json
{
  "project_name": "Leaf",
  "video_data": {
    "size": [1920, 1080],
    "FPS": 30,
    "duration": 10,
    "interpolation_method": "log",
    "format": "avi"
  },
  "images_data": [
    {
      "image": "/home/me/leaf_images/leaf_1.jpg",
      "frame": [[120.0, 80.0], [1080.0, 620.0]],
      "prev_points": null,
      "next_points": [[300.0, 200.0], [500.0, 220.0], [420.0, 400.0]],
      "alpha_range": [0.2, 0.8]
    }
  ]
}
```

| Key | Meaning |
| --- | --- |
| `project_name` | Name shown in the window title |
| `video_data.size` | Output `[width, height]` in pixels |
| `video_data.FPS` | Frames per second |
| `video_data.duration` | Length in seconds; frames = `FPS * duration` |
| `video_data.interpolation_method` | `"log"` (default) or `"linear"` marker interpolation |
| `video_data.format` | Output container extension, selected from formats probed by the active OpenCV installation (default `"avi"`) |
| `images_data[].image` | Image path |
| `images_data[].frame` | `[[x0, y0], [x1, y1]]` crop in image pixels, with the video aspect ratio |
| `images_data[].next_points` | Three `[x, y]` markers matched with the next image; `null` on the last image |
| `images_data[].prev_points` | Three markers matched with the previous image; `null` on the first image |
| `images_data[].alpha_range` | Optional `[start, end]` in `0..1` (default `[0.0, 1.0]`) stored on the first image of a pair |

A relative image path is resolved against the current working directory
when the project is opened, so keep paths absolute (as saved) or open
projects from the directory they were written for.

## Application config (`zoomer.cfg`)

```json
{
  "frame_crosshair": true,
  "marker_thickness": 2,
  "auto_open_last_project": false,
  "last_project": ""
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `frame_crosshair` | `true` | Draw the frame centre crosshair in the editors |
| `marker_thickness` | `2` | Colored alignment-cross stroke and each outline edge, in pixels (clamped to `1..10`) |
| `auto_open_last_project` | `false` | Reopen `last_project` on start |
| `last_project` | `""` | Absolute path of the most recently opened or saved project |

Missing keys fall back to the defaults; an unreadable file is ignored.

## Recovery (`autosave.zmr`)

`autosave.zmr` uses the same JSON project structure as a named `.zmr` file.
It is atomically replaced after each project change and is offered for
recovery on the next launch. Explicit Save and Save As write the named project
file separately; Save does not rename or remove the recovery file.
