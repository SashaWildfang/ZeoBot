import discord
from discord.ext import commands, tasks
import datetime

TARGET_CHANNEL_ID = 1487886250114547762
LOG_CHANNEL_ID = 1360344042705256660
PURGE_TIME = datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc)

class UnverifiedChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_purge.start()

    @tasks.loop(time=PURGE_TIME)
    async def daily_purge(self):
        channel = self.bot.get_channel(TARGET_CHANNEL_ID)
        if channel:
            try:
                await channel.purge(limit=None)
            except Exception:
                pass

    @daily_purge.before_loop
    async def before_daily_purge(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = self.bot.get_channel(TARGET_CHANNEL_ID)
        if channel:
            try:
                await channel.purge(limit=1000, check=lambda m: m.author.id == member.id)
            except Exception:
                pass

    def cog_unload(self):
        self.daily_purge.cancel()

async def setup(bot):
    await bot.add_cog(UnverifiedChat(bot))