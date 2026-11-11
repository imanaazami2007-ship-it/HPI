import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "9158813748"))
CARD_NUMBER = os.getenv("CARD_NUMBER", "Not configured")
CARD_OWNER = os.getenv("CARD_OWNER", "Not configured")
DATABASE_PATH = os.getenv("DATABASE_PATH", "zeus_self.db")

# Set your prices in the admin-facing price table in app/db.py.
