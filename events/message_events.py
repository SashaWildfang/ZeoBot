import discord
from discord.ext import commands
from db.database import get_connection
import random
import math
import datetime
import time

# Anti-farming cooldowns: 1 reward per 60 seconds
time_cache = {}
IGNORED_CHANNEL_IDS = {1358486649360748665}

# Add your ignored categories here
IGNORED_CATEGORY_IDS = {
    1358485995649237103, 
    1362459990245245151, 
    1362461644768411758, 
    1448247633574363237, 
    1358485130242560020, 
    1358486463251091569
}

class MessageEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_seconds = 60

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Base ignores: bots, DMs, or explicitly ignored individual channels
        if message.author.bot or not message.guild or message.channel.id in IGNORED_CHANNEL_IDS:
            return
            
        # 2. Category ignore: safely check if the channel's category is in the ignored list
        if getattr(message.channel, "category_id", None) in IGNORED_CATEGORY_IDS:
            return

        discord_id = message.author.id 
        now = time.time()

        if discord_id in time_cache and now - time_cache[discord_id] < self.cooldown_seconds:
            return
        time_cache[discord_id] = now

        db = get_connection()
        users_col = db["users"]
        globals_col = db["globals"]
        temp_boosters_col = db["temporary_boosters"]

        try:
            # 1. Fetch User Data
            user_doc = await users_col.find_one({"discordId": discord_id})

            if not user_doc:
                await users_col.insert_one({
                    "discordId": discord_id,
                    "msgCount": 0,
                    "butterflies": 0,
                    "xp": 0,
                    "level": 0,
                    "streak_days": 0,
                    "last_message": datetime.datetime.utcnow(),
                    "xpMultiplier": 1.0,
                    "butterflyMultiplier": 1.0
                })
                user_doc = {"xpMultiplier": 1.0, "butterflyMultiplier": 1.0, "level": 0}

            # 2. Fetch Base Multipliers
            base_xp_mult = float(user_doc.get("xpMultiplier", 1.0))
            # Fallback checking both naming conventions just in case
            base_bf_mult = float(user_doc.get("butterflyMultiplier", user_doc.get("butterfly_multiplier", 1.0)))

            # 3. Fetch Global XP Weekend Status
            global_doc = await globals_col.find_one({"isXpWeekend": {"$exists": True}}) 
            if not global_doc:
                global_doc = await globals_col.find_one({}) or {}
            is_weekend = global_doc.get("isXpWeekend", 0)

            # 4. Fetch Active Temp Boosters (Stored as string IDs in inventory)
            active_booster = await temp_boosters_col.find_one({"discordId": str(discord_id)})

            # --- CALCULATE FINAL MULTIPLIERS ---
            final_xp_mult = base_xp_mult
            final_bf_mult = base_bf_mult

            # Apply Weekend Buff
            if is_weekend == 1:
                final_xp_mult *= 2.0

            # Apply Inventory Booster Buff
            if active_booster:
                booster_type = active_booster.get("item_id")
                if booster_type == "booster_xp":
                    final_xp_mult *= 2.0
                elif booster_type == "booster_butterfly":
                    final_bf_mult *= 2.0

            # --- CALCULATE REWARDS & TAX ---
            base_bf_reward = random.randint(30, 50)
            base_xp_reward = random.randint(25, 50)

            total_butterflies = math.ceil(base_bf_reward * final_bf_mult)
            xp_gain = math.ceil(base_xp_reward * final_xp_mult)

            # Calculate 5% tax on the crabs
            tax = int(total_butterflies * 0.05)
            net_butterflies = total_butterflies - tax

            # --- DATABASE UPDATES ---
            update_data = {
                "$inc": {
                    "msgCount": 1,
                    "butterflies": net_butterflies,  # Give the user the net amount
                    "xp": xp_gain
                },
                "$set": {
                    "last_message": datetime.datetime.utcnow()
                }
            }

            # Streak logic
            last_msg_time = user_doc.get("last_message")
            if last_msg_time:
                if isinstance(last_msg_time, str):
                    last_msg_time = datetime.datetime.fromisoformat(last_msg_time)
                delta_days = (datetime.datetime.utcnow().date() - last_msg_time.date()).days
                if delta_days == 1:
                    update_data["$inc"]["streak_days"] = 1
                elif delta_days > 1:
                    update_data["$set"]["streak_days"] = 1
            else:
                update_data["$set"]["streak_days"] = 1

            # Save User Progress
            await users_col.update_one({"discordId": discord_id}, update_data, upsert=True)

            # Add Tax to Casino Jackpot
            if tax > 0:
                await globals_col.update_one(
                    {"_id": "casino_jackpot"},
                    {"$inc": {"amount": tax}},
                    upsert=True
                )

            # Pass to Leveling Logic
            if hasattr(self.bot, "leveling") and hasattr(self.bot.leveling, "add_xp"):
                await self.bot.leveling.add_xp(message.author, xp_gain, 0)

        except Exception as e:
            print(f"❌ Message event error for {discord_id}: {e}")

async def setup(bot):
    await bot.add_cog(MessageEvents(bot))