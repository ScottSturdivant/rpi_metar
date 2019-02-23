import logging
from queue import Queue
from rpi_metar import wx

MAX_WIND_SPEED_KTS = 30  # When it's too windy, in knots.

log = logging.getLogger(__name__)


LED_QUEUE = Queue()


class Airport(object):

    def __init__(self, code, led_index, max_wind_speed_kts=MAX_WIND_SPEED_KTS, unknown_off=True):
        self.code = code.upper()
        self.index = led_index
        self.visibility = None
        self.ceiling = None
        self.raw = None
        self.thunderstorms = False
        self.wind_speed = 0
        self.wind_gusts = 0
        self.max_wind_speed = max_wind_speed_kts
        self._category = wx.FlightCategory.UNKNOWN
        self._unknown_count = 0
        self._unknown_off = unknown_off

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
        return (self.wind_speed > self.max_wind_speed or self.wind_gusts > self.max_wind_speed) and self.category != wx.FlightCategory.OFF

    @property
    def category(self):
        return self._category

    @category.setter
    def category(self, cat):
        if cat is None:
            cat = wx.FlightCategory.UNKNOWN

        if cat == wx.FlightCategory.UNKNOWN:
            self._unknown_count += 1
            if self._unknown_count >= 3:
                if self._unknown_off:
                    cat = wx.FlightCategory.OFF
                else:
                    cat = wx.FlightCategory.MISSING
        else:
            self._unknown_count = 0

        if self._category != cat:
            log.info('Changing {self} to {cat}'.format(self=self, cat=cat))
            self._category = cat
            log.info('Setting category, putting {} onto queue.'.format(self.code))
            LED_QUEUE.put(self.code)

    def process_metar(self, metars):
        # Make sure previous iterations are cleared out
        self.reset()

        try:
            metar = metars[self.code]
            log.debug(metar)
            self.raw = metar['raw_text']
        except KeyError:
            log.exception('{} has no data.'.format(self.code))
            self.category = wx.FlightCategory.UNKNOWN
            return

        # Thunderstorms
        self.thunderstorms = any(word in metar['raw_text'] for word in ['TSRA', 'VCTS']) and self.category != wx.FlightCategory.OFF

        # Wind info
        try:
            self.wind_speed = int(metar['wind_speed_kt'])
        except KeyError:
            pass

        try:
            self.wind_gusts = int(metar['wind_gust_kt'])
        except KeyError:
            pass

        # Flight categories. First automatic, then manual parsing.
        try:
            if metar['flight_category'] is None:
                log.error('flight category is missing: {}', metar)
            self.category = wx.FlightCategory[metar['flight_category']]
        except KeyError:
            log.info('%s does not have flight category field, falling back to raw text parsing.', self.code)
            self.visibility, self.ceiling, self.wind_speed, self.wind_gusts = wx.get_conditions(metar['raw_text'])
            self.category = wx.get_flight_category(self.visibility, self.ceiling)
