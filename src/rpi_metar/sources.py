import logging
import requests

from retrying import retry
from xmltodict import parse as parsexml

log = logging.getLogger(__name__)


class NOAA:

    URL = (
        'https://{subdomain}.aviationweather.gov/adds/dataserver_current/httpparam'
        '?dataSource=metars'
        '&requestType=retrieve'
        '&format=xml'
        '&stationString={airport_codes}'
        '&hoursBeforeNow=2'
        '&mostRecentForEachStation=true'
    )

    def __init__(self, airport_codes, subdomain='www'):
        self.url = self.URL.format(airport_codes=','.join(airport_codes), subdomain=subdomain)

    @retry(wait_exponential_multiplier=1000,
           wait_exponential_max=10000,
           stop_max_attempt_number=10)
    def get_metar_info(self):
        """Queries the NOAA METAR service."""
        log.debug('Getting METAR info from NOAA.')
        log.info(self.url)
        try:
            response = requests.get(self.url, timeout=10.0)
            response.raise_for_status()
        except:  # noqa
            log.exception('Metar query failure.')
            raise

        try:
            response = parsexml(response.text)['response']['data']['METAR']
        except:  # noqa
            log.exception('Metar response is invalid.')
            raise

        return {m['station_id']: m for m in response}


class SkyVector:

    URL = (
        'https://skyvector.com/api/dLayer'
        '?ll=39.80136,-104.81039'
        '&ll1=38.48928,-105.15646'
        '&ll2=41.08887,-104.46432'
        '&layers=metar'
    )

    def __init__(self, airport_codes):
        # Set lat / long info ...
        self.airport_codes = airport_codes
        self.url = self.URL  # apply formatting...

    @retry(wait_exponential_multiplier=1000,
           wait_exponential_max=10000,
           stop_max_attempt_number=10)
    def get_metar_info(self):
        log.debug('Getting METAR info from SkyVector.')
        log.info(self.url)
        try:
            response = requests.get(self.url, timeout=10.0)
            response.raise_for_status()
        except:  # noqa
            log.exception('Metar query failure.')
            raise

        try:
            data = response.json()['weather']
        except:  # noqa
            log.exception('Metar response is invalid.')
            raise

        """Sample response:
        [{'a': '01h 02m ago',
         'd': '2018-08-22 18:56:00',
         'i': '0VFR.png',
         'lat': '40.4518278',
         'lon': '-105.0113361',
         'm': 'KFNL 221856Z AUTO VRB03KT 6SM HZ CLR 23/14 A3025 RMK AO2 SLP194 T02280139 PNO $',
         'n': 'FT COLLINS/LOVEL',
         's': 'KFNL',
         't': None}, ... ]
        """

        # Make the return match the format of the other sources.
        metars = {}
        for item in data:
            metars[item['s']] = {'raw_text': item['m']}

        return metars
