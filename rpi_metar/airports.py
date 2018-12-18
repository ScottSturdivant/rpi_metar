import threading
import logging
import time
from enum import Enum
from queue import Queue
from rpi_metar.leds import GREEN, RED, BLUE, MAGENTA, YELLOW, WHITE

FAILURE_THRESHOLD = 3  # How many times do we not get data before we reboot
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

    def __init__(self, code, led_index):
        self.code = code.upper()
        self.index = led_index
        self.visibility = None
        self.ceiling = None
        self.raw = None
        self.thunderstorms = False
        self.wind_speed = 0
        self.wind_gusts = 0
        self._category = FlightCategory.UNKNOWN
        # Give each airport a lock. Since multiple threads may be trying to manipulate this LED
        # at once, only one should win.
        self.lock = threading.Lock()

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
        return self.wind_speed > MAX_WIND_SPEED_KTS or self.wind_gusts > MAX_WIND_SPEED_KTS

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

    def show_lightning(self, leds, strike_duration):
        with self.lock:
            leds.setPixelColor(self.index, WHITE)
            leds.show()
            time.sleep(strike_duration)

            leds.setPixelColor(self.index, self.category.value)
            leds.show()

    def show_wind(self, leds, indicator_duration):
        with self.lock:
            leds.setPixelColor(self.index, YELLOW)
            leds.show()
            time.sleep(indicator_duration)

            leds.setPixelColor(self.index, self.category.value)
            leds.show()
