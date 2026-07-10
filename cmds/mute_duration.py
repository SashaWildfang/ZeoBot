import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from db.database import get_connection

# -------------------------------
# ⚙️ Role Permissions
# -------------------------------

STAFF_TEAM_ROLE_ID = 1358470109965979859

def is_staff(member: discord.Member) -> bool:
    """Return True if the member has the Staff Team role."""
    # Safety check in case member is somehow a User object without roles
    if not isinstance(member, discord.Member):
        return False
    return any(role.id == STAFF_TEAM_ROLE_ID for role in member.roles)

# -------------------------------
# 🧩 MuteDuration Cog
# -------------------------------

class MuteDuration(commands.Cog):
    """Check how long a user is muted for using MongoDB data."""

    def __init__(self, bot):
        self.bot = bot

    def punishments_col(self):
        db = get_connection()
        return db["punishments"]

    @app_commands.command(name="muteduration", description="Check how long someone is muted for.")
    @app_commands.describe(user="The user to check mute duration for (leave blank to check yourself)")
    async def muteduration(self, interaction: discord.Interaction, user: discord.User = None):
        requester = interaction.user
        
        # If no user is specified, assume they are checking themselves
        if user is None:
            user = requester

        is_requester_staff = is_staff(requester)

        # Permissions: non-staff can only check themselves
        if not is_requester_staff and user.id != requester.id:
            await interaction.response.send_message(
                "❌ You can only check your own mute duration. You need the **Staff Team** role to check others.",
                ephemeral=True
            )
            return

        col = self.punishments_col()

        try:
            # Fetch the latest mute record with a duration
            punishment = col.find_one(
                {
                    "userDiscordId": user.id,
                    "action": "mute",
                    "durationSeconds": {"$ne": None}
                },
                sort=[("timestamp", -1)]
            )

            if not punishment:
                msg = (
                    f"ℹ️ {user.mention} does not have an active temporary mute on record."
                    if user.id != requester.id
                    else "ℹ️ You do not have an active temporary mute on record."
                )
                await interaction.response.send_message(msg, ephemeral=True)
                return

            start_time = punishment.get("timestamp")
            duration_seconds = punishment.get("durationSeconds")

            # Convert to datetime if stored as string
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time)
                except ValueError:
                    start_time = datetime.utcnow()

            unmute_time = start_time + timedelta(seconds=duration_seconds)
            now = datetime.utcnow()

            # Check if mute already expired
            if now >= unmute_time:
                msg = (
                    f"🔊 {user.mention} is no longer muted."
                    if user.id != requester.id
                    else "🔊 You are no longer muted."
                )
                await interaction.response.send_message(msg, ephemeral=True)
                return

            remaining = unmute_time - now
            human_readable = str(remaining).split(".")[0]  # Drop milliseconds

            embed = discord.Embed(
                title="🔇 Mute Duration Check",
                description=(
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Muted Until:** <t:{int(unmute_time.timestamp())}:F>\n"
                    f"**Time Remaining:** `{human_readable}`"
                ),
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Mute status fetched from database")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"❌ Error checking mute duration for {user}: {e}")
            await interaction.response.send_message(
                "⚠️ An error occurred while checking mute duration.",
                ephemeral=True
            )

# -------------------------------
# ⚙️ Setup
# -------------------------------

async def setup(bot):
    await bot.add_cog(MuteDuration(bot))
