import os
import io
import json
import random
import textwrap
import datetime, time
import math


import httplib2
import apiclient.discovery
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.http import MediaIoBaseDownload

# Importing the PIL library
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from fastapi import FastAPI, Response

# from dotenv import load_dotenv
# load_dotenv()

# google api
def get_google_service(service_account_json:str, api:str='sheets'):
    """return connection to google api
    api='sheets'
    api='drive'
    """
    service_account_file_json = json.loads(service_account_json, strict=False)
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(service_account_file_json, ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    httpAuth = credentials.authorize(httplib2.Http())
    if api == 'sheets':
        return apiclient.discovery.build('sheets', 'v4', http = httpAuth)
    elif api == 'drive':
        return apiclient.discovery.build('drive', 'v3', credentials=credentials)
    return None
    
def str_to_int(string):
    """
    Converts a string to an integer. If the string is not numeric, it will return 0 if the string is empty or False, and 1 if the string is 'true' or 'истина' (in any case).
    
    Parameters:
    - string (str): The input string to be converted to an integer.
    
    Returns:
    - int: The integer representation of the input string.
    
    Examples:
    >>> str_to_int("123")
    123
    >>> str_to_int("true")
    1
    >>> str_to_int("истина")
    1
    >>> str_to_int("")
    0
    >>> str_to_int("False")
    0
    """
    
    if not string:
        return 0
    elif string.isnumeric():
        return int(string)
    elif string.lower() == 'true':
        return 1
    elif string.lower() == 'истина':
        return 1
    else:
        return int(string)

def str_to_datetime(string):
    """
    Converts a string to a datetime object, using the format '%Y/%m/%d %H:%M'. If the string is empty or the conversion fails, the function returns None.
    
    Parameters:
    - string (str): The input string to be converted to a datetime object.
    
    Returns:
    - datetime: The datetime representation of the input string. If the conversion fails, returns None.
    
    Examples:
    >>> str_to_datetime("2022/12/27 12:34")
    datetime.datetime(2022, 12, 27, 12, 34)
    >>> str_to_datetime("")
    None
    >>> str_to_datetime("2022/12/27 12:34:56")
    None
    """

    if not string:
        return None
    try:
        dt = datetime.datetime.strptime(string, DATETIME_FORMAT)
    except ValueError:
        return None
    
    return dt

def get_phrases(only_new=False):
    """
    only_new=True - to show if there are new phrases, else None
    only_new=Fajse - always to show phrases, even old ones

    Retrieves a list of dictionaries containing data from a Google Sheets spreadsheet. The data consists of key-value pairs, where the keys are the column names in the spreadsheet and the values are the cell contents in the corresponding row.
    
    The function uses the Google Sheets API to retrieve the data, and processes it by converting certain values to their appropriate data types and filtering out inactive phrases. Specifically, the 'datetime' and 'show_datetime' values are converted to datetime objects, and the 'is_inactive' value is converted to an integer. Phrases with an 'is_inactive' value of 1 are not included in the final list.
    
    Returns:
    - list[dict]: A list of dictionaries, where each dictionary represents a row in the spreadsheet with the keys as column names and the values as cell contents.
    """

    service = get_google_service(SERVICE_ACCOUNT_JSON, api='sheets')
    result = service.spreadsheets().values().batchGet(spreadsheetId=SPREADSHEET_ID, ranges=PHRASES_PAGE_NAME).execute()

    keys = result['valueRanges'][0]['values'][0]
    max_len = len(keys)
    values = result['valueRanges'][0]['values'][1:]
    values = [i + [None] * (max_len - len(i)) for i in values]

    phrases = []
    for v in values:
        kv = dict()
        for i in range(max_len):
            kv[keys[i]] = v[i]
        phrases.append(kv)

    p = []
    rn = RESERVED_HEADER_ROWS
    # convert and filter
    for i in phrases:
        # row number
        rn += 1
        i['row_number'] = rn
        # datetime - convert to dt
        i['datetime'] = str_to_datetime(i['datetime'])
        # is_inactive - convert to int
        i['is_inactive'] = str_to_int(i['is_inactive'])
        # show_datetime - convert to dt
        i['show_datetime'] = str_to_datetime(i['show_datetime'])
        
        # is_inactive filter 
        if i['is_inactive'] == 0:
            # only not shown pharses needed
            if only_new:
                if not i['show_datetime']:
                    p.append(i)
            else:
                p.append(i)
    return p

def clear_gs_range(range:str):
    """
    """
    service = get_google_service(SERVICE_ACCOUNT_JSON, api='sheets')
    result = service.spreadsheets().values().clear(
                spreadsheetId=SPREADSHEET_ID, range=range).execute()

def write_to_gs(data:list, range:str):
    """
    data:  [[col1, col2,col3],
            [col1, col2,col3],
            [col1, col2,col3],
            [col1, col2,col3]]
    """
    service = get_google_service(SERVICE_ACCOUNT_JSON, api='sheets')
    result = service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range=range,
                valueInputOption="USER_ENTERED", body={'values': data}).execute()

def get_phrase(phrases):
    if not phrases:
        return None, None
        
    items =  [[i['row_number'], i['show_datetime']] for i in phrases]

    row_number_to_show = get_item_to_show(items)

    phrase = [i for i in phrases if i['row_number'] == row_number_to_show][0]

    txt = phrase['phrase']
    txt_meaning = f"({phrase['meaning']})" if phrase['meaning'] else None
    txt_row_number = phrase['row_number']

    # mark in gs as shown
    data = datetime.datetime.now().strftime(DATETIME_FORMAT)
    range = PHRASES_PAGE_NAME + '!' + PHRASES_SHOW_DATETIME_COLUMN + str(txt_row_number)
    write_to_gs([[data]], range)

    return txt, txt_meaning

def get_img():    
    img_file_id = get_img_id()
    service_google_drive = get_google_service(SERVICE_ACCOUNT_JSON, api='drive')
    request = service_google_drive.files().get_media(fileId=img_file_id)

    fn = io.BytesIO()
    downloader = MediaIoBaseDownload(fn, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    return fn

def wrap_txt(txt, width):
    '''split text by words
    width - max lenght (letters)
    '''
    strings = []
    if txt:
        for s in txt.splitlines():
            strings.extend(textwrap.wrap(s, width=width))
        return strings
    return None
    
def get_mem(img_bin, txt, txt_meaning):

    if not txt:
        return None

    basewidth = 800
        
    img = Image.open(img_bin)
    
    wpercent = (basewidth/float(img.size[0]))
    hsize = int((float(img.size[1])*float(wpercent)))
    img = img.resize((basewidth,hsize), Image.Resampling.LANCZOS)

    font_size_txt = int(basewidth/18)
    font_color_txt=(0,0,0)
    unicode_font_txt = ImageFont.truetype("DejaVuSans.ttf", font_size_txt)

    font_size_txt_meaning = int(font_size_txt*.8)
    font_color_txt_meaning=(16,16,16)
    unicode_font_txt_meaning = ImageFont.truetype("DejaVuSans.ttf", font_size_txt_meaning)

    # lists of wrapped strings
    width = 28
    txt = wrap_txt(txt, width)
    txt_meaning = wrap_txt(txt_meaning, width)

    txt_heigh = len(txt)*font_size_txt + (len(txt_meaning)*font_size_txt_meaning if txt_meaning else 0)


    y_rect = int(img.height - int(txt_heigh*1.75))
    y_txt = int(img.height - int(txt_heigh*1.5))
    x = int(img.width/25)


    I1 = ImageDraw.Draw(img, 'RGBA')

    shape = [(0, y_rect), (img.width, img.height)]
    I1.rectangle(shape, fill=(255, 255, 255, 185))

    for line in txt:
        I1.text ( (x,y_txt), line, font=unicode_font_txt, fill=font_color_txt )
        y_txt += unicode_font_txt.getbbox(line)[3]

    if txt_meaning:
        for line in txt_meaning:
            I1.text ( (x,y_txt), line, font=unicode_font_txt_meaning, fill=font_color_txt_meaning )
            y_txt += unicode_font_txt.getbbox(line)[3]

    return img

def get_img_file_ids_from_gdrive():
    service_google_drive = get_google_service(SERVICE_ACCOUNT_JSON, api='drive')
    results = service_google_drive.files().list(
                                fields="nextPageToken, files(id, name, mimeType)",
                                q=f"'{JULIA_PHOTOS_FOLDER_ID}' in parents"
                                ).execute()

    img_file_ids = [v['id']  for v in results['files']]
    return img_file_ids

def get_img_file_ids_date_from_gs():
    """Get img_id and datetime last show
    """
    service = get_google_service(SERVICE_ACCOUNT_JSON, api='sheets')
    result = service.spreadsheets().values().batchGet(spreadsheetId=SPREADSHEET_ID, ranges=PHOTOS_PAGE_NAME).execute()

    keys = result['valueRanges'][0]['values'][0]
    max_len = len(keys)
    values = result['valueRanges'][0]['values'][0+RESERVED_HEADER_ROWS:]

    res = []
    for i in values:
        if len(i) < 2:
            res.append([i[0],''])
        else:
            res.append(i)

    return res

def get_item_to_show(items):
    """ items - list of list : [item, datetime]
    """
    items_sorted = sorted(items, key=lambda x: datetime.datetime(1970,1,1,0,0) if not x[1] else x[1])

    not_shown = [i for i in items_sorted if not i[1]]
    
    # return item if there are new ones
    if not_shown:   
        return not_shown[0][0]
    else:
        return random.choice(items_sorted[len(items_sorted)//2::-1])[0]
    

def get_img_id():
    img_file_ids_dates = get_img_file_ids_date_from_gs()
    img_file_ids = get_img_file_ids_from_gdrive()

    # refresh matches img - date show
    items = []
    for i in img_file_ids:
        t = ''
        for j in img_file_ids_dates:
            if i == j[0]:
                t = j[1]
        
        t = None if t == '' else datetime.datetime.strptime(t, DATETIME_FORMAT)
        items.append([i, t])

    img_file_id = get_item_to_show(items) 

    # rewrite photos log in gs
    # clear range 
    if img_file_ids_dates:
        range = PHOTOS_PAGE_NAME + '!' + PHOTOS_PAGE_FIRST_COLUMN + str(1 + RESERVED_HEADER_ROWS) + ':' + PHOTOS_PAGE_LAST_COLUMN + str(RESERVED_HEADER_ROWS + len(img_file_ids_dates))
        clear_gs_range(range)

    # write new data
    img_file_ids_new_dates = []
    for i in items:
        if i[0] == img_file_id:
            img_file_ids_new_dates.append([i[0], datetime.datetime.now().strftime(DATETIME_FORMAT)])
        else:
            img_file_ids_new_dates.append([i[0], '' if not i[1] else i[1].strftime(DATETIME_FORMAT)])
    
    range = PHOTOS_PAGE_NAME + '!' + PHOTOS_PAGE_FIRST_COLUMN + str(1 + RESERVED_HEADER_ROWS) + ':' + PHOTOS_PAGE_LAST_COLUMN + str(RESERVED_HEADER_ROWS + len(img_file_ids_new_dates))
    write_to_gs(img_file_ids_new_dates, range)

    return img_file_id


def img2bin(img:Image):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

def mem_to_api(mem_type:str) -> Image :
    """mem_type - new, random
    """
    phrases = []
    
    if mem_type == 'new':
        phrases = get_phrases(only_new=True)
    elif mem_type == 'random':
        phrases = get_phrases(only_new=False)
    
    if phrases:
        txt, txt_meaning = get_phrase(phrases)
        img_bin = get_img()
        mem = get_mem(img_bin, txt, txt_meaning)
        return mem
    return None


app = FastAPI()


DATETIME_FORMAT = '%Y/%m/%d %H:%M'
SERVICE_ACCOUNT_JSON = os.getenv('JULIA_MEM_GOOGLE_SERVICE_ACCOUNT_KEY_JSON', None)
# SERVICE_ACCOUNT_JSON = os.environ.get('JULIA_MEM_GOOGLE_SERVICE_ACCOUNT_KEY_JSON', None)

# google spread sheet with phrases
SPREADSHEET_ID = os.getenv('JULIA_MEM_SPREADSHEET_ID', None)
# SPREADSHEET_ID = os.environ.get('JULIA_MEM_SPREADSHEET_ID', None)
PHRASES_PAGE_NAME = 'phrases'
PHRASES_SHOW_DATETIME_COLUMN = 'E'
PHOTOS_PAGE_NAME = 'photos'
PHOTOS_PAGE_ID = 1064383404
PHOTOS_PAGE_FIRST_COLUMN = "A"
PHOTOS_PAGE_LAST_COLUMN = "B"
RESERVED_HEADER_ROWS = 1

# google drive folder with photos 
JULIA_PHOTOS_FOLDER_ID = os.getenv('JULIA_MEM_PHOTOS_FOLDER_ID', None)
# JULIA_PHOTOS_FOLDER_ID = os.environ.get('JULIA_MEM_PHOTOS_FOLDER_ID', None)

@app.get("/mem/{mem_type}",
    responses = {200: {"content": {"image/png": {}}}},
    response_class=Response
    )
def get_image(mem_type):
    mem = mem_to_api(mem_type=mem_type)
    if mem:
        image_bytes = img2bin(mem)
        return Response(content=image_bytes, media_type="image/png")
    return None


@app.get("/")
def root():
    return {'message':'Helloooo, Julia!'}

#localstart:

# docker run --rm -p 8888:8888 -p 8501:8501 -p 8000:8000 -v ${pwd}:/work --name python38jupyter python38jupyter
# docker exec -it python38jupyter bash
# cd julia_mem_api
# uvicorn julia_mem_api:app --host 0.0.0.0 --port 8000 --reload


# deploy on render  with github
# https://github.com/bennylope/python-deployments-hello-world