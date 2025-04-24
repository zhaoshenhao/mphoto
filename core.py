from gdrive import GoogleDrive
from client_api import ClientAPI
from utils import setup_logging
from config import config
from multiprocessing import set_start_method
from scan import Scaner

client = ClientAPI()
gdrive = GoogleDrive()
logger = setup_logging(config['logging']['cli_prefix'])

def remove_keys(list):
    for i in list:
        del i['thumb_link']
        del i['web_content_link']
    return list

def print_list(list):
    for n in list:
        logger.info(f"  new file: {n['name']} / {n['gdid']}")

def refresh(cloud_storage_id):
    logger.info(f"Start refreshing: ")
    logger.info(f"Get cloud storage detail for ID {cloud_storage_id}")
    cs = client.get_cloud_storage_detail(cloud_storage_id)
    if not cs:
        logger.error(f"No cloud storage found for ID: {cloud_storage_id}")
        exit(1)
    logger.info(f"Event ID: {cs['event_id']}")
    logger.info(f"Cloud Storage URL: {cs['url']}")
    logger.info(f"Cloud Storage recursive: {cs['recursive']}")
    logger.info("Get photos from database:")
    dblist = client.list_photos(cloud_storage_id)
    logger.info(f"Total photos from database: {len(dblist)}")
    logger.info("Get photos from google drive:")
    gdlist = gdrive.scan_folder(cs['url'], cs['recursive'])
    logger.info(f"Total photos from google drive: {len(gdlist)}")
    logger.info("Compare photos between google drive and database:")
    only_new, changed, missing = gdrive.compare(gdlist, dblist)
    logger.info(f"New file: {len(only_new)}")
    logger.info(f"Changed file: {len(changed)}")
    logger.info(f"Missing file: {len(missing)}")
    if len(only_new) > 0:
        logger.info(f"Processing new files")
        print_list(only_new)
        j = client.add_photos(cloud_storage_id, remove_keys(only_new))
        logger.info(f"return: {j}")

    if len(changed) > 0:
        logger.info(f"Processing change files")
        print_list(changed)
        j = client.update_photos(cloud_storage_id, remove_keys(changed))
        logger.info(f"return: {j}")

    if len(missing) > 0:
        logger.info(f"Processing missing files")
        print_list(missing)
        gdids = [item['id'] for item in missing]
        j = client.delete_photos(cloud_storage_id, gdids)
        logger.info(f"return: {j}")
    
    logger.info(f"Done")

def scan(cloud_storage_id):
    try:
        set_start_method('spawn')
    except RuntimeError:
        pass
    scaner = Scaner(cloud_storage_id)
    scaner.scan()
