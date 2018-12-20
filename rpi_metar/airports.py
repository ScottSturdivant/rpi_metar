import logging
from enum import Enum
from queue import Queue
from rpi_metar.leds import GREEN, RED, BLUE, MAGENTA, YELLOW

MAX_WIND_SPEED_KTS = 30  # When it's too windy, in knots.

log = logging.getLogger(__name__)


LED_QUEUE = Queue()


class FlightCategory(Enum):
    VFR = GREEN
    IFR = RED
    MVFR = BLUE
    LIFR = MAGENTA
    UNKNOWN = YELLOW


class Airport(object):

    def __init__(self, code, led_index, max_wind_speed_kts=MAX_WIND_SPEED_KTS):
        self.code = code.upper()
        self.index = led_index
        self.visibility = None
        self.ceiling = None
        self.raw = None
        self.thunderstorms = False
        self.wind_speed = 0
        self.wind_gusts = 0
        self.max_wind_speed = max_wind_speed_kts
        self._category = FlightCategory.UNKNOWN

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
        self.thunderstorms = False
        self.wind_speed = 0
        self.wind_gusts = 0

    @property
    def windy(self):
        return self.wind_speed > self.max_wind_speed or self.wind_gusts > self.max_wind_speed

    @property
    def category(self):
        return self._category

    @category.setter
    def category(self, cat):
        if self._category != cat:
            log.info('Changing {self} to {cat}'.format(self=self, cat=cat))
            self._category = cat
            log.info('Setting category, putting {} onto queue.'.format(self.code))
            LED_QUEUE.put(self.code)
