import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from db.database import get_connection

# ===============================
# ⚙️ Role & Channel Config
# ===============================
STAFF_ROLE_IDS = {
    1358470318087340342, 1358472557862457537, 1358472532222808126,
    1358472588430676018, 1358472511133585564, 1358472635234779207,
    1358473248534167663
}

OWNER_ROLE_ID = 1358473248534167663
BOT_LOGS_CHANNEL_ID = 1358486649360748665

# ===============================
# 🔒 Helper Functions
# ===============================
def is_staff(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def is_owner(member: discord.Member) -> bool:
    return any(role.id == OWNER_ROLE_ID for role in member.roles)

# ===============================
# ⚠️ Warn Cog
# ===============================
class Warn(commands.Cog):
    """Issues user warnings, logs them to MongoDB (7-day expiry), and posts to mod logs."""

    def __init__(self, bot):
        self.bot = bot
        db = get_connection()
        self.punishments = db["punishments"]

    @app_commands.command(name="warn", description="Warn a user and log the punishment (Staff only)")
    @app_commands.describe(user="The user to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        staff = interaction.user

        # 1. Permission check
        if not is_staff(staff):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        # 2. Prevent staff from warning other staff unless Owner
        if is_staff(user) and not is_owner(staff):
            return await interaction.response.send_message(
                "⚠️ You cannot warn another staff member unless you are the Owner.",
                ephemeral=True
            )

        # 3. Handle Expiration Logic (7 Days)
        now = datetime.utcnow()
        duration_days = 7
        expires_at = now + timedelta(days=duration_days)
        expiry_ts = int(expires_at.timestamp())

        # 4. Create punishment document for MongoDB
        punishment_doc = {
            "discordId": str(user.id),
            "issuerId": str(staff.id),
            "action": "warn",
            "reason": reason,
            "timestamp": now,
            "durationSeconds": duration_days * 86400,
            "expiresAt": expires_at,
            "extraInfo": "Manual Warning"
        }

        try:
            result = await self.punishments.insert_one(punishment_doc)
            punishment_id = str(result.inserted_id)
        except Exception as e:
            print(f"❌ MongoDB insert error: {e}")
            return await interaction.response.send_message(f"❌ Database error: {e}", ephemeral=True)

        # 5. Build Embed for Feedback and Logs
        embed = discord.Embed(
            title="⚠️ User Warned",
            description=(
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Staff:** {staff.mention} (`{staff.id}`)\n"
                f"**Reason:** {reason}\n"
                f"**Expires:** <t:{expiry_ts}:F> (<t:{expiry_ts}:R>)\n"
                f"**Punishment ID:** `{punishment_id}`"
            ),
            color=discord.Color.gold(),
            timestamp=now
        )
        embed.set_footer(text="Manual warning logged")

        # Send public feedback in channel
        await interaction.response.send_message(content=f"⚠️ {user.mention} has been warned.", embed=embed)

        # 6. Log to bot logs channel
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to send warn log: {e}")

        # 7. DM the warned user
        try:
            await user.send(
                f"⚠️ You have been warned in **{interaction.guild.name}**.\n\n"
                f"**Staff Member:** {staff.name} ({staff.mention})\n"
                f"**Reason:** {reason}\n"
                f"**Expires:** <t:{expiry_ts}:F>\n"
                f"**Punishment ID:** `{punishment_id}`\n\n"
                f"Please follow the server rules to avoid further actions."
            )
        except Exception:
            pass

        print(f"✅ Warned {user} by {staff} — ID {punishment_id}")

async def setup(bot):
    await bot.add_cog(Warn(bot))
    print("✅ Loaded Warn Cog")