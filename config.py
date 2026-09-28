import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))
    LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))
    SERVER_OWNER_ID: int = int(os.getenv("SERVER_OWNER_ID", "0"))
    BOT_ICON_URL: str = os.getenv("BOT_ICON_URL", "")
    RULES_URL: str = os.getenv("RULES_URL", "https://discord.com")
    DB_PATH: str = os.getenv("DB_PATH", "slots.db")
    DEFAULT_MAX_DAILY_PINGS: int = int(os.getenv("DEFAULT_MAX_DAILY_PINGS", "2"))
    SLOT_CATEGORY_PREFIX: str = os.getenv("SLOT_CATEGORY_PREFIX", "SLOTS")

config = Config()
