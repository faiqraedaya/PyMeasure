import math
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Point:
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
class Measurement:
    kind: str  # "distance", "area", "angle"
    value: float
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    points: list = field(default_factory=list)  # [[x, y], ...] in image coords

    def display(self) -> str:
        if self.kind == "distance":
            return f"[{self.timestamp}] Distance: {self.value:.4f} {self.unit}"
        if self.kind == "area":
            return f"[{self.timestamp}] Area: {self.value:.4f} {self.unit}²"
        if self.kind == "angle":
            return f"[{self.timestamp}] Angle: {self.value:.2f}°"
        return f"[{self.timestamp}] {self.kind}: {self.value:.4f} {self.unit}"

    def display_short(self) -> str:
        if self.kind == "distance":
            return f"{self.value:.4g} {self.unit}"
        if self.kind == "area":
            return f"{self.value:.4g} {self.unit}²"
        if self.kind == "angle":
            return f"{self.value:.2f}°"
        return f"{self.value:.4g}"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "points": self.points,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Measurement":
        return cls(
            d["kind"], d["value"], d["unit"],
            d.get("timestamp", ""), d.get("points", []),
        )
