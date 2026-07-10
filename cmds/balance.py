import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection

def abbreviate_number(num: int) -> str:
    """Converts large numbers into abbreviated formats (e.g., 1,240,000 -> 1.24M)"""
    if abs(num) < 1000:
        return f"{num:,}"
    
    magnitude = 0
    suffixes = ["", "k", "M", "B", "T", "Q"]
    
    temp_num = float(abs(num))
    while temp_num >= 1000 and magnitude < len(suffixes) - 1:
        magnitude += 1
        temp_num /= 1000.0
        
    # Format to 2 decimals, then strip trailing zeroes and decimal point if they aren't needed
    formatted_num = f"{temp_num:.2f}".rstrip('0').rstrip('.')
    result = f"{formatted_num}{suffixes[magnitude]}"
    
    # Re-apply negative sign if the balance is negative
    return f"-{result}" if num < 0 else result


class Balance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]

    @app_commands.command(name="balance", description="Check your balance or another user's balance.")
    @app_commands.describe(member="The user whose balance you want to check (leave blank for yourself)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        # If no member is provided, default to the user who ran the command
        target_user = member or interaction.user
        
        # Defer the response since we are making a database call
        await interaction.response.defer()

        # Fetch the user's data from the database
        user_data = await self.users_col.find_one({"discordId": target_user.id})
        
        # The currency field in the DB is now 'balance'
        raw_balance = user_data.get("balance", 0) if user_data else 0

        # Calculate the abbreviated version
        abbreviated = abbreviate_number(raw_balance)

        # Build a clean, styled embed showing the abbreviation big, and the comma-formatted exact amount small
        embed = discord.Embed(
            title=f"Balance | {target_user.display_name}",
            description=f"**{abbreviated} <:leaf:1524758896659660831>**\n*(Exact: {raw_balance:,})*",
            color=discord.Color.green()  # Optional: Changed to green to match the "leaves" theme! (Was gold)
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)

        # If checking someone else's balance, add a small footer for clarity
        if target_user != interaction.user:
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Balance(bot))