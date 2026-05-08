# PyMeasure

A desktop tool for making precise measurements on images and PDFs. Set a real-world scale, place labelled points, and measure distances, angles, and polygon areas.

## Requirements

- Python 3.10+
- PySide6
- PyMuPDF

Install dependencies:

```
pip install -r requirements.txt
```

## Running

```
python main.py
```

## Features

| Feature | Details |
|---|---|
| **Open files** | PNG, JPEG, BMP, TIFF images and multi-page PDFs |
| **Pan & zoom** | Drag to pan, scroll wheel to zoom, Ctrl+0 to fit |
| **Set origin** | Click to place the coordinate origin (world 0,0) |
| **Set scale** | By known distance between two points, or by entering known coordinates |
| **Add points** | Click to place labelled points; world coordinates shown on canvas |
| **Measure distance** | Click two points |
| **Measure angle** | Click three points (middle point is the vertex) |
| **Measure area** | Click polygon vertices, right-click to close |
| **Undo / Redo** | Full undo/redo stack for all state changes |
| **Export** | CSV, JSON, or clipboard |
| **Sessions** | Save and reload the full measurement state as JSON |

## Keyboard shortcuts

| Key | Action |
|---|---|
| `P` | Pan / Zoom tool |
| `O` | Set Origin |
| `S` | Scale by Distance |
| `C` | Scale by Coordinates |
| `A` | Add Point |
| `D` | Measure Distance |
| `G` | Measure Angle |
| `E` | Measure Area |
| `Escape` | Cancel current measurement |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save session |
| `Ctrl+E` | Export data |
| `Ctrl+0` | Fit to window |
| `Ctrl+=` | Zoom in |
| `Ctrl+-` | Zoom out |

## Project structure

```
main.py               Entry point
pymeasure/
    models.py         Data classes: Point, ScaleInfo, Measurement
    constants.py      Tool enum and UI metadata
    dialogs.py        Qt dialogs for scale input, point labels, and export
    viewer.py         ImageViewer widget (rendering, pan/zoom, measurement logic)
    panel.py          LeftPanel sidebar widget
    window.py         MainWindow and app entry point
requirements.txt
```

## Session file format

Sessions are saved as JSON with the following top-level keys:

```json
{
  "scale_info": { "pixel_distance": 1.0, "real_distance": 1.0, "unit": "m" },
  "origin":     { "x": 0.0, "y": 0.0, "label": "" },
  "points":     [ { "x": 100.0, "y": 200.0, "label": "A" } ],
  "measurements": [
    { "kind": "distance", "value": 5.3, "unit": "m", "timestamp": "14:22:01" }
  ]
}
```
