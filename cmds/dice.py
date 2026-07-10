import discord
from discord.ext import commands
from discord import app_commands
import random

class Dice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dice", description="Roll a die! Defaults to 6 sides.")
    @app_commands.describe(sides="The number of sides on the die (defaults to 6)")
    async def roll(self, interaction: discord.Interaction, sides: int = 6):
        # Prevent impossible dice rolls
        if sides < 2:
            return await interaction.response.send_message("❌ A die must have at least 2 sides!", ephemeral=True)

        # Roll the dice based on the input amount
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title="🎲 Dice Roll",
            description=f"You rolled a **{result}** on a d{sides}!",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Dice(bot))