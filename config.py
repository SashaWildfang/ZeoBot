import os
from dotenv import load_dotenv

# Load .env values into environment
load_dotenv()

# Discord bot settings
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

# Optional: Add more as needed
DB_URL = os.getenv("DATABASE_URL", "sqlite:///data/bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
