import discord
from discord.ext import commands
from discord import app_commands

class Patreon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="patreon", description="View the Patreon link for supporting the server.")
    async def patreon(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="💖 Support Kitty Kingdom on Patreon",
            description=(
                "Join our amazing supporters and unlock exclusive perks, roles, Leaves <:leaf:1524758896659660831>, and bonus XP rewards!\n\n"
                "Your support helps us grow and continue providing great experiences for everyone.\n\n"
                "👉 [Click here to view our Patreon tiers and sign up](https://www.patreon.com/c/thekittykingdom/membership)"
            ),
            color=discord.Color.pink()
        )
        embed.set_footer(text="Thank you for considering becoming a Patron!")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Patreon(bot))
    print("Loaded Patreon Cog")