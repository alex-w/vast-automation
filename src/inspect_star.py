from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
import matplotlib.pyplot as plt
from photutils import aperture_photometry, CircularAperture
from astropy.coordinates import match_coordinates_sky
from pathlib import Path
import utils
import os
from reading import ImageRecord
import do_calibration
import utils_sd
import subprocess
import logging
import time
import reading
import argparse
from datetime import datetime
import random

from star_description import StarDescription
from ucac4 import UCAC4

padding = 0
dpi = 100


# import scipy.misc
# from skimage.draw import line_aa


def inspect(vastdir, resultdir, fitsdir, apikey, stars):
    ref_jd, _, _, reference_frame = reading.extract_reference_frame(vastdir)
    _, shapex, shapey = reading.get_fits_data(Path(fitsdir, Path(reference_frame).name))
    stars = list(map(lambda x: int(x), stars))
    for starid in stars:
        process(vastdir, resultdir, fitsdir, apikey, shapex, shapey, starid, ref_jd, reference_frame)


def process(vastdir, resultdir, fitsdir, apikey, shapex, shapey, starid, ref_jd, reference_frame):
    logging.info(f"Processing star {starid}")
    # getting the image records and rotation dict for star X
    image_records, rotation_dict = reading.get_star_jd_xy_rot(starid, vastdir)
    logging.debug(f"rotation dict has {len(rotation_dict)} entries")
    logging.debug(f"imagerecords has {len(image_records)} entries")
    df = pd.DataFrame(image_records)

    # check if reference frame is good enough
    jddict = reading.jd_to_fitsfile_dict(vastdir)
    refdf = df[df.jd == float(ref_jd)]
    if len(refdf) == 1 and (abs(shapex / 2 - refdf.iloc[0].x) < shapex / 2 * 0.95) and (
        abs(shapey / 2 - refdf.iloc[0].y) < shapey / 2 * 0.95):
        logging.info("Choosing original refframe because star is on it.")
        refrow = refdf.iloc[0]
        chosen_record = ImageRecord(refrow.jd, refrow.x, refrow.y, refrow.file, 0.0)
        wcs_file, _ = reading.read_wcs_file(vastdir)
        platesolved_file =  wcs_file
        chosen_fits = jddict[float(ref_jd)]
    else:
        logging.info("Choosing other fits frame because star is on it.")
        df = df[(df.x > 0) & (df.x < shapex) & (df.y > 0) & (df.y < shapey)]
        df['borderdistance'] = abs(shapex / 2 - df.x) + abs(shapey / 2 - df.y)
        logging.debug(df['borderdistance'].idxmin())
        logging.debug(df.iloc[df['borderdistance'].idxmin()])
        chosen_row = df.iloc[df['borderdistance'].idxmin()]
        chosen_jd = chosen_row.jd
        chosen_record = ImageRecord(chosen_jd, chosen_row.x, chosen_row.y, chosen_row.file, chosen_row.rotation)
        chosen_fits = jddict[chosen_jd]
        platesolved_file = Path(vastdir) / f'platesolve_{starid}.fits'
    chosen_fits_fullpath = Path(fitsdir, chosen_fits)
    chosen_rotation = rotation_dict[chosen_fits]
    logging.info(f"platesolved file: {platesolved_file}, chosen fits: {chosen_fits}, {chosen_fits_fullpath}, "
                 f"rotation: {chosen_rotation}")
    if not os.path.isfile(platesolved_file):
        plate_solve(apikey, chosen_fits_fullpath, platesolved_file)
    else:
        logging.info("Found platesolved file.")
    # construct star descriptions
    sds = utils_sd.construct_star_descriptions(vastdir, None)
    star_catalog = do_calibration.create_star_descriptions_catalog(sds)

    # Get the 10 closest neighbours
    sd_dict = utils.get_localid_to_sd_dict(sds)
    chosen_star_sd = sd_dict[starid]
    neighbours = []
    for neigh in range(2, 12):
        idx, d2d, _ = match_coordinates_sky(chosen_star_sd.coords, star_catalog, nthneighbor=neigh)
        neighbours.append(sds[idx])
    add_ucac4(neighbours)
    add_ucac4([chosen_star_sd])
    update_img(chosen_star_sd, chosen_record, neighbours, resultdir, platesolved_file)


def add_ucac4(stars: List[StarDescription]):
    ucac4 = UCAC4()
    ucac4.add_ucac4_to_sd(stars)


# platesolve the best frame for this star
def plate_solve(apikey, chosen_fits_fullpath, output_file):
    subprocess.Popen(f"python3 ./src/astrometry_api.py --apikey={apikey} "
                     f"--upload={chosen_fits_fullpath} --newfits={output_file} --private --no_commercial", shell=True)
    while not os.path.isfile(output_file):
        logging.info(f"Waiting for the astrometry.net plate solve...")
        time.sleep(10)


def update_img(star: StarDescription, record: ImageRecord, neighbours: List[StarDescription], resultdir: str,
               output_file: str):
    fig = plt.figure(figsize=(36, 32), dpi=160, facecolor='w', edgecolor='k')
    wcs = do_calibration.get_wcs(output_file)
    data, shapex, shapey = reading.get_fits_data(output_file)
    backgr = data.mean()
    data = data.reshape(shapex, shapey)
    data = np.pad(data, (padding, padding), 'constant', constant_values=(backgr, backgr))
    # add main target
    add_circle(record.x, record.y, 4, 'b')
    log_star(star, -1)

    random_offset = False
    offset1 = 70
    offset2 = 10

    # add neighbours
    for idx, nstar in enumerate(neighbours):
        add_pixels(nstar, wcs, 0)
        add_circle(nstar.xpos, nstar.ypos, 5, 'g')
        if random_offset:
            xrandoffset = random.randint(50, 100)
            yrandoffset = random.randint(20, 40)
            xsignrand = random.choice([-1.0, 1.0])
            ysignrand = random.choice([-1.0, 1.0])
            offset1 = xsignrand * xrandoffset
            offset2 = ysignrand * yrandoffset
        plt.annotate(f'{idx}', xy=(round(nstar.xpos), round(nstar.ypos)), xycoords='data',
                     xytext=(offset1, offset2), textcoords='offset points', size=12, arrowprops=dict(arrowstyle="-"))
        log_star(nstar, idx)

    median = np.median(data)
    print(data.max())
    #     data = ndimage.interpolation.rotate(data, record.rotation)
    plt.imshow(data, cmap='gray_r', origin='lower', vmin=0, vmax=min(median * 5, 65536))
    save_inspect_image = Path(resultdir, f'inspect_star_{star.local_id}.png')
    fig.savefig(save_inspect_image)
    logging.info(f"Saved file as {save_inspect_image}.")
    plt.close(fig)
    plt.clf()


def log_star(star, idx):
    star_ucac4 = star.get_metadata("UCAC4")
    logging.info(f'IDX: {idx}, Star: {star.local_id} with ucac4: {star_ucac4.name}, vmag: '
                 f'{star_ucac4.vmag}, coords: {star_ucac4.coords}')


def add_circle(xpos, ypos, radius: float, color: str):
    target_app = CircularAperture((xpos, ypos), r=radius)
    target_app.plot(color=color)


def add_pixels(star, wcs, offset):
    star_coord = star.coords
    xy = SkyCoord.to_pixel(star_coord, wcs=wcs, origin=0)
    x, y = round(xy[0].item(0)), round(xy[1].item(0))
    star.xpos = x + offset
    star.ypos = y + offset


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.basicConfig(format="%(asctime)s %(name)s: %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description='munipack automation cli')
    parser.add_argument('-d', '--datadir',
                        help="The directory where the data can be found (usually the vast dir)",
                        nargs='?', required=True)
    parser.add_argument('-r', '--resultdir',
                        help="The directory where all results will be written",
                        nargs='?', required=True)
    parser.add_argument('--fitsdir', help="The dir where the fits are, only needed to plate-solve the reference frame",
                        required=True)
    parser.add_argument('--apikey', '-k', dest='apikey',
                        help='API key for Astrometry.net web service; if not given will check AN_API_KEY environment variable')
    parser.add_argument('-s', '--stars', help="List the star id's to plot", nargs='+')
    parser.add_argument('-x', '--verbose', help="Set logging to debug mode", action="store_true")
    args = parser.parse_args()
    datadir = utils.add_trailing_slash(args.datadir)
    datenow = datetime.now()
    resultdir = Path(args.resultdir)
    filehandler = f"{datadir}vastlog-{datenow:%Y%M%d-%H_%M_%S}.log"
    fh = logging.FileHandler(filehandler)
    fh.setLevel(logging.INFO)
    # add the handlers to the logger
    logger.addHandler(fh)
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        fh.setLevel(logging.DEBUG)

    assert os.path.exists(args.datadir), "datadir does not exist"
    # assert os.path.exists(args.resultdir), "resultdir does not exist" ==> this dir is created
    assert os.path.exists(args.resultdir), "resultdir does not exist"
    assert os.path.exists(args.fitsdir), "fitsdir does not exist"
    inspect(datadir, args.resultdir, args.fitsdir, args.apikey, args.stars)
