from .database import get_connection
from datetime import datetime

# -----------------------------
# Ensure a user document exists
# -----------------------------
def ensure_user(discord_id):
    """
    Ensure a user document exists in the 'users' collection.
    If not, create it with default values.
    """
    db = get_connection()
    if db is None:
        return

    user = db.users.find_one({"discord_id": discord_id})
    if not user:
        db.users.insert_one({
            "discord_id": discord_id,
            "msg_count": 0,
            "xp": 0,
            "level": 1,
            "xp_needed": 100,
            "last_work": None,
            "verified_by": None,
            "nsfw_verified_by": None
        })

# -----------------------------
# Increment message count
# -----------------------------
def update_msg_count(discord_id):
    """
    Increment the message count for a user by 1.
    """
    ensure_user(discord_id)
    db = get_connection()
    if db is None:
        return

    db.users.update_one(
        {"discord_id": discord_id},
        {"$inc": {"msg_count": 1}}
    )

# -----------------------------
# Get full user data
# -----------------------------
def get_user(discord_id):
    """
    Retrieve the user document from MongoDB.

    Returns:
        dict or None
    """
    db = get_connection()
    if db is None:
        return None

    return db.users.find_one({"discord_id": discord_id})

# -----------------------------
# Update XP and level
# -----------------------------
def update_xp(discord_id, xp_gain):
    """
    Add XP to a user and handle leveling up.
    """
    ensure_user(discord_id)
    db = get_connection()
    if db is None:
        return

    user = db.users.find_one({"discord_id": discord_id})
    if not user:
        return

    new_xp = user.get("xp", 0) + xp_gain
    new_level = user.get("level", 1)
    xp_needed = user.get("xp_needed", 100)

    # Level up loop
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        new_level += 1
        xp_needed = int(xp_needed * 1.25)  # simple leveling curve

    db.users.update_one(
        {"discord_id": discord_id},
        {"$set": {"xp": new_xp, "level": new_level, "xp_needed": xp_needed}}
    )

# -----------------------------
# Set last work time (job cooldown)
# -----------------------------
def update_last_work(discord_id):
    """
    Update the last_work timestamp for a user.
    """
    ensure_user(discord_id)
    db = get_connection()
    if db is None:
        return

    db.users.update_one(
        {"discord_id": discord_id},
        {"$set": {"last_work": datetime.utcnow()}}
    )

# -----------------------------
# Set verification info
# -----------------------------
def set_verified_by(discord_id, staff_id):
    """
    Set the staff member who verified the user.
    """
    ensure_user(discord_id)
    db = get_connection()
    if db is None:
        return

    db.users.update_one(
        {"discord_id": discord_id},
        {"$set": {"verified_by": staff_id}}
    )

def set_nsfw_verified_by(discord_id, staff_id):
    """
    Set the staff member who verified the user for NSFW access.
    """
    ensure_user(discord_id)
    db = get_connection()
    if db is None:
        return

    db.users.update_one(
        {"discord_id": discord_id},
        {"$set": {"nsfw_verified_by": staff_id}}
    )
