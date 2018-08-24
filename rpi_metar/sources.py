import csv
import logging
import requests

from pkg_resources import resource_filename
from retrying import retry
from xmltodict import parse as parsexml

log = logging.getLogger(__name__)


class METARSource:

    @retry(wait_exponential_multiplier=1000,
           wait_exponential_max=10000,
           stop_max_attempt_number=10)
    def _query(self):
        """Queries the NOAA METAR service."""
        log.info(self.url)
        try:
            response = requests.get(self.url, timeout=10.0)
            response.raise_for_status()
        except:  # noqa
            log.exception('Metar query failure.')
            raise
        return response


class NOAA(METARSource):

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

    def get_metar_info(self):
        """Queries the NOAA METAR service."""
        response = self._query()
        try:
            response = parsexml(response.text)['response']['data']['METAR']
        except:  # noqa
            log.exception('Metar response is invalid.')
            raise

        return {m['station_id']: m for m in response}


class SkyVector(METARSource):

    URL = (
        'https://skyvector.com/api/dLayer'
        '?ll1={lat1},{lon1}'  # lower left
        '&ll2={lat2},{lon2}'  # upper right
        '&layers=metar'
    )

    def _find_coordinates(self):
        data = {}
        file_name = resource_filename('rpi_metar', 'data/us-airports.csv')
        with open(file_name, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                airport_code, lat, lon = row
                if airport_code in self.airport_codes:
                    data[airport_code] = (lat, lon)

        self.data = data

        lat1 = min((float(lat) for lat, _ in data.values()))
        lon1 = min((float(lon) for _, lon in data.values()))
        lat2 = max((float(lat) for lat, _ in data.values()))
        lon2 = max((float(lon) for _, lon in data.values()))

        # skyvector either isn't inclusive, or our data doesn't match theirs. Regardless, we
        # must expand the search area slightly.
        lat1, lon1 = map(lambda x: x - 0.5, [lat1, lon1])
        lat2, lon2 = map(lambda x: x + 0.5, [lat2, lon2])

        self.url = SkyVector.URL.format(lat1=lat1, lon1=lon1, lat2=lat2, lon2=lon2)

    def __init__(self, airport_codes):
        # Set lat / long info for the request...
        self.airport_codes = [code.upper() for code in airport_codes]
        self._find_coordinates()

    def get_metar_info(self):
        response = self._query()
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
            if item['s'] in self.airport_codes:
                metars[item['s']] = {'raw_text': item['m']}

        return metars
