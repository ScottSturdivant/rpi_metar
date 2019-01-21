#!/usr/bin/env python
from rpi_metar import sources, core
from rpi_metar.leds import GREEN, BLACK
from rpi_ws281x import PixelStrip
import configparser


def main():
    config = configparser.ConfigParser()
    config['settings'] = {'brightness': 75}
    cfg_file = '/etc/rpi_metar.conf'

    leds = PixelStrip(num=2000, pin=18, gamma=core.GAMMA, brightness=128)
    leds.begin()

    # If there's an existing config file, see if we want to continue where we left off or just
    # overwrite it.
    i = 0
    airports = {}
    try:
        config.read([cfg_file])
    except:
        pass
    else:
        prompt = None
        while prompt not in ['c', 'o']:
            prompt = input('cfg file exists.  [c]ontinue or [o]verwrite')
        if prompt == 'c':
            for code in config.options('airports'):
                index = config.getint('airports', code)
                airports[code.upper()] = index
            i = max(airports.values()) + 1

    code = None
    while code != 'q':
        core.set_all(leds, BLACK)
        leds.setPixelColor(i, GREEN)
        leds.show()

        code = input('Code:   [s]kip or [q]uit ').casefold()
        if code == 'q':
            break
        if code == 's':
            i += 1
            continue

        if len(code) == 3:
            code = 'k' + code
        code = code.upper()
        noaa = sources.NOAA([code])
        try:
            noaa.get_metar_info()
        except:
            prompt = None
            while prompt not in ['k', 'r']:
                prompt = input('{code} is invalid.  [k]eep or [r]etry '.format(code=code))
            if prompt == 'r':
                continue

        if code in airports:
            prompt = None
            while prompt not in ['k', 'r']:
                prompt = input('{code} has already been set.  [k]eep or [r]etry '.format(code=code))
            if prompt == 'r':
                continue

        airports[code] = i
        i += 1

    core.set_all(leds, BLACK)
    config['airports'] = airports
    with open(cfg_file, 'w') as f:
        config.write(f)
    print('Wrote {file}'.format(file=cfg_file))
