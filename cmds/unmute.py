import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import get_connection

# ===============================
# ⚙️ Role Config
# ===============================
MOD_PLUS_ROLE_IDS = {
    1358472532222808126, # Mod
    1358472588430676018, # Sr Mod
    1358472511133585564, # Admin
    1358472635234779207, # Sr Admin
    1358473248534167663  # Owner
}

DENY_ROLE_ID = 1431581220386373712
BOT_LOGS_CHANNEL_ID = 1358486649360748665

# ===============================
# 🔒 Permission Checks
# ===============================
def has_deny_role(member: discord.Member) -> bool:
    return any(role.id == DENY_ROLE_ID for role in member.roles)

def is_mod_plus(member: discord.Member) -> bool:
    return any(role.id in MOD_PLUS_ROLE_IDS for role in member.roles)

# ===============================
# 🎧 Unmute Cog
# ===============================
class Unmute(commands.Cog):
    """Unmutes a user and synchronizes database states."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.punishments = self.db["punishments"]
        self.pending_unmutes = self.db["pending_unmutes"]

    @app_commands.command(name="unmute", description="Unmute a user (Mod+ only)")
    @app_commands.describe(
        user="The user to unmute",
        reason="Reason for unmuting",
        silent="If true, confirmation is only visible to you"
    )
    async def unmute(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Manual unmute", silent: bool = False):
        staff = interaction.user

        # 1. Permission Checks
        if has_deny_role(staff):
            return await interaction.response.send_message("🚫 Access denied.", ephemeral=True)

        if not is_mod_plus(staff):
            return await interaction.response.send_message("❌ This command requires Mod+.", ephemeral=True)

        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role or muted_role not in user.roles:
            return await interaction.response.send_message("⚠️ This user is not currently muted.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # 2. Discord Action
        try:
            await user.remove_roles(muted_role, reason=f"Unmuted by {staff.name}: {reason}")
        except Exception as e:
            return await interaction.followup.send(f"❌ Discord error: {e}")

        # 3. Database Synchronization
        try:
            # Standardized doc
            unmute_doc = {
                "discordId": str(user.id),
                "issuerId": str(staff.id),
                "action": "unmute",
                "reason": reason,
                "timestamp": datetime.utcnow(),
                "extraInfo": "Manual Unmute",
                "active": False
            }
            
            result = await self.punishments.insert_one(unmute_doc)
            pun_id = str(result.inserted_id)

            # Cleanup: Mark all active mutes for this user as inactive
            await self.punishments.update_many(
                {"discordId": str(user.id), "action": "mute", "active": True},
                {"$set": {"active": False}}
            )

            # Cleanup: Mark any automated pending unmutes as handled
            if self.pending_unmutes is not None:
                await self.pending_unmutes.update_many(
                    {"userDiscordId": user.id, "handled": False},
                    {"$set": {"handled": True}}
                )

        except Exception as e:
            print(f"❌ DB Sync Error: {e}")
            # We don't return here because the Discord unmute already happened

        # 4. Feedback
        embed = discord.Embed(
            title="🔊 User Unmuted",
            description=(
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Staff:** {staff.mention} (`{staff.id}`)\n"
                f"**Reason:** {reason}\n"
                f"🆔 **Log ID:** `{pun_id}`"
            ),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Manual unmute logged")

        await interaction.followup.send(embed=embed)

        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except:
                pass

async def setup(bot):
    await bot.add_cog(Unmute(bot))