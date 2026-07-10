import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import re
from db.database import get_connection

# ===============================
# 🔒 Constants
# ===============================
STAFF_ROLE_IDS = {
    1358470318087340342, 1358472557862457537, 1358472532222808126,
    1358472588430676018, 1358472511133585564, 1358472635234779207,
    1358473248534167663
}

STAFF_TEAM_ROLE_ID = 1358470109965979859
OWNER_ROLE_ID = 1358473248534167663
MUTED_ROLE_ID = 1360956830263541950
BOT_LOGS_CHANNEL_ID = 1358486649360748665
NOTIFICATION_CHANNEL_ID = 1358485891361804358 # Target channel for plain-text alerts
GUILD_ID = 1358466858348576849 

def is_staff(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def parse_duration(time_str: str):
    matches = re.findall(r'(\d+)([dhms])', time_str.lower())
    if not matches: return None
    delta = timedelta()
    for value, unit in matches:
        value = int(value)
        if unit == 'd': delta += timedelta(days=value)
        elif unit == 'h': delta += timedelta(hours=value)
        elif unit == 'm': delta += timedelta(minutes=value)
        elif unit == 's': delta += timedelta(seconds=value)
    return delta if delta.total_seconds() > 0 else None

class TempMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.punishments = self.db["punishments"]
        self.check_unmutes.start()

    def cog_unload(self):
        self.check_unmutes.cancel()

    async def apply_unmute(self, guild, user_id, doc_id, reason_suffix="Expired"):
        """Helper to remove role, update database, and log the action."""
        muted_role = guild.get_role(MUTED_ROLE_ID)
        if not muted_role: return

        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            
            # Remove the role if they have it
            if muted_role in member.roles:
                await member.remove_roles(muted_role, reason=f"TempMute {reason_suffix}")
            
            # 1. Plain Text Notification (UNMUTE)
            notify_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if notify_channel:
                await notify_channel.send(f"🔊 {member.mention}, your mute has expired. You can now speak again.")
            
            # 2. Staff Log (Embed)
            log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🔊 User Unmuted",
                    description=f"**User:** {member.mention} (`{member.id}`)\n**Status:** Role removed automatically.",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text=f"Case ID: {doc_id}")
                await log_channel.send(embed=embed)
                
            print(f"✅ Auto-unmuted {member.name}")
        except discord.NotFound:
            print(f"💨 User {user_id} left the server; case closed.")
        except Exception as e:
            print(f"❌ Error during unmute for {user_id}: {e}")
        finally:
            await self.punishments.update_one({"_id": doc_id}, {"$set": {"active": False}})

    @tasks.loop(seconds=30)
    async def check_unmutes(self):
        """Backup task: Catches anyone missed if the bot was offline."""
        now = datetime.utcnow()
        query = {"action": "tempmute", "active": True, "expiresAt": {"$lte": now}}
        expired_mutes = await self.punishments.find(query).to_list(length=100)

        if not expired_mutes: return

        guild = self.bot.get_guild(GUILD_ID) or await self.bot.fetch_guild(GUILD_ID)
        if not guild: return

        for mute in expired_mutes:
            await self.apply_unmute(guild, int(mute["discordId"]), mute["_id"], "Expired (Backup Loop)")

    @app_commands.command(name="tempmute", description="Mute a user with a role and auto-timer")
    @app_commands.describe(user="User to mute", duration="e.g. 10m, 1h", reason="Reason")
    async def tempmute(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str, silent: bool = False):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        # Protection check: Staff Team vs Owner
        target_is_staff_team = any(role.id == STAFF_TEAM_ROLE_ID for role in user.roles)
        issuer_is_owner = any(role.id == OWNER_ROLE_ID for role in interaction.user.roles)

        if target_is_staff_team and not issuer_is_owner:
            return await interaction.response.send_message("❌ You cannot tempmute a Staff Team member unless you are the Owner.", ephemeral=True)

        delta = parse_duration(duration)
        if not delta:
            return await interaction.response.send_message("❌ Invalid duration format (1d, 1h, 1m).", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        muted_role = interaction.guild.get_role(MUTED_ROLE_ID)
        if not muted_role:
            return await interaction.followup.send("❌ Muted role not found.")

        expires_at = datetime.utcnow() + delta
        doc = {
            "discordId": user.id,
            "issuerId": str(interaction.user.id),
            "action": "tempmute",
            "reason": reason,
            "timestamp": datetime.utcnow(),
            "expiresAt": expires_at,
            "active": True
        }

        try:
            await user.add_roles(muted_role, reason=f"TempMute: {reason}")
            result = await self.punishments.insert_one(doc)
            doc_id = result.inserted_id

            # 1. Plain Text Notification (MUTE)
            notify_channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if notify_channel:
                await notify_channel.send(
                    f"🔇 {user.mention}, you have been muted for **{duration}**.\n"
                    f"**Reason:** {reason}\n"
                    f"**Expires:** <t:{int(expires_at.timestamp())}:R>"
                )

            # 2. Staff Log/Interaction Response (Embeds)
            embed = discord.Embed(
                title="🔇 User Muted",
                description=f"**User:** {user.mention}\n**Ends:** <t:{int(expires_at.timestamp())}:R>\n**Reason:** {reason}",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Case ID: {doc_id}")
            
            await interaction.followup.send(content=f"⚠️ {user.mention} has been muted.", embed=embed)

            log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
            if log_channel: 
                await log_channel.send(embed=embed)

            # Start the Live Timer
            async def run_timer():
                await asyncio.sleep(delta.total_seconds())
                current_status = await self.punishments.find_one({"_id": doc_id})
                if current_status and current_status.get("active"):
                    await self.apply_unmute(interaction.guild, user.id, doc_id, "Expired (Live Timer)")

            asyncio.create_task(run_timer())

        except Exception as e:
            await interaction.followup.send(f"❌ Failed: {e}")

async def setup(bot):
    await bot.add_cog(TempMute(bot))