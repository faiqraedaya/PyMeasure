from enum import Enum


class Tool(Enum):
    PAN = "pan"
    SET_ORIGIN = "set_origin"
    SET_SCALE_DISTANCE = "set_scale_distance"
    SET_SCALE_COORDS = "set_scale_coords"
    ADD_POINT = "add_point"
    MEASURE_DISTANCE = "measure_distance"
    MEASURE_ANGLE = "measure_angle"
    MEASURE_AREA = "measure_area"


TOOL_LABELS = {
    Tool.PAN: "Pan / Zoom",
    Tool.SET_ORIGIN: "Set Origin",
    Tool.SET_SCALE_DISTANCE: "Scale – Distance",
    Tool.SET_SCALE_COORDS: "Scale – Coordinates",
    Tool.ADD_POINT: "Add Point",
    Tool.MEASURE_DISTANCE: "Measure Distance",
    Tool.MEASURE_ANGLE: "Measure Angle",
    Tool.MEASURE_AREA: "Measure Area",
}

TOOL_SHORTCUTS = {
    Tool.PAN: "P",
    Tool.SET_ORIGIN: "O",
    Tool.SET_SCALE_DISTANCE: "S",
    Tool.SET_SCALE_COORDS: "C",
    Tool.ADD_POINT: "A",
    Tool.MEASURE_DISTANCE: "D",
    Tool.MEASURE_ANGLE: "G",
    Tool.MEASURE_AREA: "E",
}

TOOL_HELP = {
    Tool.PAN: "Pan/Zoom — drag to pan · scroll to zoom · Ctrl+0 to fit",
    Tool.SET_ORIGIN: "Set Origin — click to place the coordinate origin",
    Tool.SET_SCALE_DISTANCE: "Scale (Distance) — click 2 points of known distance",
    Tool.SET_SCALE_COORDS: "Scale (Coords) — click 2 points of known coordinates",
    Tool.ADD_POINT: "Add Point — click to add a labelled point",
    Tool.MEASURE_DISTANCE: "Measure Distance — click 2 points",
    Tool.MEASURE_ANGLE: "Measure Angle — click 3 points (middle point is vertex)",
    Tool.MEASURE_AREA: "Measure Area — click vertices · right-click to close polygon",
}
