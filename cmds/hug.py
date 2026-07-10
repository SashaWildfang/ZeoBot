import discord
from discord.ext import commands
from discord import app_commands
import random

from db.database import get_connection

HUG_MESSAGES = [
    # --- Cozy & Affectionate ---
    "{sender} wraps their arms around {target} in a warm, cozy hug.",
    "{sender} gives {target} a big, squishy bear hug!",
    "{sender} pulls {target} into a long, comforting embrace.",
    "{sender} leans in and gives {target} a soft, gentle hug.",
    "{sender} tackles {target} with a surprise cuddle!",
    
    # --- Friendly & Energetic ---
    "{sender} gives {target} a friendly squeeze!",
    "{sender} wraps a wing/arm around {target} for a quick side-hug.",
    
    # --- Wholesome & Sweet ---
    "{sender} gives {target} a hug that feels like home.",
    "{sender} nestles closer to {target} for a brief, sweet hug.",
    "{sender} offers {target} a hug to brighten their day.",
    
    # --- Playful ---
    "{sender} refuses to let go and keeps hugging {target}!",
    "{sender} boops {target} on the nose before pulling them into a hug."
]

# Fixed to use MongoDB and compare properly
async def hugs_allowed(discord_id: int) -> bool:
    db = get_connection()
    # In MongoDB/Motor, we check if it is not None explicitly
    if db is not None:
        user_settings = await db["users"].find_one({"discordId": discord_id}, {"allowHugs": 1})
        if user_settings:
            # Default to True if the key doesn't exist yet
            return user_settings.get("allowHugs", True)
    return True

class Hug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hug", description="Give someone a hug.")
    @app_commands.checks.cooldown(rate=1, per=10.0, key=lambda i: (i.user.id,))
    async def hug(self, interaction: discord.Interaction, user: discord.User):
        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't hug yourself.", ephemeral=True)
            return

        # Need to await the async function now
        allowed = await hugs_allowed(user.id)
        if not allowed:
            await interaction.response.send_message(f"{user.display_name} has hugs disabled.", ephemeral=True)
            return

        message = random.choice(HUG_MESSAGES).format(
            sender=interaction.user.mention,
            target=user.mention
        )
        await interaction.response.send_message(message)

    @hug.error
    async def on_hug_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ You can hug again in {round(error.retry_after, 1)} seconds.",
                ephemeral=True
            )
        else:
            # For debugging, you can print the error to console
            print(f"Hug Command Error: {error}")

async def setup(bot):
    await bot.add_cog(Hug(bot))