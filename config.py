# config.py

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "").split(',')))
EXPIRATION_TIME=28800

ALLOW_ROOM = 'allow_room'
HLV = 'hlv'
BUDGET ='ngan_sach'
ADS = 'ads'
BUDGET_THRESHOLD='budget_limits'

AREA_NAME=os.getenv("AREA_NAME")
MONGO_URI=os.getenv("MONGO_URI")
DB_NAME=os.getenv("DB_NAME")
WS_URL=os.getenv("WS_URL")