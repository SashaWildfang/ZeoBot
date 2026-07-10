import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from db.database import get_connection

# Configuration
ANNOUNCEMENT_CHANNEL_ID = 1358485236073238528
PING_ROLE_ID = 1363972415822237747

class XPWeekendHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.check_weekend.start()

    def cog_unload(self):
        self.check_weekend.cancel()

    @tasks.loop(minutes=30)
    async def check_weekend(self):
        now = datetime.now(ZoneInfo("America/New_York"))
        # Active Friday (4), Saturday (5), Sunday (6)
        is_weekend = now.weekday() in [4, 5, 6]

        config = await self.db.globals.find_one({"id": 1})
        if not config:
            return

        currently_active = config.get("isXpWeekend", 0) == 1

        if is_weekend and not currently_active:
            await self.update_weekend_status(True)
        elif not is_weekend and currently_active:
            await self.update_weekend_status(False)

    async def update_weekend_status(self, active: bool):
        multiplier = 2.0 if active else 1.0
        await self.db.globals.update_one(
            {"id": 1},
            {"$set": {
                "isXpWeekend": 1 if active else 0,
                "xpWeekendMultiplier": multiplier,
                "updatedAt": datetime.utcnow().isoformat() + "Z"
            }}
        )

        channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if channel:
            ping = f"<@&{PING_ROLE_ID}>" if PING_ROLE_ID else "@everyone"
            if active:
                embed = discord.Embed(
                    title="🎉 XP Weekend is Active!",
                    description="Double XP is now live! Your XP Multipliers have been updated" ,
                    color=discord.Color.gold()
                )
                await channel.send(content=ping, embed=embed)
            else:
                embed = discord.Embed(
                    title="⌛ XP Weekend Ended",
                    description="The event has finished. Multipliers have returned to normal",
                    color=discord.Color.red()
                )
                await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(XPWeekendHandler(bot))