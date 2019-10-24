# from .context import src
import unittest
import do_compstars
from ucac4 import UCAC4
from comparison_stars import ComparisonStars
import os
from pathlib import PurePath
import logging
from pandas import DataFrame
from astropy.coordinates import SkyCoord


test_file_path = PurePath(os.getcwd(), 'tests', 'data')


class TestUcac4(unittest.TestCase):
    def setUp(self) -> None:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
        self.UCAC4_ID = 'UCAC4 001-000003'
        self.ucac4 = UCAC4()

    def test_get_ucac4_details_raw(self):
        # ucac4.get_ucac4_star_description_raw('UCAC4 001-000003')
        result = self.ucac4.get_ucac4_details_raw('001', [3])
        self.assertEqual(result[0][0].ra, 18290451)


    def test_get_ucac4_details(self):
        result = self.ucac4.get_ucac4_details(self.UCAC4_ID)
        self.assertEqual(result[0][0].ra, 18290451)


    def test_get_ucac4_star_description(self):
        result = self.ucac4.get_ucac4_star_description_fromid(self.UCAC4_ID)
        print(result)
        #     local_id: None, aavso_id: UCAC4 001-000003, coords: <SkyCoord (ICRS): (ra, dec) in deg
        # (5.08068083, -89.81054306)>, xy: None, None, vmag: 10.986, nr matches: 0, matches: [], path: None
        self.assertEqual(result.aavso_id, self.UCAC4_ID)
        self.assertEqual(round(result.coords.ra.deg, 8), 5.08068083)
        self.assertEqual(round(result.coords.dec.deg, 8), -89.81054306)
        self.assertEqual(result.vmag, 10.986)


    def test_name_to_zone_and_run_nr(self):
        zone, runnr = self.ucac4.name_to_zone_and_run_nr(self.UCAC4_ID)
        self.assertEqual(zone, '001')
        self.assertEqual(runnr, 3)


    def test_zone_and_run_nr_to_name(self):
        ucac4_id = self.ucac4.zone_and_run_nr_to_name('001', 3)
        self.assertEqual(ucac4_id, self.UCAC4_ID)


    def test_get_ucac4_id(self):
        # Compstar match: UCAC4 231-154752 with 3174 (271.2347344444444 deg, -43.84581611111111 deg)
        # Compstar match: UCAC4 232-147677 with 2620 (271.2807819444444 deg, -43.77729194444444 deg)
        ra, dec = 271.2347344444444, -43.84581611111111
        target = SkyCoord(ra, dec, unit='deg')
        result = self.ucac4.get_ucac4_sd(ra, dec)
        self.assertEqual("UCAC4 231-154752", result.aavso_id)
        self.assertEqual(12.107, result.vmag)
        print("diff is ", target.separation(result.coords))
        ra, dec = 271.2807819444444, -43.77729194444444
        result = self.ucac4.get_ucac4_sd(ra, dec)
        self.assertEqual("UCAC4 232-147677", result.aavso_id)
        self.assertEqual(12.314, result.vmag)
        print("diff is ", target.separation(result.coords))


    def test_get_zone_for_dec(self):
        self.assertEqual(1, self.ucac4.get_zone_for_dec(-90))
        self.assertEqual(1, self.ucac4.get_zone_for_dec(-89.8))
        self.assertEqual(3, self.ucac4.get_zone_for_dec(-89.5))
        self.assertEqual(900, self.ucac4.get_zone_for_dec(90))


    def test_get_ra_bucket(self):
        self.assertEqual(1440, self.ucac4.get_ra_bucket(360))
        self.assertEqual(1, self.ucac4.get_ra_bucket(0))
        self.assertEqual(720, self.ucac4.get_ra_bucket(180))


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
    unittest.main()