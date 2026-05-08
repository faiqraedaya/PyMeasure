import math
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Point:
    """Internal coordinate type used for temp points and origin only."""
    x: float
    y: float
    label: str = ""

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "label": self.label}

    @classmethod
    def from_dict(cls, d: dict) -> "Point":
        return cls(d["x"], d["y"], d.get("label", ""))


@dataclass
class ScaleInfo:
    pixel_distance: float = 1.0
    real_distance: float = 1.0
    unit: str = "px"

    @property
    def scale_factor(self) -> float:
        return self.real_distance / self.pixel_distance if self.pixel_distance > 0 else 1.0

    def to_dict(self) -> dict:
        return {
            "pixel_distance": self.pixel_distance,
            "real_distance": self.real_distance,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScaleInfo":
        return cls(d["pixel_distance"], d["real_distance"], d["unit"])


@dataclass
class DiagramObject:
    """A persistent diagram annotation: point, distance, angle, or area."""
    kind: str        # "point" | "distance" | "angle" | "area"
    name: str = ""
    points: list = field(default_factory=list)   # [[x, y], ...] image coords
    unit: str = "px"
    value: float = 0.0   # pre-computed measurement value; unused for points
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    _ICONS = {"point": "●", "distance": "─ ", "angle": "∠ ", "area": "▣ ", "polyline": "〜 "}

    def list_label(self) -> str:
        """Short label for the objects panel list."""
        icon = self._ICONS.get(self.kind, "? ")
        name = self.name if self.name else self.kind.capitalize()
        if self.kind == "point":
            return f"{icon}{name}"
        if self.kind in ("distance", "polyline"):
            return f"{icon}{name}: {self.value:.4g} {self.unit}"
        if self.kind == "angle":
            return f"{icon}{name}: {self.value:.2f}°"
        if self.kind == "area":
            return f"{icon}{name}: {self.value:.4g} {self.unit}²"
        return f"{icon}{name}"

    def display_short(self) -> str:
        """Compact value label drawn on the canvas."""
        if self.kind in ("distance", "polyline"):
            return f"{self.value:.4g} {self.unit}"
        if self.kind == "area":
            return f"{self.value:.4g} {self.unit}²"
        if self.kind == "angle":
            return f"{self.value:.2f}°"
        return self.name

    def display(self) -> str:
        """Full string for export / status bar."""
        ts = f"[{self.timestamp}] " if self.timestamp else ""
        name = self.name or self.kind.capitalize()
        if self.kind == "point":
            c = f"({self.points[0][0]:.4f}, {self.points[0][1]:.4f})" if self.points else ""
            return f"{ts}{name} {c}".strip()
        if self.kind in ("distance", "polyline"):
            return f"{ts}{name}: {self.value:.4f} {self.unit}"
        if self.kind == "area":
            return f"{ts}{name}: {self.value:.4f} {self.unit}²"
        if self.kind == "angle":
            return f"{ts}{name}: {self.value:.2f}°"
        return f"{ts}{name}: {self.value}"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "points": self.points,
            "unit": self.unit,
            "value": self.value,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DiagramObject":
        return cls(
            kind=d["kind"],
            name=d.get("name", d.get("label", "")),
            points=d.get("points", []),
            unit=d.get("unit", "px"),
            value=d.get("value", 0.0),
            timestamp=d.get("timestamp", ""),
        )
