from RPi import GPIO
import logging

log = logging.getLogger(__name__)


# The two pins that the encoder uses (BCM numbering).
GPIO_A = 23
GPIO_B = 25


class RotaryEncoder:

    def __init__(self, callback, gpio_a=GPIO_A, gpio_b=GPIO_B):
        self.last_gpio = None
        self.gpio_a = gpio_a
        self.gpio_b = gpio_b
        self.callback = callback

        self.level_a = 0
        self.level_b = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(self.gpio_a, GPIO.BOTH, self._callback)
        GPIO.add_event_detect(self.gpio_b, GPIO.BOTH, self._callback)

    def destroy(self):
        GPIO.remove_event_detect(self.gpio_a)
        GPIO.remove_event_detect(self.gpio_b)
        GPIO.cleanup()

    def reset(self):
        self.last_gpio = None
        self.level_a = 0
        self.level_b = 0

    def _callback(self, channel):
        level = GPIO.input(channel)
        log.debug('{channel} = {level}'.format(channel=channel, level=level))
        if channel == self.gpio_a:
            self.level_a = level
        else:
            self.level_b = level

        if level != 1:
            return

        # When both inputs are at 1, we'll fire a callback. If A was the most recent pin set high,
        # it'll be forward, and if B was the most recent pin set high, it'll be reverse.
        if channel != self.last_gpio:  # debounce
            self.last_gpio = channel
            log.debug('set last_gpio to {channel}'.format(channel=channel))
            if channel == self.gpio_a and self.level_b == 1:
                log.debug('A is set and B was already set, callback(1)')
                self.callback(1)
                self.reset()
            elif channel == self.gpio_b and self.level_a == 1:
                log.debug('B is set and A was already set, callback(-1)')
                self.callback(-1)
                self.reset()
