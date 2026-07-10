import os
import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

# Load environment variables from the .env file
load_dotenv()

# Fetch variables from the environment
USERNAME = os.getenv("MONGO_USERNAME")
PASSWORD = os.getenv("MONGO_PASSWORD")
HOST = os.getenv("MONGO_HOST")
DATABASE = os.getenv("MONGO_DATABASE", "zeo_bot") # "zeo_bot" acts as a fallback

# Safeguard: Ensure required variables aren't None before trying to connect
if not all([USERNAME, PASSWORD, HOST]):
    raise ValueError(
        "Missing required MongoDB environment variables. "
        "Please check your .env file and ensure MONGO_USERNAME, MONGO_PASSWORD, and MONGO_HOST are set."
    )

# Build URI
URI = f"mongodb+srv://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}?authSource=admin"

# Global client instance (recommended so you don’t reconnect every query)
_client = None

def get_connection():
    """
    Returns an AsyncIOMotorDatabase instance for use in cogs.
    
    Example usage:
        db = get_connection()
        if db is not None:
            users_col = db["users"]
            doc = await users_col.find_one({"discordId": 123})
    """
    global _client
    try:
        if _client is None:
            _client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
        return _client[DATABASE]
    except PyMongoError as e:
        print(f"[DB ERROR] Failed to connect to MongoDB: {e}")
        return None

# -------------------------------
# ✅ Optional: Manual connection test
# -------------------------------
if __name__ == "__main__":
    async def test_connection():
        db = get_connection()
        if db is not None:
            try:
                # Motor collections methods are awaitable
                collections = await db.list_collection_names()
                print(f"✅ Connected successfully. Collections in '{DATABASE}':", collections)
            except Exception as e:
                print(f"❌ Error listing collections: {e}")
        else:
            print("❌ Database connection failed. Please check your credentials and network.")

    asyncio.run(test_connection())
