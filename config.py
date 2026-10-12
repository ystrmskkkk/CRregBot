import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError(
        "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
    )

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()

ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
]

DB_PATH = os.getenv("DB_PATH", "tournament.db")

MAX_PARTICIPANTS = int(os.getenv("MAX_PARTICIPANTS", "0"))

READINESS_TIMEOUT_MINUTES = int(os.getenv("READINESS_TIMEOUT_MINUTES", "10"))
