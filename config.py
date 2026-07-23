import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env")

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing in .env")
DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_id_store")

# Owner ID (super admin)
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID must be set in .env")

# Payment UPI
MERCHANT_UPI = os.getenv("MERCHANT_UPI", "")

# Telethon credentials (for OTP forwarding)
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
if not API_ID or not API_HASH:
    raise RuntimeError("API_ID and API_HASH are required for OTP forwarding")

# Optional: Force channel (can be set via admin panel as well)
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")   # e.g., -1001234567890 or @channel

# Optional: Default price for services (can be overridden per service)
DEFAULT_PRICE = float(os.getenv("DEFAULT_PRICE", "100"))
