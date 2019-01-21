from RPi import GPIO
import logging

log = logging.getLogger(__name__)


# The two pins that the encoder uses (BCM numbering).
GPIO_A = 23
GPIO_B = 25


class RotaryEncoder:

    def __init__(self, callback, gpioA=GPIO_A, gpioB=GPIO_B):
        self.lastGpio = None
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.callback = callback

        self.levA = 0
        self.levB = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpioA, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpioB, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(self.gpioA, GPIO.BOTH, self._callback)
        GPIO.add_event_detect(self.gpioB, GPIO.BOTH, self._callback)

    def destroy(self):
        GPIO.remove_event_detect(self.gpioA)
        GPIO.remove_event_detect(self.gpioB)
        GPIO.cleanup()

    def _callback(self, channel):
        level = GPIO.input(channel)
        log.debug('{channel} = {level}'.format(channel=channel, level=level))
        if channel == self.gpioA:
            self.levA = level
        else:
            self.levB = level

        # Debounce.
        if channel == self.lastGpio:
            log.debug('debounced.')
            return

        # When both inputs are at 1, we'll fire a callback. If A was the most recent pin set high,
        # it'll be forward, and if B was the most recent pin set high, it'll be reverse.
        self.lastGpio = channel
        log.debug('set lastGpio to {channel}'.format(channel=channel))
        if channel == self.gpioA and level == 1:
            if self.levB == 1:
                log.debug('A is set and B was already set, callback(1)')
                self.callback(1)
        elif channel == self.gpioB and level == 1:
            if self.levA == 1:
                log.debug('B is set and A was already set, callback(-1)')
                self.callback(-1)
