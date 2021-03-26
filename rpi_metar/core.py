#!/usr/bin/env python
import enum

import requests
import logging
import logging.handlers
import os
import socket
import signal
import sys
import time
import threading
from configparser import ConfigParser
from rpi_ws281x import PixelStrip
from rpi_metar import cron, sources, encoder
from rpi_metar.airports import Airport, LED_QUEUE, MAX_WIND_SPEED_KTS, Legend
from rpi_metar import wx
from rpi_metar import leds as colors
from queue import Queue


log = logging.getLogger(__name__)


METAR_REFRESH_RATE = 5 * 60  # How often METAR data should be fetched, in seconds
WIND_DISPLAY_RATE = 5  # How often to show that it's windy, in seconds
LIGHTNING_STRIKE_RATE = 5  # How regularly should lightning strike, in seconds

FAILURE_THRESHOLD = 3  # How many times do we not get data before we reboot

ENCODER_QUEUE = Queue()
METAR_QUEUE = Queue()
ENCODER_EVENT = threading.Event()
METAR_EVENT = threading.Event()

# A collection of the airports we'll ultimately be tracking.
AIRPORTS = {}


def is_internet_up():
    try:
        response = requests.get('http://google.com', timeout=10.0)
        response.raise_for_status()
    except:  # noqa
        return False
    return True


def fetch_metars(queue, cfg):
    """Fetches new METAR information periodically."""
    failure_count = 0

    # Load the desired data sources from the user configuration.
    srcs = cfg.get('settings', 'sources', fallback='NOAA,NOAABackup,SkyVector').split(',')
    srcs = [getattr(sources, src.strip()) for src in srcs]

    while True:

        metars = {}
        # Allow duplicate LEDs by only using the first 4 chars as the ICAO. Anything else after it helps keep it unique.
        airport_codes = set([code[:4] for code in AIRPORTS.keys()])
        for source in srcs:
            try:
                data_source = source(list(airport_codes), config=cfg)
            except:  # noqa
                log.exception('Unable to create data source.')
                continue

            try:
                info = data_source.get_metar_info()
                log.info('Retrieved: %s', info)
                metars.update(info)
                failure_count = 0
            except:  # noqa
                log.exception('Failed to retrieve metar info.')

            # We have retrieved METAR info, but did we get responses for all stations? If we did
            # not, let's request those missing stations from the other sources. Perhaps they have
            # the info!
            airport_codes = airport_codes - set(metars.keys())
            if not airport_codes:
                # Nothing else needs to be retrieved
                break

        # We have exhausted the list of sources.
        if not metars:
            metars = None

            # Some of the raspberry pis lose their wifi after some time and fail to automatically
            # reconnect. This is a workaround for that case. If we've failed a lot, just reboot.
            # We do need to make sure we're not rebooting too soon (as would be the case for
            # initial setup).
            failure_count += 1

            # If other web services are available, it's just the NOAA site having problems so we
            # don't need to reboot.
            if failure_count >= FAILURE_THRESHOLD and not is_internet_up():
                log.warning('Internet is not up, rebooting.')
                os.system('reboot')

        queue.put(metars)
        time.sleep(cfg.getint('settings', 'metar_refresh_rate', fallback=METAR_REFRESH_RATE))


def process_metars(queue, leds):
    """Converts METAR info info Flight Categories and updates the LEDs."""

    airports = AIRPORTS.values()

    # When the system first starts up, waiting for all of the LEDs to fade into their correct
    # colors can take a very long time. To mitigate this, we'll just slam the colors into place
    # if this is the first time this thread is executing.
    first = True

    while True:

        try:
            metars = queue.get()
            if metars is None:
                for airport in airports:
                    airport.category = wx.FlightCategory.UNKNOWN
                continue

            for airport in airports:
                airport.process_metar(metars)

                if first:
                    leds.setPixelColor(airport.index, airport.category.value)

            if first:
                first = False
                leds.show()

            # Let the weather checkers know the info is refreshed
            METAR_EVENT.set()

            log.info(sorted(AIRPORTS.values(), key=lambda x: x.index))

        except:  # noqa
            log.exception('metar processor error')


def render_leds(queue, leds, cfg):
    """Updates the LED strand when something pops onto the queue."""
    while True:
        log.info('waiting for queue.')
        airport_code = queue.get()
        log.info('got {}'.format(airport_code))
        airport = AIRPORTS[airport_code.upper()]
        # This is our target color.
        color = airport.category.value

        if not cfg.getboolean('settings', 'do_fade', fallback=True):
            leds.setPixelColor(airport.index, color)
            leds.show()
            continue

        # Let's try to fade to our desired color
        start_color = leds.getPixelColor(airport.index)
        start_g = start_color >> 16 & 0xff
        start_r = start_color >> 8 & 0xff
        start_b = start_color & 0xff

        end_g = color >> 16 & 0xff
        end_r = color >> 8 & 0xff
        end_b = color & 0xff

        with leds.lock:  # Don't let lightning or wind interrupt us.
            while((start_r != end_r) or (start_g != end_g) or (start_b != end_b)):
                if start_r < end_r:
                    start_r += 1
                elif start_r > end_r:
                    start_r -= 1
                if start_g < end_g:
                    start_g += 1
                elif start_g > end_g:
                    start_g -= 1
                if start_b < end_b:
                    start_b += 1
                elif start_b > end_b:
                    start_b -= 1

                leds.setPixelColorRGB(airport.index, start_g, start_r, start_b)
                leds.show()


def lightning(leds, event, cfg):
    """Briefly changes LEDs to white, indicating lightning in the area."""
    airports = AIRPORTS.values()
    strike_duration = cfg.getfloat('settings', 'lightning_duration', fallback=1.0)
    legend = cfg.getint('legend', 'lightning', fallback=None)
    legend = [Legend('LIGHTNING', legend, wx.FlightCategory.OFF)] if legend else []
    while True:
        # Which airports currently are experiencing thunderstorms
        ts_airports = [airport for airport in airports if airport.thunderstorms] + legend
        log.debug("LIGHTNING @: {}".format(ts_airports))
        if ts_airports:
            with leds.lock:
                for airport in ts_airports:
                    leds.setPixelColor(airport.index, wx.FlightCategory.THUNDERSTORM.value)
                leds.show()
                time.sleep(strike_duration)

                for airport in ts_airports:
                    leds.setPixelColor(airport.index, airport.category.value)
                leds.show()
            time.sleep(LIGHTNING_STRIKE_RATE - strike_duration)
        else:
            # Sleep until the next metar refresh...
            event.wait(cfg.getint('settings', 'metar_refresh_rate', fallback=METAR_REFRESH_RATE))
            event.clear()


def wind(leds, event, cfg):
    """Briefly changes LEDs to yellow, indicating it's too windy."""
    airports = AIRPORTS.values()
    indicator_duration = cfg.getfloat('settings', 'wind_duration', fallback=1.0)
    legend = cfg.getint('legend', 'wind', fallback=None)
    legend = [Legend('WIND', legend, wx.FlightCategory.OFF)] if legend else []
    while True:
        # Which locations are currently breezy
        windy_airports = [airport for airport in airports if airport.windy] + legend
        log.debug('WINDY @: {}'.format(windy_airports))
        if windy_airports:
            # We want wind indicators to appear simultaneously.
            with leds.lock:
                for airport in windy_airports:
                    leds.setPixelColor(airport.index, wx.FlightCategory.WINDY.value)
                leds.show()
                time.sleep(indicator_duration)

                for airport in windy_airports:
                    leds.setPixelColor(airport.index, airport.category.value)
                leds.show()

            time.sleep(WIND_DISPLAY_RATE - indicator_duration)
        else:
            event.wait(cfg.getint('settings', 'metar_refresh_rate', fallback=METAR_REFRESH_RATE))
            event.clear()


def set_all(leds, color=colors.BLACK):
    """Sets all leds to a specific color."""
    for i in range(leds.numPixels()):
        leds.setPixelColor(i, color)
    leds.show()


def load_configuration():
    cfg_files = ['/etc/rpi_metar.conf', './rpi_metar.conf']

    cfg = ConfigParser(converters={'color': colors.get_color})
    cfg.read(cfg_files)

    if 'megamap' in socket.gethostname():
        cfg.set('settings', 'unknown_off', 'False')
        cfg.write(open('/etc/rpi_metar.conf', 'w'))


    # If we have redefined a color value (e.g. tweaked green a bit), or changed what should be displayed entirely (e.g.
    # display ORANGE for LIFR), we need to rebuild the FlightCategory enum.
    enum_needs_update = cfg.has_section('colors') or cfg.has_section('flight_categories')

    # Load colors first so we can associate those to flight categories / behaviors
    if cfg.has_section('colors'):
        for color_name in cfg.options('colors'):
            color_name = color_name.upper()
            color_value = cfg.getcolor('colors', color_name)
            # And the hacks begin. Set these newly defined colors in the module.
            setattr(colors, color_name.upper(), color_value)
            log.debug('Setting custom color: {} -> {}'.format(color_name, color_value))

    # Now that colors should all be set, let's associate them to categories / behaviors
    categories_to_colors = {
        'VFR': colors.GREEN,
        'IFR': colors.RED,
        'LIFR': colors.MAGENTA,
        'MVFR': colors.BLUE,
        'UNKNOWN': colors.YELLOW,
        'OFF': colors.BLACK,
        'MISSING': colors.ORANGE,
        'THUNDERSTORM': colors.WHITE,
        'WINDY': colors.YELLOW,
    }

    if cfg.has_section('flight_categories'):
        for category_name in cfg.options('flight_categories'):
            category_name = category_name.upper()
            if category_name not in categories_to_colors:
                log.warning('{} is not a valid flight category, ignoring.'.format(category_name))
                continue
            color_value = cfg.getcolor('flight_categories', category_name)
            log.debug('Overriding default color for {}, setting to: {}'.format(category_name, color_value))
            categories_to_colors[category_name] = color_value

    if enum_needs_update:
        wx.FlightCategory = enum.Enum(
            'FlightCategory',
            categories_to_colors
        )

    max_wind_speed_kts = cfg.getint('settings', 'max_wind', fallback=MAX_WIND_SPEED_KTS)
    unknown_off = cfg.getboolean('settings', 'unknown_off', fallback=True)

    for code in cfg.options('airports'):
        index = cfg.getint('airports', code)
        AIRPORTS[code.upper()] = Airport(code, index, max_wind_speed_kts=max_wind_speed_kts, unknown_off=unknown_off)



    return cfg


def on_turn(delta):
    """Let the brightness adjustment thread be aware that it needs to do something."""
    log.debug("on turn called.")
    ENCODER_QUEUE.put(delta)
    ENCODER_EVENT.set()


def adjust_brightness(leds, cfg):
    while not ENCODER_QUEUE.empty():
        delta = ENCODER_QUEUE.get() * 5
        brightness = leds.getBrightness()
        try:
            leds.setBrightness(brightness + delta)
        except OverflowError:
            log.info('New brightness exceeds limits: {}'.format(brightness + delta))
        else:
            leds.show()
            log.info('Set brightness to {}'.format(brightness + delta))

    # Now that we've handled everything in the queue, write out the current brightness into the
    # config file. This way it persists upon reboots / restarts, etc.
    if 'settings' not in cfg:
        cfg['settings'] = {}
    cfg['settings']['brightness'] = str(leds.getBrightness())
    with open('/etc/rpi_metar.conf', 'w') as f:
        cfg.write(f)
    log.info('Saved new brightness ({}) to cfg file.'.format(leds.getBrightness()))

    # Indicate that we've handled the event.
    ENCODER_EVENT.clear()


def wait_for_knob(event, leds, cfg):
    while True:
        try:
            event.wait()
            adjust_brightness(leds, cfg)
        except:
            log.exception('unexpected error')


def set_legend(leds, cfg):
    """Sets a few LEDs to fixed colors, for use with a legend."""
    if not cfg.has_section('legend'):
        return

    for category in wx.FlightCategory:
        index = cfg.getint('legend', category.name.casefold(), fallback=None)
        if index is not None:
            leds.setPixelColor(index, category.value)
            log.info('Legend: set %s to %s.', index, category.name)


def get_num_leds(cfg):
    """Returns the number of LEDs as defined in the configuration file.

    It takes into account that LEDs can be defined in both the 'airports' and 'legend' sections.
    """
    airport_max = max((airport.index for airport in AIRPORTS.values()))
    legend_max = 0
    if cfg.has_section('legend'):
        legend_max = max((int(v) for v in cfg['legend'].values()))

    return max([airport_max, legend_max]) + 1


def main():

    # Register the encoder to handle changing the brightness
    knob = encoder.RotaryEncoder(callback=on_turn)

    def on_exit(sig, frame):
        knob.destroy()
        set_all(leds, colors.BLACK)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    cron.set_upgrade_schedule()

    cfg = load_configuration()

    kwargs = {
        'num': get_num_leds(cfg),
        'pin': 18,
        'gamma': colors.GAMMA,
        'brightness': int(cfg.get('settings', 'brightness', fallback=128))
    }
    # Sometimes if we use LED strips from different batches, they behave differently with the gamma
    # controls and brightness levels. Therefore we need to be able to disable the gamma controls.
    if cfg.get('settings', 'disable_gamma', fallback=False):
        kwargs.pop('gamma')

    leds = PixelStrip(**kwargs)
    leds.begin()
    leds.lock = threading.Lock()
    set_all(leds, wx.FlightCategory.UNKNOWN.value)

    for airport in AIRPORTS.values():
        leds.setPixelColor(airport.index, wx.FlightCategory.UNKNOWN.value)
    set_legend(leds, cfg)
    leds.show()

    # Kick off a thread to handle adjusting the brightness
    t = threading.Thread(name='brightness', target=wait_for_knob, args=(ENCODER_EVENT, leds, cfg))
    t.start()

    # A thread to fetch metar information periodically
    t = threading.Thread(name='metar_fetcher', target=fetch_metars, args=(METAR_QUEUE, cfg))
    t.start()

    # A thread to process metar info.
    t = threading.Thread(name='metar_processor', target=process_metars, args=(METAR_QUEUE, leds))
    t.start()

    # A thread to change the LEDs when airport categories change.
    t = threading.Thread(name='render_leds', target=render_leds, args=(LED_QUEUE, leds, cfg))
    t.start()

    # A thread for lightning
    if cfg.get('settings', 'lightning', fallback=True):
        t = threading.Thread(name='lightning', target=lightning, args=(leds, METAR_EVENT, cfg))
        t.start()

    # A thread for wind
    if cfg.get('settings', 'wind', fallback=True):
        t = threading.Thread(name='wind', target=wind, args=(leds, METAR_EVENT, cfg))
        t.start()


if __name__ == '__main__':
    main()
