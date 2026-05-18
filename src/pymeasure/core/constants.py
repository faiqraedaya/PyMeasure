from enum import Enum


class Tool(Enum):
    PAN                  = "pan"
    ZOOM_RECT            = "zoom_rect"
    SET_ORIGIN           = "set_origin"
    SET_SCALE_DISTANCE   = "set_scale_distance"
    SET_SCALE_COORDS     = "set_scale_coords"
    ADD_POINT            = "add_point"
    ADD_LINE             = "add_line"
    ADD_ANGLE            = "add_angle"
    ADD_AREA             = "add_area"
    ADD_POLYLINE         = "add_polyline"


TOOL_LABELS = {
    Tool.PAN:                "Pan / Zoom",
    Tool.ZOOM_RECT:          "Zoom Rectangle",
    Tool.SET_ORIGIN:         "Set Origin",
    Tool.SET_SCALE_DISTANCE: "Scale – Distance",
    Tool.SET_SCALE_COORDS:   "Scale – Coordinates",
    Tool.ADD_POINT:          "Add Point",
    Tool.ADD_LINE:           "Add Line",
    Tool.ADD_ANGLE:          "Add Angle",
    Tool.ADD_AREA:           "Add Area",
    Tool.ADD_POLYLINE:       "Add Polyline",
}

TOOL_SHORTCUTS = {
    Tool.PAN:                "Space",
    Tool.ZOOM_RECT:          "Z",
    Tool.SET_ORIGIN:         "O",
    Tool.SET_SCALE_DISTANCE: "S",
    Tool.SET_SCALE_COORDS:   "C",
    Tool.ADD_POINT:          "T",
    Tool.ADD_LINE:           "L",
    Tool.ADD_ANGLE:          "G",
    Tool.ADD_AREA:           "A",
    Tool.ADD_POLYLINE:       "N",
}

TOOL_HELP = {
    Tool.PAN:                "Pan/Zoom — drag to pan · scroll to zoom · Ctrl+0 to fit",
    Tool.ZOOM_RECT:          "Zoom Rectangle — drag to draw a rectangle and zoom into it",
    Tool.SET_ORIGIN:         "Set Origin — click to place the coordinate origin",
    Tool.SET_SCALE_DISTANCE: "Scale (Distance) — click 2 points of known distance",
    Tool.SET_SCALE_COORDS:   "Scale (Coords) — click 2 points of known coordinates",
    Tool.ADD_POINT:          "Add Point — click to add a labelled point",
    Tool.ADD_LINE:           "Add Line — click 2 points to measure a straight line",
    Tool.ADD_ANGLE:          "Add Angle — click 3 points (middle point is the vertex)",
    Tool.ADD_AREA:           "Add Area — click vertices · double-click or right-click to close",
    Tool.ADD_POLYLINE:       "Add Polyline — click vertices · double-click or right-click to finish",
}
