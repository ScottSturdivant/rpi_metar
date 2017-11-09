#!/usr/bin/env python
import asyncio
import requests
import logging
import re
from enum import Enum
from retrying import retry
# from neopixel import Color
def Color(red, green, blue, white = 0):
    return (white << 24) | (red << 16)| (green << 8) | blue

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

GREEN = Color(0, 255, 0)
RED = Color(255, 0, 0)
BLUE = Color(0, 0, 255)
MAGENTA = Color(255, 0, 255)
YELLOW = Color(255, 255, 0)
BLACK = Color(0, 0, 0)


class FlightCategory(Enum):
    VFR = GREEN
    IFR = RED
    MVFR = BLUE
    LIFR = MAGENTA
    UNKNOWN = YELLOW


TOGGLE = {
    FlightCategory.UNKNOWN.value: BLACK,
    BLACK: FlightCategory.UNKNOWN.value,
}


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

class Dummy():
    def __init__(self, *args, **kwargs):
        pass

    def begin(self):
        pass

    def setPixelColor(self, pos, col):
        pass

    def show(self):
        pass


class LEDS(object):

    def __init__(self):
        # self._strip = Adafruit_NeoPixel(len(AIRPORT_CODES))
        self._strip = Dummy()
        self._strip.begin()
        # A dictionary mapping LED positions to their current color value.
        self._leds = {position: FlightCategory.UNKNOWN.value for position in AIRPORT_CODES}
        self.display()


    def update_color(self, position, color):
        self._leds[position] = color

    async def display(self):
        while True:
            print('Displaying.')
            for position, color in self._leds.items():
                if color in TOGGLE:
                    color = TOGGLE[color]
                # Update the actual LED
                self._strip.setPixelColor(position, color)
                # And update our reference
                self._leds[position] = color
            self._strip.show()
            await asyncio.sleep(0.5)


async def refresh_metar_info(leds):
    while True:
        print("Updating metar info.")
        try:
            info = get_metar_info()
        except:
            log.exception('Failed to retrieve metar info.')
            for position in AIRPORT_CODES:
                leds.update_color(position, FlightCategory.UNKNOWN.value)
            await asyncio.sleep(60)

        for position, code in AIRPORT_CODES.items():
            visibility, ceiling = get_visibility_and_ceiling(info.content.decode('utf-8'), code)
            # print(code, visibility, ceiling)
            category = get_flight_category(visibility, ceiling)
            leds.update_color(position, category.value)
        await asyncio.sleep(5 * 60)


def main():
    leds = LEDS()

    loop = asyncio.get_event_loop()
    loop.create_task(leds.display())
    loop.create_task(refresh_metar_info(leds))
    loop.run_forever()

if __name__ == '__main__':
    main()
