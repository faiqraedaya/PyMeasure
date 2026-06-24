# PyMeasure

A desktop GUI for making precise measurements on images and PDFs — set a real-world scale, annotate with
labelled objects, and measure distances, angles, polygon area/perimeter, and polyline lengths.

## Features
- Interactive GUI built with PySide6
- Open PNG, JPEG, BMP, TIFF images and multi-page PDFs
- Set coordinate origin and scale (by known distance or known point coordinates)
- Add labelled points, lines, angles, polygons, polylines, ellipses, and text boxes
- Draw **risk contours** around a polyline or point: each contour defines up to 20
  levels (reference value, distance, color) and renders smooth rounded boundaries

## Installation

```bash
git clone https://github.com/faiqraedaya/PyMeasure
cd PyMeasure
uv sync
```

## Quick start

```bash
uv run main.py
```

## Keyboard shortcuts

| Key         | Tool / Action                                    |
|-------------|--------------------------------------------------|
| `Space`     | Pan / Zoom                                       |
| `Z`         | Zoom Rectangle                                   |
| `O`         | Set Origin                                       |
| `S`         | Scale by Distance                                |
| `C`         | Scale by Coordinates                             |
| `T`         | Add Point                                        |
| `L`         | Add Line                                         |
| `G`         | Add Angle (middle click = vertex)                |
| `A`         | Add Polygon (double-click or right-click to close) |
| `N`         | Add Polyline (double-click or right-click to finish) |
| `E`         | Add Ellipse (2 corners; hold Shift for a circle) |
| `B`         | Add Text Box (2 corners, then enter text/style)  |
| `K`         | Add Polyline Contour (finish, then define levels) |
| `P`         | Add Point Contour (click, then define levels)    |
| `Ctrl+L`    | Toggle text labels                               |
| `Escape`    | Cancel current operation                         |
| `Ctrl+Z`    | Undo                                             |
| `Ctrl+Y`    | Redo                                             |
| `Ctrl+N`    | New (unload current drawing)                     |
| `Ctrl+O`    | Open file                                        |
| `Ctrl+S`    | Save session                                     |
| `Ctrl+Shift+O` | Load session                                  |
| `Ctrl+E`    | Export data                                      |
| `Ctrl+Shift+E` | Export view as image                          |
| `Ctrl+0`    | Fit to window                                    |
| `Ctrl+=`    | Zoom in                                          |
| `Ctrl+-`    | Zoom out                                         |
| `Ctrl+A`    | Select all                                       |
| `Ctrl+X`    | Cut selection                                    |
| `Ctrl+C`    | Copy selection                                   |
| `Ctrl+V`    | Paste                                            |
| `Del`       | Delete selected                                  |

## Session file format

Sessions are saved as JSON:

```json
{
  "scale_info": { "pixel_distance": 1.0, "real_distance": 1.0, "unit": "m" },
  "origin":     { "x": 0.0, "y": 0.0, "label": "" },
  "objects": [
    {
      "kind": "distance",
      "name": "Wall",
      "points": [[100.0, 200.0], [400.0, 200.0]],
      "unit": "m",
      "value": 3.0,
      "timestamp": "14:22:01"
    }
  ]
}
```

`kind` is one of `"point"`, `"distance"`, `"angle"`, `"polygon"`, `"polyline"`,
`"ellipse"`, `"textbox"`, `"polyline_contour"`, or `"point_contour"` (the legacy
`"area"` is loaded as `"polygon"`). Objects may also carry a `"color"` (hex line
color), `"line_width"`, `"line_style"` (`solid`/`dashed`/`dotted`/`dashdot`), and a
`"measures"` map of named secondary measurements (e.g. area + perimeter). Text
boxes add `"text"`, `"font_family"`, `"font_size"`, `"font_color"`, `"fill_color"`,
`"bold"`, `"italic"`, `"underline"`, `"h_align"` (`left`/`center`/`right`), and
`"v_align"` (`top`/`middle`/`bottom`); contours add a `"levels"` list of
`{ "reference": str, "distance": float, "color": "#rrggbb" }`. The session may
include a `"legend_title"` string.

## LICENSE

[MIT](LICENSE)