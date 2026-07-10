import discord
from discord.ext import commands
from discord import app_commands
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import psutil

START_TIME = time.time()

class Uptime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uptime", description="Show Zeo bot's uptime and system boot time.")
    async def uptime(self, interaction: discord.Interaction):
        eastern = ZoneInfo("America/New_York")
        current_time = datetime.now(eastern)
        uptime_seconds = int(time.time() - START_TIME)

        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_parts = []
        if days:
            uptime_parts.append(f"{days}d")
        if hours:
            uptime_parts.append(f"{hours}h")
        if minutes:
            uptime_parts.append(f"{minutes}m")
        uptime_parts.append(f"{seconds}s")
        uptime_str = " ".join(uptime_parts)

        boot_time = datetime.fromtimestamp(psutil.boot_time(), eastern).strftime("%B %d, %Y at %I:%M %p %Z")

        embed = discord.Embed(
            title="📊 Zeo Bot Uptime",
            color=discord.Color.from_str("#d69238"),
            timestamp=current_time
        )

        embed.add_field(name="🕒 Uptime", value=f"`{uptime_str}`", inline=False)
        embed.add_field(name="💻 System Boot Time", value=boot_time, inline=False)
        embed.set_footer(text="Zeo bot status")

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Uptime(bot))
