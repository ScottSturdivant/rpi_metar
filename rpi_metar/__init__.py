import logging
import logging.handlers
import pkg_resources
import socket


class ContextFilter(logging.Filter):
    hostname = socket.gethostname()
    version = pkg_resources.get_distribution('rpi_metar').version

    def filter(self, record):
        record.hostname = ContextFilter.hostname
        record.version = ContextFilter.version
        return True


ctx_filter = ContextFilter()


def init_logger():

    log = logging.getLogger(__name__)

    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(version)s - %(threadName)s - %(message)s')
    handler = logging.handlers.SysLogHandler(address='/dev/log')
    handler.setFormatter(formatter)
    handler.addFilter(ctx_filter)
    log.addHandler(handler)


init_logger()
