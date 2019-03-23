#!/usr/bin/env python
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
from rpi_metar.leds import BLACK, YELLOW, WHITE, GAMMA
from rpi_metar.airports import Airport, LED_QUEUE, MAX_WIND_SPEED_KTS
from rpi_metar.wx import FlightCategory
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

    airport_codes = list(AIRPORTS.keys())
    data_sources = [
        sources.NOAA(airport_codes),
        sources.NOAA(airport_codes, 'bcaws'),
        sources.SkyVector(airport_codes),
    ]

    while True:
        for source in data_sources:
            try:
                metars = source.get_metar_info()
                failure_count = 0
                break
            except:  # noqa
                log.exception('Failed to retrieve metar info.')
        else:  # No data sources returned any info
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
                    airport.category = FlightCategory.UNKNOWN
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
        airport = AIRPORTS[airport_code.lower()]
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
    while True:
        # Which airports currently are experiencing thunderstorms
        ts_airports = [airport for airport in airports if airport.thunderstorms]
        log.debug("LIGHTNING @: {}".format(ts_airports))
        if ts_airports:
            with leds.lock:
                for airport in ts_airports:
                    leds.setPixelColor(airport.index, WHITE)
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
    while True:
        # Which locations are currently breezy
        windy_airports = [airport for airport in airports if airport.windy]
        log.debug('WINDY @: {}'.format(windy_airports))
        if windy_airports:
            # We want wind indicators to appear simultaneously.
            with leds.lock:
                for airport in windy_airports:
                    leds.setPixelColor(airport.index, YELLOW)
                leds.show()
                time.sleep(indicator_duration)

                for airport in windy_airports:
                    leds.setPixelColor(airport.index, airport.category.value)
                leds.show()

            time.sleep(WIND_DISPLAY_RATE - indicator_duration)
        else:
            event.wait(cfg.getint('settings', 'metar_refresh_rate', fallback=METAR_REFRESH_RATE))
            event.clear()


def set_all(leds, color=BLACK):
    """Sets all leds to a specific color."""
    for i in range(leds.numPixels()):
        leds.setPixelColor(i, color)
    leds.show()


def load_configuration():
    cfg_files = ['/etc/rpi_metar.conf', './rpi_metar.conf']

    cfg = ConfigParser()
    cfg.read(cfg_files)

    if 'megamap' in socket.gethostname():
        cfg.set('settings', 'unknown_off', 'False')
        cfg.write(open('/etc/rpi_metar.conf', 'w'))

    max_wind_speed_kts = cfg.getint('settings', 'max_wind', fallback=MAX_WIND_SPEED_KTS)
    unknown_off = cfg.getboolean('settings', 'unknown_off', fallback=True)

    for code in cfg.options('airports'):
        index = cfg.getint('airports', code)
        AIRPORTS[code] = Airport(code, index, max_wind_speed_kts=max_wind_speed_kts, unknown_off=unknown_off)

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


def main():

    # Register the encoder to handle changing the brightness
    knob = encoder.RotaryEncoder(callback=on_turn)

    def on_exit(sig, frame):
        knob.destroy()
        set_all(leds, BLACK)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    cron.set_upgrade_schedule()

    cfg = load_configuration()

    if cfg.getboolean('settings', 'papertrail', fallback=True):
        from rpi_metar import papertrail
        logger = logging.getLogger('rpi_metar')
        logger.addHandler(papertrail)

    kwargs = {
        'num': max((airport.index for airport in AIRPORTS.values())) + 1,
        'pin': 18,
        'gamma': GAMMA,
        'brightness': int(cfg.get('settings', 'brightness', fallback=128))
    }
    # Sometimes if we use LED strips from different batches, they behave differently with the gamma
    # controls and brightness levels. Therefore we need to be able to disable the gamma controls.
    if cfg.get('settings', 'disable_gamma', fallback=False):
        kwargs.pop('gamma')

    leds = PixelStrip(**kwargs)
    leds.begin()
    leds.lock = threading.Lock()
    set_all(leds, BLACK)

    for airport in AIRPORTS.values():
        leds.setPixelColor(airport.index, YELLOW)
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
