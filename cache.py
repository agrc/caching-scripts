import datetime
import arcpy
import os
import time
from agrc import messaging
from agrc import logging
from agrc import update
from agrc import arcpy_helpers
from settings import *


extentsFGDB = r'C:\Cache\MapData\Extents.gdb'
cache_dir = r'C:\arcgisserver\directories\arcgiscache'
test_extent = 'test_extent'
complete_num_bundles = 2087
# complete_num_bundles = 13402 # hybrid
arcpy.env.workspace = extentsFGDB

service_name = raw_input('Cache name with folder ( e.g. "BaseMaps/Terrain"): ')
email_subject = 'Cache Update ({})'.format(service_name)
update_mode = raw_input('Overwrite existing tiles? (Y/N) ')
if update_mode == 'Y':
    update_mode = 'RECREATE_ALL_TILES'
else:
    update_mode = 'RECREATE_EMPTY_TILES'
# num_instances = int(raw_input('number of instances: '))
num_instances = 3
preview_url = 'http://{}/arcgis/rest/services/{}/MapServer?f=jsapi'.format(GIS_SERVER_IP, service_name)

pauseAtNight = True

service = r'GIS Servers\arcgis on localhost_6080 (admin)\{}.MapServer'.format(service_name)
all_scales = [
    1.8489297737236E7,
    9244648.868618,
    4622324.434309,
    2311162.217155,
    1155581.108577,
    577790.554289,
    288895.277144,
    144447.638572,
    72223.819286,
    36111.909643,
    18055.954822,
    9027.977411,
    4513.988705,
    2256.994353,
    1128.497176,

    # hybrid only
    564.248588,
    282.124294
]

extent_0_2 = 'CacheExtent_0_2'
extent_3_4 = 'CacheExtent_3_4'
extent_5_10 = 'CacheExtent_5_9'
cache_extents = [
    [extent_0_2, all_scales[0:3]],
    [extent_3_4, all_scales[3:5]],
    [extent_5_10, all_scales[5:10]]
]

grids10 = 'CacheGrids_10'
grids11 = 'CacheGrids_11'
grids12 = 'CacheGrids_12'
grids13 = 'CacheGrids_13'
grids14 = 'CacheGrids_14'
grids15 = 'CacheGrids_15'
grids16 = 'CacheGrids_16'
grids = [
    [grids10, all_scales[10]],
    [grids11, all_scales[11]],
    [grids12, all_scales[12]],
    [grids13, all_scales[13]],
    [grids14, all_scales[14]]

    # hybrid only
    # [grids15, all_scales[15]],
    # [grids16, all_scales[16]]
]

errors = []
emailer = messaging.Emailer('stdavis@utah.gov', testing=False)
logger = logging.Logger()
start_time = time.time()

if pauseAtNight:
    logger.logMsg('will pause at night')


def cache_extent(scales, aoi, name):
    today = datetime.datetime.today()
    if pauseAtNight and (today.hour > 22 or today.hour < 6):
        # don't cache at night, it slows down the update scripts
        if today.hour > 22:
            sleep_hours = 24 - today.hour + 6
        else:
            sleep_hours = 6 - today.hour
        logger.logMsg('sleeping for {} hours'.format(sleep_hours))
        time.sleep(sleep_hours*60*60)
    logger.logMsg('caching {} at {}'.format(name, scales))

    try:
        arcpy.ManageMapServerCacheTiles_server(service, scales, update_mode, num_instances, aoi)
    except arcpy.ExecuteError:
        errors.append([scales, aoi, name])
        logger.logMsg('arcpy.ExecuteError')
        logger.logError()
        logger.logGPMsg()
        emailer.sendEmail('Cache Update ({}) - arcpy.ExecuteError'.format(service_name), logger.log)


def get_progress():
    global start_time
    total_bundles = get_bundles_count()

    bundles_per_hour = (total_bundles - start_bundles)/((time.time() - start_time)/60/60)
    if bundles_per_hour != 0 and total_bundles > start_bundles:
        hours_remaining = (complete_num_bundles - total_bundles) / bundles_per_hour
    else:
        start_time = time.time()
        hours_remaining = '??'
    percent = int(round(float(total_bundles)/complete_num_bundles * 100.00))
    msg = '{} of {} ({}%) bundle files created.\nEstimated hours remaining: {}'.format(
        total_bundles, complete_num_bundles, percent, hours_remaining)
    logger.logMsg(msg)
    return msg


def get_bundles_count():
    totalfiles = 0
    basefolder = os.path.join(cache_dir, service_name.replace('/', '_'), 'Layers', '_alllayers')
    for d in os.listdir(basefolder):
        if d != 'missing.jpg':
            totalfiles += len(os.listdir(os.path.join(basefolder, d)))
    return totalfiles


def cache_test_extent():
    logger.logMsg('caching test extent')
    try:
        arcpy.ManageMapServerCacheTiles_server(service, all_scales, 'RECREATE_ALL_TILES', num_instances, test_extent)
        emailer.sendEmail('Cache Test Extent Complete ({})'.format(service_name), preview_url)
        if raw_input('Recache test extent (T) or continue with full cache (F): ') == 'T':
            cache_test_extent()
    except arcpy.ExecuteError:
        logger.logMsg('arcpy.ExecuteError')
        logger.logError()
        logger.logGPMsg()
        emailer.sendEmail('Cache Test Extent Error ({}) - arcpy.ExecuteError'.format(service_name), logger.log)
        raise arcpy.ExecuteError


def update_data():
    logger.logMsg('Updating data')
    sgid_sde = r'{}SGID10.sde'.format(HNAS_DATA_FOLDER)
    hnas_data = HNAS_DATA_FOLDER
    sgid_fgdb = 'SGID10.gdb'
    cache_fgdb = 'UtahBaseMap-Data.gdb'
    local_data = r'C:\Cache\MapData\Temp'
    local_sgid = os.path.join(local_data, sgid_fgdb)
    local_cache = os.path.join(local_data, cache_fgdb)

    errors, changes = update.updateFGDBfromSDE(os.path.join(hnas_data, sgid_fgdb), sgid_sde)
    if len(errors) > 0:
        emailer.sendEmail(email_subject + ' Errors',
                          'Data update schema changes: \n\n{}'.format('\n'.join(errors)))
        if raw_input('Re-update data? (Y/N): ') == 'Y':
            update_data()
            return

    logger.logMsg('Copying updated data locally')
    arcpy_helpers.DeleteIfExists([local_sgid, local_cache])
    arcpy.Copy_management(os.path.join(hnas_data, sgid_fgdb), local_sgid)
    arcpy.Copy_management(os.path.join(hnas_data, cache_fgdb), local_cache)

    logger.logMsg('Data update complete')

    emailer.sendEmail(email_subject, 'Data update complete. Proceeding with caching...')


updatedata = raw_input('Update data? (Y/N): ')
testcache = raw_input('Run a test cache? (Y/N): ')
if updatedata == 'Y':
    update_data()
if testcache == 'Y':
    cache_test_extent()

start_bundles = get_bundles_count()

def cache():
    for extent in cache_extents:
        cache_extent(extent[1], extent[0], extent[0])
        emailer.sendEmail(email_subject,
                          '{} completed\n{}\n{}'.format(extent[0], get_progress(), preview_url))

    for grid in grids:
        total_grids = int(arcpy.GetCount_management(grid[0]).getOutput(0))
        grid_count = 0
        step = 10
        currentStep = step
        with arcpy.da.SearchCursor(grid[0], ['SHAPE@', 'OID@']) as cur:
            for row in cur:
                grid_count += 1
                grid_percent = int(round((float(grid_count)/total_grids)*100))
                cache_extent(grid[1], row[0], '{}: OBJECTID: {}'.format(grid[0], row[1]))
                grit_percent_msg = 'Grids for this level completed: {}%'.format(grid_percent)
                logger.logMsg(grit_percent_msg)
                progress = get_progress()
                logger.logMsg(progress)
                if grid_percent >= currentStep:
                    emailer.sendEmail(email_subject,
                                      'Current Level: {}\n{}\n{}\n{}\nNumber of Errors: {}'.format(grid[0], progress, grit_percent_msg, preview_url, len(errors)))
                    currentStep = currentStep + step

    while (len(errors) > 0):
        msg = 'Recaching errors. Errors left: {}'.format(len(errors))
        logger.logMsg(msg)
        emailer.sendEmail(email_subject, msg)
        cache_extent(*errors.pop())

    bundles = get_bundles_count()
    if bundles < complete_num_bundles:
        msg = 'Only {} out of {} bundles completed. Recaching...'.format(bundles, complete_num_bundles)
        logger.logMsg(msg)
        emailer.sendEmail(email_subject, msg)
        cache()

cache()

emailer.sendEmail(email_subject + ' Finished', 'Caching complete!\n\n{}\n\n{}'.format(preview_url, logger.log))

logger.writeLogToFile()
