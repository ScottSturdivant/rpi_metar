"""Weather parsing utilities."""
import logging
import re
from fractions import Fraction


log = logging.getLogger(__name__)


def get_conditions(metar_info):
    """Returns the visibility and ceiling for a given airport from some metar info."""
    log.debug(metar_info)
    visibility = ceiling = None
    # Visibility
    # We may have fractions, e.g. 1/8SM or 1 1/2SM
    # Or it will be whole numbers, e.g. 2SM
    # There's also variable wind speeds, followed by vis, e.g. 300V360 1/2SM
    match = re.search(r'(?P<visibility>\b(?:\d+\s+)?\d+(?:/\d)?)SM', metar_info)
    if match:
        visibility = match.group('visibility')
        try:
            visibility = float(sum(Fraction(s) for s in visibility.split()))
        except ZeroDivisionError:
            visibility = None
    # Ceiling
    match = re.search(r'(VV|BKN|OVC)(?P<ceiling>\d{3})', metar_info)
    if match:
        ceiling = int(match.group('ceiling')) * 100  # It is reported in hundreds of feet
        return visibility, ceiling
    return (visibility, ceiling)


def get_flight_category(visibility, ceiling):
    """Converts weather conditions into a category."""
    log.debug('Finding category for %s, %s', visibility, ceiling)
    if visibility is None and ceiling is None:
        return FlightCategory.UNKNOWN

    # Unlimited ceiling
    if visibility and ceiling is None:
        ceiling = 10000

    # http://www.faraim.org/aim/aim-4-03-14-446.html
    if visibility < 1 or ceiling < 500:
        return FlightCategory.LIFR
    elif 1 <= visibility < 3 or 500 <= ceiling < 1000:
        return FlightCategory.IFR
    elif 3 <= visibility <= 5 or 1000 <= ceiling <= 3000:
        return FlightCategory.MVFR
    elif visibility > 5 and ceiling > 3000:
        return FlightCategory.VFR
    raise ValueError
