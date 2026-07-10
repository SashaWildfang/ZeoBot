import discord
from discord.ext import commands
from pymongo import UpdateOne
import asyncio
from db.database import get_connection

BOT_LOG_CHANNEL_ID = 1360344042705256660

class RoleChangeListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Role IDs and their XP, Leaf, and Profile Weight bonus multipliers
        self.role_multipliers = {
            1362102163693633818: {"xp": 0.10, "leaf": 0.0, "weight": 1.5},   # Tier 1 Patreon
            1362502662721114245: {"xp": 0.20, "leaf": 0.0, "weight": 2.0},   # Tier 2 Patreon
            1362502871639396362: {"xp": 0.40, "leaf": 0.0, "weight": 2.5},   # Tier 3 Patreon
            1360260086500561237: {"xp": 0.15, "leaf": 0.15, "weight": 1.0}   # Nitro Booster
        }

    def calculate_multipliers(self, roles):
        xp_bonus = 0.0
        leaf_bonus = 0.0
        weight_bonus = 0.0
        
        for role in roles:
            if role.id in self.role_multipliers:
                xp_bonus += self.role_multipliers[role.id]["xp"]
                leaf_bonus += self.role_multipliers[role.id]["leaf"]
                weight_bonus += self.role_multipliers[role.id]["weight"]
                
        return round(1.0 + xp_bonus, 2), round(1.0 + leaf_bonus, 2), round(1.0 + weight_bonus, 2)

    async def update_user_multipliers(self, member: discord.Member):
        """Updates a single user when their roles change naturally."""
        new_xp, new_leaf, new_weight = self.calculate_multipliers(member.roles)
        
        user_id_str = str(member.id)
        user_id_int = member.id

        try:
            # Run the database operations in a thread to avoid blocking the bot
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_update_db, user_id_str, user_id_int, new_xp, new_leaf, new_weight)

            # Send log embed
            log_channel = self.bot.get_channel(BOT_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="📊 Role Update - Multipliers Adjusted",
                    description=(
                        f"**User:** {member.mention} ({user_id_str})\n"
                        f"**New XP Multiplier:** {new_xp}x\n"
                        f"**New <:leaf:1524758896659660831> Multiplier:** {new_leaf}x\n"
                        f"**New Profile Weight:** {new_weight}"
                    ),
                    color=discord.Color.red()
                )
                await log_channel.send(embed=embed)

            print(f"✅ Updated multipliers for {member.display_name}: XP {new_xp}x, 🍃 {new_leaf}x")

        except Exception as e:
            print(f"❌ Failed to update multipliers for {member.display_name}: {e}")

    def _sync_update_db(self, user_id_str, user_id_int, new_xp, new_leaf, new_weight):
        """Synchronous helper for DB calls to be run in executor."""
        db = get_connection()
        users_col = db.users
        dating_col = db["dating_profiles"]

        user_doc = users_col.find_one({"discordId": user_id_str}, {"xpMultiplier": 1, "multiplier": 1})
        current_xp = user_doc.get("xpMultiplier", 1.0) if user_doc else 1.0
        current_leaf = user_doc.get("multiplier", 1.0) if user_doc else 1.0

        dating_doc = dating_col.find_one({"_id": user_id_int}, {"profile_weight": 1})
        current_weight = dating_doc.get("profile_weight", 1.0) if dating_doc else 1.0

        if current_xp == new_xp and current_leaf == new_leaf and current_weight == new_weight:
            return

        users_col.update_one(
            {"discordId": user_id_str},
            {"$set": {
                "xpMultiplier": new_xp,
                "multiplier": new_leaf,
                "updatedAt": discord.utils.utcnow()
            }},
            upsert=True
        )
        
        if dating_doc:
            dating_col.update_one(
                {"_id": user_id_int},
                {"$set": {"profile_weight": new_weight}}
            )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        tracked_roles = set(self.role_multipliers.keys())
        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}

        if (after_roles - before_roles) & tracked_roles or (before_roles - after_roles) & tracked_roles:
            await self.update_user_multipliers(after)

# ==========================================
# BACKGROUND STARTUP SYNC
# ==========================================
async def initial_sync(bot, cog):
    await bot.wait_until_ready()
    print("⏳ Starting background multiplier sync...")
    
    try:
        db = get_connection()
        users_col = db.users
        dating_col = db["dating_profiles"]

        user_updates = []
        dating_updates = []
        member_count = 0
        
        for guild in bot.guilds:
            for member in guild.members:
                if member.bot: 
                    continue
                
                new_xp, new_leaf, new_weight = cog.calculate_multipliers(member.roles)
                
                user_updates.append(UpdateOne(
                    {"discordId": str(member.id)},
                    {"$set": {
                        "xpMultiplier": new_xp, 
                        "multiplier": new_leaf,
                        "updatedAt": discord.utils.utcnow()
                    }},
                    upsert=True 
                ))
                
                dating_updates.append(UpdateOne(
                    {"_id": member.id},
                    {"$set": {"profile_weight": new_weight}},
                    upsert=False 
                ))
                
                member_count += 1

        # Run bulk writes in a thread so the bot doesn't freeze
        loop = asyncio.get_event_loop()
        if user_updates:
            await loop.run_in_executor(None, users_col.bulk_write, user_updates)
        if dating_updates:
            await loop.run_in_executor(None, dating_col.bulk_write, dating_updates)

        print(f"✅ Background sync complete! Checked {member_count} members.")
        
    except Exception as e:
        print(f"❌ Background sync failed: {e}")

async def setup(bot):
    cog = RoleChangeListener(bot)
    await bot.add_cog(cog)
    bot.loop.create_task(initial_sync(bot, cog))