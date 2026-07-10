import discord
from discord.ext import commands
from discord import app_commands
import random
from db.database import get_connection

BOOP_MESSAGES = [
    "{sender} booped {target} on the nose.",
    "{sender} gave {target} a soft boop.",
    "{sender} reached out and booped {target}.",
    "{sender} gently booped {target}.",
    "{sender} looked at {target}, then booped them.",
    "{sender} launched a surprise boop at {target}.",
    "{sender} used Boop! It was super effective on {target}.",
    "{sender} gave {target} a boop and vanished.",
    "{sender} delivered a critical boop to {target}.",
]

# --- Mongo Helpers ---
def get_settings_col():
    db = get_connection()
    return db["settings"]

def boops_allowed(discord_id: int) -> bool:
    try:
        col = get_settings_col()
        doc = col.find_one({"discordId": discord_id}, {"allowBoop": 1})
        # Default True if not found or missing
        return doc is None or doc.get("allowBoop", True)
    except Exception as e:
        print(f"⚠️ boops_allowed Mongo error: {e}")
        return True

class Boop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="boop", description="Boop someone.")
    @app_commands.checks.cooldown(rate=1, per=10.0, key=lambda i: (i.user.id,))
    async def boop(self, interaction: discord.Interaction, user: discord.User):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("You can't boop yourself.", ephemeral=True)

        if not boops_allowed(user.id):
            return await interaction.response.send_message(f"{user.display_name} has boops disabled.", ephemeral=True)

        message = random.choice(BOOP_MESSAGES).format(sender=interaction.user.mention, target=user.mention)
        await interaction.response.send_message(message)

    @boop.error
    async def on_boop_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ You can boop again in {round(error.retry_after, 1)} seconds.",
                ephemeral=True,
            )
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Boop(bot))
    print("✅ Loaded Boop Cog (Mongo Edition)")