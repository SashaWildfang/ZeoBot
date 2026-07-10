import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

from db.punishments import log_punishment
from db.database import get_connection


# -------------------------------
# ⚙️ Configuration
# -------------------------------

STAFF_ROLE_IDS = {
    1358472557862457537,  # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

BOT_LOGS_CHANNEL_ID = 1358486649360748665
BAN_APPEAL_LINK = "https://forms.gle/AgbY3XDFFVmVTjab9"
REJOIN_LINK = "https://discord.gg/SYm3Z7fr7c"


# -------------------------------
# 🧩 Helper Functions
# -------------------------------

def is_staff(member: discord.Member) -> bool:
    """Check if a member has any staff role."""
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)


def get_users_collection():
    """Return the MongoDB users collection."""
    db = get_connection()
    return db["users"]


# -------------------------------
# ⚔️ Kick Command
# -------------------------------

class Kick(commands.Cog):
    """Kick a user from the server (for staff use only)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Kick a user from the server (Staff only).")
    @app_commands.describe(
        user="The user to kick",
        reason="Reason for the kick",
        silent="If true, suppresses public messages and logs only to the bot logs"
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        silent: bool = False
    ):
        """Kick a member, log punishment in MongoDB, and notify both parties."""

        # Check staff permissions
        if not is_staff(interaction.user):
            return await interaction.response.send_message(
                "❌ You do not have permission to use this command (Staff only).",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=silent)

        # ----------------------------------------
        # ✅ Log punishment in database (AWAIT FIX)
        # ----------------------------------------
        punishment_id = await log_punishment(
            user.id,
            interaction.user.id,
            "kick",
            reason,
            extra_info="Manual Kick"
        )

        # ----------------------------------------
        # DM the user
        # ----------------------------------------
        dm_sent = False
        try:
            await user.send(
                f"👢 You have been kicked from **{interaction.guild.name}**.\n"
                f"📝 **Reason:** {reason}\n"
                f"🆔 **Punishment ID:** `{punishment_id}`\n\n"
                f"If you believe this was a mistake, you may appeal here:\n**{BAN_APPEAL_LINK}**\n"
                f"Use the **Punishment ID** in your appeal form.\n\n"
                f"You can also rejoin using this invite (if allowed):\n**{REJOIN_LINK}**"
            )
            dm_sent = True
        except discord.Forbidden:
            print(f"⚠️ Could not DM {user} — DMs closed.")
        except Exception as e:
            print(f"⚠️ Unexpected DM error for {user}: {e}")

        # Suppress public leave messages if silent
        leave_cog = self.bot.get_cog("MemberLeave")
        if silent and leave_cog:
            leave_cog.mark_silent(user.id)

        # ----------------------------------------
        # Execute the kick
        # ----------------------------------------
        try:
            await user.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.followup.send("❌ I do not have permission to kick that user.", ephemeral=True)
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Kick failed due to an API error: {e}", ephemeral=True)

        # ----------------------------------------
        # Update user stats in Mongo
        # ----------------------------------------
        users_col = get_users_collection()
        users_col.update_one(
            {"discordId": user.id},
            {"$inc": {"kicksReceived": 1}, "$set": {"lastKick": datetime.utcnow()}},
            upsert=True
        )

        # ----------------------------------------
        # Create embed
        # ----------------------------------------
        embed = discord.Embed(
            title="👢 User Kicked",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="Staff", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)

        # ✅ REAL punishment ID now prints
        embed.add_field(name="Punishment ID", value=f"`{punishment_id}`", inline=False)

        embed.set_footer(text="Manual Kick Issued")

        embed.add_field(name="DM Sent", value="✅ Yes" if dm_sent else "❌ No", inline=True)

        # ----------------------------------------
        # Send embed to logs
        # ----------------------------------------
        try:
            log_channel = await self.bot.fetch_channel(BOT_LOGS_CHANNEL_ID)
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send kick log: {e}")

        # ----------------------------------------
        # Response to staff
        # ----------------------------------------
        if not silent:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Kick logged silently.", ephemeral=True)


# -------------------------------
# ⚙️ Cog Setup
# -------------------------------

async def setup(bot):
    await bot.add_cog(Kick(bot))
