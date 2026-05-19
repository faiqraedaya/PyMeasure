# PyMeasure

A desktop GUI for making precise measurements on images and PDFs — set a real-world scale, annotate with
labelled objects, and measure distances, angles, areas, and polyline lengths.

## Features

- Open PNG, JPEG, BMP, TIFF images and multi-page PDFs
- Set coordinate origin and scale (by known distance or known point coordinates)
- Add labelled points, lines, angles, areas, and polylines
- Select, move, cut, copy, and paste objects; drag individual vertex handles
- Right-click a vertex to delete it; right-click an edge to insert a new vertex
- Shift-lock to cardinal directions while placing measurement points
- Export results to CSV, JSON, or clipboard; save and reload full sessions

## Requirements

- Python 3.13+
- PySide6 >= 6.5
- PyMuPDF >= 1.23

## Installation

```bash
git clone https://github.com/faiqraedaya/PyMeasure
cd PyMeasure
uv pip install -r requirements.txt   # or: pip install -r requirements.txt
```

## Quick start

```bash
python main.py
```

The application opens with a blank canvas. Use **File → Open** (`Ctrl+O`) to load an image or PDF,
then set a scale before placing measurements.

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
| `A`         | Add Area (double-click or right-click to close)  |
| `N`         | Add Polyline (double-click or right-click to finish) |
| `Escape`    | Cancel current operation                         |
| `Ctrl+Z`    | Undo                                             |
| `Ctrl+Y`    | Redo                                             |
| `Ctrl+O`    | Open file                                        |
| `Ctrl+S`    | Save session                                     |
| `Ctrl+Shift+O` | Load session                                  |
| `Ctrl+E`    | Export data                                      |
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

`kind` is one of `"point"`, `"distance"`, `"angle"`, `"area"`, or `"polyline"`.

## Project structure

```
main.py                    Entry point
src/
  pymeasure/
    core/
      models.py            Data classes: Point, ScaleInfo, DiagramObject
      constants.py         Tool enum, labels, shortcuts, and help text
    gui/
      dialogs.py           Scale input, point label, export, and edit dialogs
      viewer.py            ImageViewer widget (rendering, pan/zoom, measurement logic)
      panel.py             LeftPanel (tools, scale info) and RightPanel (objects list)
      window.py            MainWindow and application entry point
requirements.txt
pyproject.toml
uv.lock
```