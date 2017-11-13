#!/usr/bin/env python
import threading
import requests
import logging
import logging.handlers
import re
import time
from enum import Enum
from configparser import ConfigParser
from retrying import retry
from rpi_ws281x import PixelStrip, Color


log = logging.getLogger(__name__)

METAR_REFRESH_RATE = 5 * 60  # How often METAR data should be fetched, in seconds

GREEN = Color(0, 255, 0)
RED = Color(255, 0, 0)
BLUE = Color(0, 0, 255)
MAGENTA = Color(255, 0, 255)
YELLOW = Color(255, 255, 0)
BLACK = Color(0, 0, 0)

# For gamma correction
# https://learn.adafruit.com/led-tricks-gamma-correction/the-issue
GAMMA = [
    0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
    0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  1,  1,  1,
    1,  1,  1,  1,  1,  1,  1,  1,  1,  2,  2,  2,  2,  2,  2,  2,
    2,  3,  3,  3,  3,  3,  3,  3,  4,  4,  4,  4,  4,  5,  5,  5,
    5,  6,  6,  6,  6,  7,  7,  7,  7,  8,  8,  8,  9,  9,  9, 10,
   10, 10, 11, 11, 11, 12, 12, 13, 13, 13, 14, 14, 15, 15, 16, 16,
   17, 17, 18, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23, 24, 24, 25,
   25, 26, 27, 27, 28, 29, 29, 30, 31, 32, 32, 33, 34, 35, 35, 36,
   37, 38, 39, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 50,
   51, 52, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 66, 67, 68,
   69, 70, 72, 73, 74, 75, 77, 78, 79, 81, 82, 83, 85, 86, 87, 89,
   90, 92, 93, 95, 96, 98, 99,101,102,104,105,107,109,110,112,114,
  115,117,119,120,122,124,126,127,129,131,133,135,137,138,140,142,
  144,146,148,150,152,154,156,158,160,162,164,167,169,171,173,175,
  177,180,182,184,186,189,191,193,196,198,200,203,205,208,210,213,
  215,218,220,223,225,228,231,233,236,239,241,244,247,249,252,255,
]


class FlightCategory(Enum):
    VFR = GREEN
    IFR = RED
    MVFR = BLUE
    LIFR = MAGENTA
    UNKNOWN = YELLOW

# This relates an LED index to an airport.
AIRPORT_CODES = {}
# This is a mapping of the LED position to their current color value.
# It will be updated by the refresh_metar thread and read by the render_leds thread.
LEDS = {}

# Where we'll be fetching the METAR info from.
URL = 'http://www.aviationweather.gov/metar/data?ids={airport_codes}&format=raw&hours=0&taf=off&layout=off&date=0'

# Certain statuses should result in the LEDS blinking.  Inclimate weather conditions
# and failure to fetch current weather info seem to fit the bill.
BLINKING_CATEGORIES = set([FlightCategory.LIFR, FlightCategory.UNKNOWN])


def init_logger():
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
    handler = logging.handlers.SysLogHandler(address='/dev/log')
    handler.setFormatter(formatter)
    log.addHandler(handler)


@retry(wait_exponential_multiplier=1000,
       wait_exponential_max=10000,
       stop_max_attempt_number=10)
def get_metar_info(airport_codes):
    """Queries the METAR service."""
    log.info("Getting METAR info.")
    response = requests.get(URL.format(airport_codes=','.join(airport_codes.values())))
    response.raise_for_status()
    return response


def get_conditions(metar_info, airport_code):
    """Returns the visibility and ceiling for a given airport from some metar info."""
    visibility = ceiling = None
    for line in metar_info.splitlines():
        if line.startswith(airport_code):
            log.debug(line)
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
    """Converts weather conditions into a category."""
    log.debug('Finding category for %s, %s', visibility, ceiling)
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


def render_leds(leds, flag):
    """Responsible for updating the LEDS.

    This is in a separate thread so that the blinking lights can be running
    without interfering with the periodic refresh of the METAR data.
    """
    blink_period = 1.0

    def _blink(leds):
        for position, category in LEDS.items():
            color = category.value
            leds.setPixelColor(position, color)
        leds.show()
        time.sleep(blink_period / 2)

        for position, category in LEDS.items():
            color = category.value if category not in BLINKING_CATEGORIES else BLACK
            leds.setPixelColor(position, color)
        leds.show()
        time.sleep(blink_period / 2)

    while flag.is_set():
        try:
            _blink(leds)
        except:  # noqa
            log.exception('Unhandled exception.')
            flag.clear()

    log.info('Exiting.')


def refresh_metar(flag):
    """Fetches new METAR information and updates the airport LEDS with the current info."""
    metar_next_refresh_at = time.time()

    def _refresh():
        try:
            info = get_metar_info(AIRPORT_CODES)
        except:  # noqa
            log.exception('Failed to retrieve metar info.')
            for position in LEDS:
                LEDS[position] = FlightCategory.UNKNOWN

        for position, code in AIRPORT_CODES.items():
            visibility, ceiling = get_conditions(info.content.decode('utf-8'), code)
            category = get_flight_category(visibility, ceiling)
            LEDS[position] = category

    while flag.is_set():
        if time.time() < metar_next_refresh_at:
            # We wake up early to make sure the other thread hasn't ended.
            time.sleep(1.0)
            continue

        try:
            _refresh()
        except:  # noqa
            log.exception('Failed to refresh METAR info.')
            flag.clear()
        else:
            metar_next_refresh_at = time.time() + METAR_REFRESH_RATE

    log.info('Exiting.')


def all_off(leds):
    """Sets all leds off."""
    for i in range(leds.numPixels()):
        leds.setPixelColor(i, BLACK)
    leds.show()


def load_configuration():
    cfg_files = ['/etc/rpi_metar.conf', './rpi_metar.conf']

    cfg = ConfigParser()
    cfg.read(cfg_files)

    for code in cfg.options('airports'):
        index = cfg.getint('airports', code)
        AIRPORT_CODES[index] = code.upper()
        LEDS[index] = FlightCategory.UNKNOWN


def main():

    init_logger()

    load_configuration()
    log.debug('cfg loaded.')
    log.debug(AIRPORT_CODES)
    log.debug(LEDS)

    leds = PixelStrip(max(AIRPORT_CODES.keys()) + 1, 18, gamma=GAMMA)
    leds.begin()
    all_off(leds)

    # This flag allows us to stop all of the threads if one has died.  It's not much
    # use if the render thread runs while the refresh METAR thread has died.  So if
    # one thread dies, so should the other, then the program should terminate and
    # systemd would be responsible for restarting it.
    flag = threading.Event()
    flag.set()

    threads = [
        threading.Thread(name='render_leds', target=render_leds, args=(leds, flag)),
        threading.Thread(name='refresh_metar', target=refresh_metar, args=(flag,)),
    ]

    for thread in threads:
        thread.daemon = True
        thread.start()

    try:
        while threading.active_count() > 0:
            time.sleep(1.0)
    except:  # noqa
        log.exception("It's quitin' time.")
    finally:
        all_off(leds)


if __name__ == '__main__':
    main()
