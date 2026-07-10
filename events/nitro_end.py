import discord
from discord.ext import commands
from db.database import get_connection

BOOST_ROLE_ID = 1360260086500561237  # Nitro booster role ID

class NitroEndListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_boost = any(role.id == BOOST_ROLE_ID for role in before.roles)
        after_boost = any(role.id == BOOST_ROLE_ID for role in after.roles)

        # If the user lost Nitro boost
        if before_boost and not after_boost:
            db = get_connection()
            settings_col = db.settings

            # Set daily_reminder to 0 for this user
            settings_col.update_one(
                {"discord_id": str(after.id)},
                {"$set": {"daily_reminder": 0}},
                upsert=True  # optional, ensures document exists
            )
            print(f"✅ Daily reminder reset for user {after.id} (lost Nitro boost)")

async def setup(bot):
    await bot.add_cog(NitroEndListener(bot))
    print("✅ Loaded NitroEndListener Cog (MongoDB)")
