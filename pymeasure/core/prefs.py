"""Global display preferences and the formatting helpers that read them.

A tiny module-level singleton keeps number formatting consistent across the
objects list, canvas labels, status bar and scale bar without threading a
settings object through every call. It is intentionally Qt-free: the GUI layer
loads/saves these fields from QSettings, but the formatting itself stays pure
and unit-testable.
"""
import math
from dataclasses import dataclass


@dataclass
class DisplayPrefs:
    value_sig_figs: int = 4     # significant figures for lengths / areas
    coord_decimals: int = 4     # decimal places for world coordinates
    angle_in_radians: bool = False

    def fmt_value(self, v: float) -> str:
        """Format a measurement magnitude (length, area) — no unit appended."""
        return f"{v:.{self.value_sig_figs}g}"

    def fmt_coord(self, v: float) -> str:
        """Format a single world coordinate."""
        return f"{v:.{self.coord_decimals}f}"

    def fmt_angle(self, deg: float) -> str:
        """Format an angle (stored in degrees) with its unit."""
        if self.angle_in_radians:
            return f"{math.radians(deg):.{self.value_sig_figs}g} rad"
        return f"{deg:.2f}°"


# Shared singleton. Mutated in place by the GUI so existing references stay live.
PREFS = DisplayPrefs()
