# PyMeasure

A desktop GUI for making precise measurements on images and PDFs — set a real-world scale, annotate with labelled objects, and measure distances, angles, areas, and polyline lengths.

## Features

- Open PNG, JPEG, BMP, TIFF images and multi-page PDFs
- Set coordinate origin and scale by known distance or known point coordinates
- Add labelled points, lines, angles, areas, and polylines
- Select, move, cut, copy, and paste objects with individual vertex handles
- Snap to existing vertices while measuring; on-canvas scale bar overlay
- Live takeoff totals (Σ length / Σ area) and configurable display precision
- Export results to CSV, JSON, clipboard, or an annotated image; save and reload full sessions

## Installation

```bash
git clone https://github.com/faiqraedaya/PyMeasure
cd PyMeasure
uv sync
```

## Usage

```bash
uv run main.py
```

## License

[MIT](LICENSE)
