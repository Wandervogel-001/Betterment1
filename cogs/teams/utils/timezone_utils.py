import re
from typing import Optional

class TimezoneProcessor:
    """Handles parsing and compatibility scoring for timezones."""
    # This map is now the single source of truth for timezones.
    TIMEZONE_MAP = {
        "EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
        "PST": -8, "PDT": -7, "AKST": -9, "AKDT": -8, "HST": -10, "GMT": 0,
        "UTC": 0, "CET": 1, "CEST": 2, "EET": 2, "EEST": 3, "IST": 5.5,
        "JST": 9, "AEST": 10, "AEDT": 11,
    }

    def parse_to_utc_offset(self, tz_string: str) -> Optional[float]:
        """Parses a timezone string (abbreviation or UTC/GMT offset) to a float offset."""
        if not isinstance(tz_string, str):
            return None

        tz_upper = tz_string.upper().strip()
        if tz_upper in self.TIMEZONE_MAP:
            return self.TIMEZONE_MAP[tz_upper]

        match = re.match(r"(?:UTC|GMT)\s?([+-])(\d{1,2})(?::(\d{2}))?", tz_upper)
        if match:
            sign, hours, minutes = match.groups()
            offset = float(hours) + (float(minutes) / 60.0 if minutes else 0.0)
            return offset if sign == '+' else -offset

        return None

    def calculate_compatibility(self, tz_offset1: Optional[float], tz_offset2: Optional[float]) -> float:
        """Calculates timezone compatibility using a linear decay model (0-9 hours)."""
        if tz_offset1 is None or tz_offset2 is None:
            return 0.0
        hour_diff = abs(tz_offset1 - tz_offset2)
        # Score is 1.0 for 0 diff, decaying to 0.0 for >= 9 hours diff.
        return max(0.0, 1.0 - (hour_diff / 9.0))
