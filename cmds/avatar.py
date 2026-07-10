# avatar.py
import discord
from discord.ext import commands
from discord import app_commands

class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Show a user's avatar in full size.")
    @app_commands.describe(user="The user whose avatar you want to see")
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"🖼️ Avatar of {user}", color=discord.Color.blurple())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    print("✅ Loaded Avatar Cog")
    await bot.add_cog(Avatar(bot))