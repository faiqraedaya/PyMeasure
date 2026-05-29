"""Unit tests for pymeasure.core.prefs formatting (pure, no Qt required)."""
import math

from pymeasure.core.prefs import DisplayPrefs


def test_fmt_value_sig_figs():
    p = DisplayPrefs(value_sig_figs=3)
    assert p.fmt_value(1234.5678) == "1.23e+03"
    assert p.fmt_value(0.00123456) == "0.00123"


def test_fmt_coord_decimals():
    assert DisplayPrefs(coord_decimals=2).fmt_coord(3.14159) == "3.14"
    assert DisplayPrefs(coord_decimals=0).fmt_coord(3.6) == "4"


def test_fmt_angle_degrees():
    assert DisplayPrefs(angle_in_radians=False).fmt_angle(90.0) == "90.00°"


def test_fmt_angle_radians():
    out = DisplayPrefs(angle_in_radians=True, value_sig_figs=4).fmt_angle(180.0)
    assert out.endswith(" rad")
    assert math.isclose(float(out[:-4]), math.pi, rel_tol=1e-3)


def _run():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"{len(tests)} prefs tests passed")


if __name__ == "__main__":
    _run()
