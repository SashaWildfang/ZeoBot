from motor.motor_asyncio import AsyncIOMotorClient

from pymongo.errors import PyMongoError



# MongoDB connection details

USERNAME = "sasha"

PASSWORD = "XxQ72Io456BS03W8"

HOST = "kitty-kingdom-dev-2b083521.mongo.ondigitalocean.com"

DATABASE = "zeo_bot"



# Build URI

URI = f"mongodb+srv://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}?authSource=admin"



# Global client instance (recommended so you don’t reconnect every query)

_client = None





def get_connection():

    """

    Returns an AsyncIOMotorDatabase instance for use in cogs.

    

    Example usage:

        db = get_connection()

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

    import asyncio



    async def test_connection():

        db = get_connection()

        if db:

            try:

                # Motor collections methods are awaitable

                collections = await db.list_collection_names()

                print("✅ Connected successfully. Collections:", collections)

            except Exception as e:

                print(f"❌ Error listing collections: {e}")

        else:

            print("❌ Database connection failed.")



    asyncio.run(test_connection())

