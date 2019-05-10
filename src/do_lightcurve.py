# JD V-C s1 V s2 C s3
# Aperture: 2, Filter: V
# 2457657.5088310 -0.50728 0.10291 16.65794 0.05604 17.16522 0.08631

from init_loader import init, settings
from reading import trash_and_recreate_dir
from reading import reduce_star_list
from tqdm import tqdm
from functools import partial
import multiprocessing as mp
from multiprocessing.pool import ThreadPool
from read_pht import read_pht_file
import glob
import numpy as np
import math
import logging
from typing import List

preamble = None
star_result = None
Vector = List[float]
MAX_MAG = 99.99999
MAX_ERR = 9.99999
STAR_DATA_MB = 1.5274047851562502e-05  # the size of the data of one star


# multithreaded writing of lightcurves
def write_lightcurves(star_list_1, comparison_stars_1, aperture, apertureidx, jd, fwhm, star_result_):
    trash_and_recreate_dir(settings.lightcurvedir)

    global preamble
    preamble = init_preamble(aperture, comparison_stars_1)
    global star_result
    star_result = star_result_
    pool = mp.Pool(init.nr_threads * 2, maxtasksperchild=None)
    # pool = mp.Pool(1)
    func = partial(write_lightcurve, comparison_stars_1=comparison_stars_1, aperture=aperture, apertureidx=apertureidx,
                   jd=jd, fwhm=fwhm)
    logging.debug(f"Writing star lightcurve txt files for {len(star_list_1)} stars into {settings.lightcurvedir}")
    for _ in tqdm(pool.imap_unordered(func, star_list_1), total=len(star_list_1), desc='Writing lightcurve'):
        pass


def write_lightcurve(star_1: int, comparison_stars_1: Vector, aperture: float, apertureidx: int, jd: float,
                     fwhm: float):
    # print(f"Write lightcurve for star:", star_1)
    comparison_stars_1 = exclude_star_from_comps(comparison_stars_1, star_1)
    comparison_stars_0 = np.array(comparison_stars_1) - 1
    star_0 = star_1 - 1

    lines = [preamble]
    # print("nr of files:", nrfiles)
    # for every file
    sorted_jd = np.argsort(jd)  # argsort the julian date so lines are inserted in the correct order
    for fileidx in sorted_jd:
        line = f"{jd[fileidx]:.7f}"  # start the line with the julian date
        V = star_result[fileidx][star_0][0]
        Verr = min(MAX_ERR, star_result[fileidx][star_0][1])
        if not is_valid(V, Verr): continue
        C, Cerr, mask = calculate_synthetic_c(fileidx, star_result[fileidx], comparison_stars_0)
        if C == 0 and Cerr == 0: continue  # abort if one of the comparison stars is not available
        Cerr = min(MAX_ERR, Cerr)


        linedata = [(V - C, math.sqrt(Verr ** 2 + Cerr ** 2)), (V, Verr), (C, Cerr)] \
                   + [(star_result[fileidx][checkstar_0][0], star_result[fileidx][checkstar_0][1]) for checkstar_0 in comparison_stars_0]

        # print(linedata)
        for tuple in linedata:
            line += f" {min(MAX_MAG, tuple[0]):.5f} {min(MAX_ERR, tuple[1]):.5f}"
        line += " " + mask
        lines.append(line)

    with open(settings.lightcurvedir + 'curve_' + str(star_1).zfill(5) + ".txt", 'wt') as f:
        # for l in lines: f.write('%s\n' % l)
        logging.debug(f"Writing lightcurve {settings.lightcurvedir + 'curve_' + str(star_1).zfill(5)}.txt")
        f.write('\n'.join(lines) + '\n')


# the static first part of the file
def init_preamble(aperture, check_stars_list):
    preamble = "JD V-C s1 V s2 C s3"
    checkstarcount = 1
    count = 4
    for _ in check_stars_list:
        preamble = preamble + f" C{checkstarcount} s{count}"
        checkstarcount = checkstarcount + 1
        count = count + 1
    preamble = preamble + f" mask\nAperture: {aperture}, Filter: V, Check stars: {check_stars_list}"
    return preamble




# mean value option for ensemble photometry, 'Ensemble Photometry Crawford'
def calculate_synthetic_c(fileidx, star_result_file, check_stars_0):
    result = []
    mask = ""
    for idx, entry in enumerate(check_stars_0):
        if entry == -1:
            logging.debug(f"Star is part of compstars")
            mask = mask + "0"
            continue
        cmag = star_result_file[entry][0]
        cerr = star_result_file[entry][1]
        if is_valid(cmag, cerr):
            logging.debug(f"synth: valid fileidx:{fileidx}, idx:{idx}, entry:{entry}")
            result.append((cmag, cerr))
            mask = mask + "1"
        else:
            logging.debug(f"synth: not valid fileidx:{fileidx}, idx:{idx}, entry:{entry}")
            mask = mask + "0"
    if len(result) == 0:
        logging.debug(f"synth: len is 0 fileidx:{fileidx}, idx:{idx}, entry:{entry}")
        return 0, 0, "00"

    cummag = 0
    cumerr = 0
    for entry in result:
        cummag += entry[0]
        cumerr += entry[1]
    logging.debug(f"mask: {mask}, {star_result[fileidx][:][0]} - fileidx:{fileidx}")
    return cummag / len(result), cumerr / len(result), mask

# /* Comparison star */
# if (lc->comp.count==1) {
# 	if (comp[0].valid) {
# 		cmag = comp[0].mag;
# 		cerr = comp[0].err;
# 		comp_ok = 1;
# 	} else {
# 		cerr = cmag = 0.0;
# 		comp_ok = 0;
# 	}
# } else {
# 	cmag = cerr = 0.0;
# 	n = 0;
# 	for (i=0; i<lc->comp.count; i++) {
# 		if (comp[i].valid) {
# 			cmag += pow(10.0, -0.4*comp[i].mag);
# 			cerr += comp[i].err;
# 			n++;
# 		}
# 	}
# 	if (n==lc->comp.count) {
# 		cmag = -2.5*log10(cmag/n);
# 		cerr = (cerr/n)/sqrt((double)n);
# 		comp_ok = 1;
# 	} else {
# 		cerr = cmag = 0.0;
# 		comp_ok = 0;
# 	}
# }
def calculate_synthetic_c_munipack(fileidx, star_result_file, check_stars_0):
    if len(check_stars_0) == 1:
        cmag = star_result_file[check_stars_0[0]][0]
        cerr = star_result_file[check_stars_0[0]][1]
        if is_valid(cmag, cerr):
            return cmag, cerr
        else:
            return 0, 0

    cmag, cerr, valid = 0, 0, 0
    nrstars = len(check_stars_0)
    for entry in check_stars_0:
        mag = star_result_file[entry][0]
        err = star_result_file[entry][1]
        if is_valid(mag, err):
            cmag += np.power(10, -0.4 * mag)
            cerr += err
            valid += 1
    if valid > 0:
        cmag = -2.5 * math.log10(cmag / valid)
        cerr = (cerr / valid) / math.sqrt(valid)
    else:
        cmag, cerr = 0, 0
        logging.info(f"losing line in {fileidx}")
    return cmag, cerr


def is_valid(mag, err):
    return not np.isnan(mag) and not np.isnan(err) and mag < MAX_MAG and err < MAX_ERR


def join_check_stars_string(check_stars, exclude_star):
    check_stars = filter(lambda star: star != exclude_star, check_stars)
    check_stars_string = ','.join(map(str, check_stars))
    return check_stars_string


def exclude_star_from_comps(check_stars, exclude_star):
    exclude_index = check_stars.index(exclude_star) if exclude_star in check_stars else None
    if exclude_index is not None:
        check_stars = check_stars.copy()
        check_stars[exclude_index] = -1
    return check_stars


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]
