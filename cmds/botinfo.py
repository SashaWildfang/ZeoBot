import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import platform
import psutil
import time

CREATOR_ID = 164577223162986498

class BotInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    def get_uptime(self):
        seconds = int(time.time() - self.start_time)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h {minutes}m {seconds}s"

    @app_commands.command(name="botinfo", description="Get information about the bot")
    async def botinfo(self, interaction: discord.Interaction):
        creator = await self.bot.fetch_user(CREATOR_ID)
        uptime = self.get_uptime()
        server_count = len(self.bot.guilds)
        user_count = sum(g.member_count for g in self.bot.guilds if g.member_count)

        embed = discord.Embed(
            title="Zeo Bot Info",
            description="Zeo is a multipurpose moderation and utility bot built for **Kitty Kingdom**. "
                        "It includes auto-mod, user tracking, logging, database integration, and custom Discord features.",
            color=discord.Color.blurple(),
            timestamp=datetime.now()
        )

        embed.add_field(name="Creator", value=f"{creator.mention}", inline=True)
        embed.add_field(name="🆔 Bot ID", value=f"`{self.bot.user.id}`", inline=True)
        embed.add_field(name="📈 Uptime", value=uptime, inline=False)
        embed.add_field(name="🌐 Servers", value=f"{server_count}", inline=True)
        embed.add_field(name="👥 Users", value=f"{user_count:,}", inline=True)
        embed.add_field(name="⚙️ Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="🧠 RAM Usage", value=f"{psutil.Process().memory_info().rss // (1024 ** 2)} MB", inline=True)

        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text="Zeo Bot • Powered by Discord.py")

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BotInfo(bot))
