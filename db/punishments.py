from .database import get_connection
from datetime import datetime, timedelta
from bson.objectid import ObjectId

# -----------------------------
# Log a punishment for a user
# -----------------------------
async def log_punishment(user_id, issuer_id, action, reason, duration=None, extra_info=None):
    """
    Insert a punishment document into the MongoDB 'punishments' collection.
    """
    db = get_connection()
    if db is None:
        print("❌ Failed to connect to database.")
        return None

    now = datetime.utcnow()
    expires_at = now + timedelta(days=1)

    if action == "mute" and duration:
        expires_at = now + timedelta(seconds=duration)

    punishment_doc = {
        "user_discord_id": user_id,
        "issuer_discord_id": issuer_id,
        "action": action,
        "reason": reason,
        "duration_seconds": duration,
        "timestamp": now,
        "expires_at": expires_at,
        "extra_info": extra_info
    }

    try:
        result = await db.punishments.insert_one(punishment_doc)
        return str(result.inserted_id)
    except Exception as e:
        print(f"❌ DB Log Error: {e}")
        return None

# -----------------------------
# Get the current active punishment
# -----------------------------
async def get_active_punishment(user_discord_id, action=None):
    """
    Retrieve the most recent active punishment for a user.
    """
    db = get_connection()
    if db is None:
        return None

    query = {
        "user_discord_id": user_discord_id,
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": datetime.utcnow()}}
        ]
    }
    if action:
        query["action"] = action

    return await db.punishments.find_one(query, sort=[("timestamp", -1)])

# -----------------------------
# Check if a user is currently punished
# -----------------------------
async def is_currently_punished(user_discord_id, action):
    """
    Check if a user has an active punishment of a specific type.
    """
    active = await get_active_punishment(user_discord_id, action)
    return active is not None

# -----------------------------
# Get all punishments for a user
# -----------------------------
async def get_all_punishments(user_id):
    """
    Retrieve all active punishments for a user.
    """
    db = get_connection()
    if db is None:
        return []

    query = {
        "user_discord_id": user_id,
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": datetime.utcnow()}}
        ]
    }

    try:
        cursor = db.punishments.find(query).sort("timestamp", -1)
        return [doc async for doc in cursor]
    except Exception as e:
        print(f"❌ Fetch Error: {e}")
        return []

# -----------------------------
# Remove expired punishments
# -----------------------------
async def remove_expired_punishments():
    """
    Delete all punishments that have expired.
    """
    db = get_connection()
    if db is None:
        return

    try:
        result = await db.punishments.delete_many({
            "expires_at": {"$lte": datetime.utcnow()}
        })
        print(f"🧹 Removed {result.deleted_count} expired punishments.")
    except Exception as e:
        print(f"❌ Remove Error: {e}")
