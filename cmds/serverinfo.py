# serverinfo.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Display info about the server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(
            title=f"🌐 Server Info: {guild.name}",
            color=discord.Color.from_str("#d69238"),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Preferred Locale", value=str(guild.preferred_locale), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style='F'), inline=False)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Channels", value=len(guild.channels), inline=True)

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    print("✅ Loaded ServerInfo Cog")
    await bot.add_cog(ServerInfo(bot))