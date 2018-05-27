#!/usr/bin/env python
from fractions import Fraction
import requests
import logging
import logging.handlers
import re
import time
from enum import Enum
from configparser import ConfigParser
from retrying import retry
from rpi_ws281x import PixelStrip, Color
from xmltodict import parse as parsexml


log = logging.getLogger(__name__)

METAR_REFRESH_RATE = 5 * 60  # How often METAR data should be fetched, in seconds

# The rpi_ws281x library initializes the strip as GRB.
GREEN = Color(255, 0, 0)
RED = Color(0, 255, 0)
BLUE = Color(0, 0, 255)
MAGENTA = Color(0, 255, 255)
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


class Airport(object):

    def __init__(self, code, led_index):
        self.code = code.upper()
        self.index = led_index
        self.visibility = None
        self.ceiling = None
        self.raw = None
        self.category = FlightCategory.UNKNOWN

    def __repr__(self):
        return '<{code} @ {index}: {raw} -> {cat}>'.format(
            code=self.code,
            index=self.index,
            raw=self.raw,
            cat=self.category.name
        )

    def reset(self):
        self.visibility = None
        self.ceiling = None
        self.raw = None
        self.category = FlightCategory.UNKNOWN


# A collection of the airports we'll ultimately be tracking.
AIRPORTS = {}

# Where we'll be fetching the METAR info from.
URL = (
    'https://www.aviationweather.gov/adds/dataserver_current/httpparam'
    '?dataSource=metars'
    '&requestType=retrieve'
    '&format=xml'
    '&stationString={airport_codes}'
    '&hoursBeforeNow=2'
    '&mostRecentForEachStation=true'
    '&fields=flight_category,station_id,raw_text'
)


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
    """Queries the METAR service.

    Returns a list of dicts.
    """
    log.info("Getting METAR info.")
    url = URL.format(airport_codes=','.join(airport_codes))
    log.debug(url)
    try:
        response = requests.get(url, timeout=10.0)
        response.raise_for_status()
    except:  # noqa
        log.exception('Metar query failure.')
        raise

    try:
        response = parsexml(response.text)['response']['data']['METAR']
    except:
        log.exception('Metar response is invalid.')
        raise

    return response


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


def run(leds):
    """Fetches new METAR information and updates the airport LEDS with the current info."""

    while True:

        try:
            metars = get_metar_info(AIRPORTS.keys())
        except:  # noqa
            log.exception('Failed to retrieve metar info.')
            for airport in AIRPORTS.values():
                airport.category = FlightCategory.UNKNOWN
                # Visually indicate a failure to refresh the data.
                color = airport.category.value
                leds.setPixelColor(airport.index, color)
            leds.show()
            time.sleep(METAR_REFRESH_RATE)
            continue

        metars = {m['station_id']: m for m in metars}

        for airport in AIRPORTS.values():

            # Make sure the previous iteration is cleared out.
            airport.reset()

            try:
                metar = metars[airport.code]
                log.debug(metar)
                airport.raw = metar['raw_text']
            except KeyError:
                log.exception('%s has no data.', airport.code)
                airport.category = FlightCategory.UNKNOWN
            else:
                try:
                    airport.category = FlightCategory[metar['flight_category']]
                except KeyError:
                    log.exception('%s does not have flight category field, falling back to raw text parsing.', airport.code)
                    airport.visibility, airport.ceiling = get_conditions(metar['raw_text'])
                    try:
                        airport.category = get_flight_category(airport.visibility, airport.ceiling)
                    except (TypeError, ValueError):
                        log.exception("Failed to get flight category from %s, %s", airport.visibility, airport.ceiling)
                        airport.category = FlightCategory.UNKNOWN
            finally:
                color = airport.category.value
                leds.setPixelColor(airport.index, color)

        leds.show()
        log.info(sorted(AIRPORTS.values(), key=lambda x: x.index))
        time.sleep(METAR_REFRESH_RATE)


def set_all(leds, color=BLACK):
    """Sets all leds to a specific color."""
    for i in range(leds.numPixels()):
        leds.setPixelColor(i, color)
    leds.show()


def load_configuration():
    cfg_files = ['/etc/rpi_metar.conf', './rpi_metar.conf']

    cfg = ConfigParser()
    cfg.read(cfg_files)

    # Fix typo in CO map cfg
    if 'khlx' in cfg['airports']:
        cfg['airports']['klhx'] = cfg['airports'].pop('khlx')
        with open('/etc/rpi_metar.conf', 'w') as f:
            try:
                cfg.write(f)
            except:
                pass

    for code in cfg.options('airports'):

        index = cfg.getint('airports', code)
        AIRPORTS[code] = Airport(code, index)


def main():

    init_logger()

    load_configuration()

    leds = PixelStrip(max((airport.index for airport in AIRPORTS.values())) + 1, 18, gamma=GAMMA)
    leds.begin()
    set_all(leds, BLACK)

    for airport in AIRPORTS.values():
        leds.setPixelColor(airport.index, YELLOW)
    leds.show()
    run(leds)

    try:
        run(leds)
    except Exception as e:
        log.exception('Unexpected exception, shutting down.')
        set_all(leds, BLACK)


if __name__ == '__main__':
    main()
