#!/usr/bin/env python
import requests
import logging
import re
from enum import Enum
from retrying import retry

log = logging.getLogger()

# This is a mapping of the LED position on the strip to an airport code.
AIRPORT_CODES = {
    0: 'KBOS',
    1: 'KBED',
    2: 'KOWD',
    3: 'KLWM',
    4: 'KBVY',
    5: 'KFIT',
    6: 'KTAN',
    7: 'KGHG',
    8: 'KPYM',
    9: 'KPVC',
    10: 'KCQX',
    11: 'KHYA',
    12: 'KFMH',
    13: 'KACK',
    14: 'KMVY',
    15: 'KEWB',
    16: 'KORH',
    17: 'KORE',
    18: 'KASH',
    19: 'KMHT',
    20: 'KAFN',
    21: 'KEEN',
    22: 'KSFZ',
    23: 'KPVD',
    24: 'KOQU',
    25: 'KUUU',
    26: 'KDEN',
}

URL = 'http://www.aviationweather.gov/metar/data?ids={airport_codes}&format=raw&hours=0&taf=off&layout=off&date=0'


class FlightCategory(Enum):
    VFR = 'green'
    IFR = 'red'
    MVFR = 'blue'
    LIFR = 'magenta'
    UNKNOWN = 'yellow'


@retry(wait_exponential_multiplier=1000,
       wait_exponential_max=10000,
       stop_max_attempt_number=10)
def get_metar_info(airport_codes=AIRPORT_CODES):
    response = requests.get(URL.format(airport_codes=','.join(airport_codes.values())))
    response.raise_for_status()
    return response


def get_visibility_and_ceiling(metar_info, airport_code):
    """Returns the visibility and ceiling for a given airport from some meta info."""
    visibility = ceiling = None
    for line in metar_info.splitlines():
        if line.startswith(airport_code):
            # Visibility
            # We may have fractions, e.g. 1/8SM
            # Or it will be whole numbers, e.g. 2SM
            match = re.search(r'(?P<visibility>\d+(/\d)?)SM', line)
            if match:
                visibility = match.group('visibility')
                try:
                    visibility = int(visibility)
                except ValueError:  # Fractions...
                    visibility = eval(visibility)
            # Ceiling
            match = re.search(r'(VV|BKN|OVC)(?P<ceiling>\d{3})', line)
            if match:
                ceiling = int(match.group('ceiling')) * 100  # It is reported in hundreds of feet
            return visibility, ceiling
    return (visibility, ceiling)


def get_flight_category(visibility, ceiling):
    if visibility is None and ceiling is None:
        return FlightCategory.UNKNOWN
    elif visibility >= 5 and (ceiling is None or ceiling >= 3000):
        return FlightCategory.VFR
    elif 3 <= visibility <= 5 or 1000 <= ceiling <= 3000:
        return FlightCategory.MVFR
    elif 1 <= visibility <= 3 or 500 <= ceiling <= 1000:
        return FlightCategory.IFR
    elif visibility <= 1 or ceiling <= 500:
        return FlightCategory.LIFR
    raise ValueError




def main():
    leds = Adafruit_NeoPixel(len(AIRPORT_CODES))
    leds.begin()

    for position in AIRPORT_CODES:
        leds.setPixelColor(position, FlightCategory.UNKNOWN.value)
    leds.show()

    while True:
        try:
            info = get_metar_info()
        except:
            log.exception('Failed to retrieve metar info.')
            for position in AIRPORT_CODES:
                leds.setPixelColor(position, FlightCategory.UNKNOWN.value)
            leds.show()
            time.sleep(60)
            continue

        for position, code in AIRPORT_CODES.items():
            visibility, ceiling = get_visibility_and_ceiling(info.content.decode('utf-8'), code)
            category = get_flight_category(visibility, ceiling)
            leds.setPixelColor(position, category.value)

        leds.show()
        time.sleep(5 * 60)


if __name__ == '__main__':
    info = get_metar_info()
    for position, code in AIRPORT_CODES.items():
        visibility, ceiling = get_visibility_and_ceiling(info.content.decode('utf-8'), code)
        category = get_flight_category(visibility, ceiling)
        print('{}:\n\tVisibility: {}\n\tCeiling: {}\n\tCategory: {}'.format(code, visibility, ceiling, category))
