import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import get_connection

# ===============================
# ⚙️ Role Config
# ===============================
MOD_PLUS_ROLE_IDS = {
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

STAFF_TEAM_ROLE_ID = 1358470109965979859
OWNER_ROLE_ID = 1358473248534167663
DENY_ROLE_ID = 1431581220386373712  # ❌ Hard deny role

BOT_LOGS_CHANNEL_ID = 1358486649360748665

# ===============================
# 🔒 Permission Helpers
# ===============================
def has_deny_role(member: discord.Member) -> bool:
    return any(role.id == DENY_ROLE_ID for role in member.roles)

def is_mod_plus(member: discord.Member) -> bool:
    return any(role.id in MOD_PLUS_ROLE_IDS for role in member.roles)

def is_owner(member: discord.Member) -> bool:
    return any(role.id == OWNER_ROLE_ID for role in member.roles)

# ===============================
# 🎧 Mute Cog
# ===============================
class Mute(commands.Cog):
    """Permanently mutes a user, logs to MongoDB, and notifies logs."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.punishments = self.db["punishments"]

    @app_commands.command(name="mute", description="Permanently mute a user (Mod+ only)")
    @app_commands.describe(
        user="The user to mute",
        reason="Reason for the mute",
        silent="If true, the confirmation is only visible to you"
    )
    async def mute(self, interaction: discord.Interaction, user: discord.Member, reason: str, silent: bool = False):
        staff = interaction.user

        # 🔒 Permissions Check
        if has_deny_role(staff):
            return await interaction.response.send_message("🚫 You are barred from using staff commands.", ephemeral=True)

        if not is_mod_plus(staff):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

        # Protection check: Staff Team vs Owner
        target_is_staff_team = any(role.id == STAFF_TEAM_ROLE_ID for role in user.roles)
        issuer_is_owner = any(role.id == OWNER_ROLE_ID for role in staff.roles)

        if target_is_staff_team and not issuer_is_owner:
            return await interaction.response.send_message("❌ You cannot permanently mute a Staff Team member unless you are the Owner.", ephemeral=True)

        # Fallback check for other staff ranks just in case
        if is_mod_plus(user) and not is_owner(staff):
            return await interaction.response.send_message("⚠️ Only the Owner can mute other staff members.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # 🔇 Handle Muted Role
        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Muted", reason="Mute system setup")
                for channel in interaction.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)
            except Exception as e:
                return await interaction.followup.send(f"❌ Could not create Muted role: {e}")

        if muted_role in user.roles:
            return await interaction.followup.send("⚠️ This user is already muted.")

        # 🗃️ Database Entry
        punishment_doc = {
            "discordId": str(user.id),
            "issuerId": str(staff.id),
            "action": "mute",
            "reason": reason,
            "timestamp": datetime.utcnow(),
            "durationSeconds": None,  # None indicates permanent
            "expiresAt": None,
            "extraInfo": "Manual Permanent Mute"
        }

        try:
            # Apply Role first
            await user.add_roles(muted_role, reason=f"Muted by {staff.name}: {reason}")
            
            # Log to DB
            result = await self.punishments.insert_one(punishment_doc)
            punishment_id = str(result.inserted_id)
        except Exception as e:
            print(f"❌ Mute Error: {e}")
            return await interaction.followup.send(f"❌ System error during mute: {e}")

        # 📝 Build Embed
        embed = discord.Embed(
            title="🔇 User Muted",
            description=(
                f"**User:** {user.mention} (`{user.id}`)\n"
                f"**Staff:** {staff.mention} (`{staff.id}`)\n"
                f"**Reason:** {reason}\n"
                f"🆔 **Punishment ID:** `{punishment_id}`"
            ),
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Permanent Mute Logged")

        await interaction.followup.send(embed=embed)

        # 📢 Log to Channel
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except:
                pass

async def setup(bot):
    await bot.add_cog(Mute(bot))