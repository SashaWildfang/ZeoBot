import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import asyncio  # Added for timeout support
from db.database import get_connection
from db.punishments import log_punishment

# -------------------------------
# ⚙️ Configuration
# -------------------------------
MOD_PLUS_ROLE_IDS = {
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

OWNER_ROLE_ID = 1358473248534167663
BOT_LOGS_CHANNEL_ID = 1358486649360748665
BAN_APPEAL_LINK = "https://forms.gle/AgbY3XDFFVmVTjab9"

# -------------------------------
# 🧩 Helper Functions
# -------------------------------
def is_mod_plus(member: discord.Member) -> bool:
    return any(r.id in MOD_PLUS_ROLE_IDS for r in member.roles)

def is_owner(member: discord.Member) -> bool:
    return any(r.id == OWNER_ROLE_ID for r in member.roles)

# -------------------------------
# 🔨 Ban Cog
# -------------------------------
class Ban(commands.Cog):
    """Handles permanent bans and logs them through unified punishment logger."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ban", description="Permanently ban a user (Mod+ only)")
    @app_commands.describe(
        user="The user to ban",
        reason="Reason for the ban",
        silent="If True, suppresses the public ban message"
    )
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str, silent: bool = False):
        
        DENY_ROLE_ID = 1431581220386373712

        # 1. Permission Checks
        if any(role.id == DENY_ROLE_ID for role in interaction.user.roles):
            return await interaction.response.send_message("⚠️ You are not allowed to use this command.", ephemeral=True)

        if not is_mod_plus(interaction.user):
            return await interaction.response.send_message("⚠️ You lack permission to use this command.", ephemeral=True)

        # 2. Staff Hierarchy Check
        member = interaction.guild.get_member(user.id)
        if member and is_mod_plus(member) and not is_owner(interaction.user):
            return await interaction.response.send_message(
                "⚠️ You can’t ban another staff member unless you are the Owner.",
                ephemeral=True
            )

        # 3. Defer Response
        await interaction.response.defer(ephemeral=silent)

        # 4. Log Punishment to Database (Corrected Keyword Arguments)
        try:
            # We wrap this in wait_for to prevent the "eternal thinking" bug
            punishment_id = await asyncio.wait_for(
                log_punishment(
                    user_id=user.id,             # Corrected from user_discord_id
                    issuer_id=interaction.user.id, # Corrected from issuer_discord_id
                    action="ban",
                    reason=reason,
                    duration=None,               # Corrected from duration_seconds
                    extra_info="Manual Ban"
                ),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            punishment_id = "DB_TIMEOUT"
            print("⚠️ Database log timed out.")
        except Exception as e:
            punishment_id = "ERROR"
            print(f"⚠️ Failed to log punishment: {e}")

        # 5. DM the user
        dm_sent = False
        try:
            await user.send(
                f"⚠️ You have been **permanently banned** from **{interaction.guild.name}**.\n\n"
                f"**Staff Member:** {interaction.user.name}\n"
                f"**Reason:** {reason}\n"
                f"**Punishment ID:** `{punishment_id}`\n\n"
                f"If you wish to appeal, use the form below and include the punishment ID:\n"
                f"👉 {BAN_APPEAL_LINK}"
            )
            dm_sent = True
        except Exception:
            pass

        # 6. Execute Ban
        try:
            leave_cog = self.bot.get_cog("MemberLeave")
            if silent and leave_cog and hasattr(leave_cog, "mark_silent"):
                leave_cog.mark_silent(user.id)

            await interaction.guild.ban(
                discord.Object(id=user.id),
                reason=f"Issued by {interaction.user}: {reason}",
                delete_message_days=1
            )
        except discord.Forbidden:
            return await interaction.followup.send("⚠️ I do not have permission to ban this user.", ephemeral=True)
        except discord.HTTPException as e:
            return await interaction.followup.send(f"⚠️ Ban failed: {e}", ephemeral=True)

        # 7. Create Enhanced Embed for Logs/Response
        embed = discord.Embed(
            title="🔨 Permanent Ban Issued",
            color=discord.Color.dark_red(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Core Info
        embed.add_field(name="👤 User", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="🛡️ Moderator", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
        embed.add_field(name="📩 DM Sent", value="✅ Yes" if dm_sent else "❌ No", inline=True)
        
        # Reason
        embed.add_field(name="📄 Reason", value=f"**{reason}**", inline=False)
        
        # Stats & Dates
        created_ts = int(user.created_at.timestamp())
        embed.add_field(name="📅 Account Created", value=f"<t:{created_ts}:f>\n(<t:{created_ts}:R>)", inline=True)
        
        if member and member.joined_at:
            joined_ts = int(member.joined_at.timestamp())
            embed.add_field(name="📥 Joined Server", value=f"<t:{joined_ts}:f>\n(<t:{joined_ts}:R>)", inline=True)
        else:
            embed.add_field(name="📥 Joined Server", value="*Not in server*", inline=True)
            
        embed.add_field(name="🔖 Punishment ID", value=f"`{punishment_id}`", inline=True)

        embed.set_footer(text=f"User ID: {user.id}")

        # 8. Send Final Confirmation
        if not silent:
            await interaction.followup.send(content=f"⚠️ {user.mention} has been banned.", embed=embed)
        else:
            await interaction.followup.send("⚠️ Ban logged silently.", ephemeral=True)

        # 9. Log to bot logs channel
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to send ban log: {e}")

async def setup(bot):
    await bot.add_cog(Ban(bot))
    print("✅ Loaded Ban Cog")