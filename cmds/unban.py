import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import re
from db.database import get_connection

# ===============================
# ⚙️ Role Config
# ===============================
SR_MOD_PLUS_ROLE_IDS = {
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

DENY_ROLE_ID = 1431581220386373712  # ❌ Hard deny role
BOT_LOGS_CHANNEL_ID = 1358486649360748665

# ===============================
# 🧩 Helper Functions
# ===============================
def has_deny_role(member: discord.Member) -> bool:
    return any(role.id == DENY_ROLE_ID for role in member.roles)

def is_sr_mod_plus(member: discord.Member) -> bool:
    return any(role.id in SR_MOD_PLUS_ROLE_IDS for role in member.roles)

def parse_duration(duration_str: str) -> timedelta | None:
    """Parses a string like '7d', '12h', '30m' into a timedelta object."""
    match = re.match(r'^(\d+)([smhd])$', duration_str.lower().strip())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    if unit == 's': return timedelta(seconds=val)
    if unit == 'm': return timedelta(minutes=val)
    if unit == 'h': return timedelta(hours=val)
    if unit == 'd': return timedelta(days=val)
    return None

# ===============================
# 🎧 Unban Cog
# ===============================
class Unban(commands.Cog):
    """Allows Sr Mod+ users to unban members, schedule unbans, and log it in MongoDB."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.punishments = self.db["punishments"]
        self.check_scheduled_unbans.start() # Start the background loop

    def cog_unload(self):
        self.check_scheduled_unbans.cancel()

    @app_commands.command(name="unban", description="Unban a user immediately or schedule an unban (Sr Mod+ only)")
    @app_commands.describe(
        user_id="The Discord ID of the user to unban",
        reason="Reason for the unban",
        duration="Optional: Delay the unban (e.g., '7d', '12h', '30m')",
        silent="If true, confirmation is only visible to you"
    )
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str, duration: str = None, silent: bool = False):
        staff = interaction.user

        # 🔒 Permissions Check
        if has_deny_role(staff):
            return await interaction.response.send_message("🚫 You are barred from using staff commands.", ephemeral=True)

        if not is_sr_mod_plus(staff):
            return await interaction.response.send_message("❌ This command requires Sr Mod+ permissions.", ephemeral=True)

        # 🧾 Validate User ID
        try:
            target_id = int(user_id)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid user ID format. Please provide a numeric ID.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # 🔍 Find user in ban list
        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=target_id))
            user = ban_entry.user
        except discord.NotFound:
            return await interaction.followup.send("⚠️ This user is not currently banned.")
        except Exception as e:
            return await interaction.followup.send(f"❌ Error fetching ban info: {e}")

        # ⏳ Scheduled Unban Logic
        if duration:
            parsed_duration = parse_duration(duration)
            if not parsed_duration:
                return await interaction.followup.send("❌ Invalid duration format. Use a number followed by s, m, h, or d (e.g., `7d`, `12h`).")
            
            unban_time = datetime.utcnow() + parsed_duration

            # Invalidate any previously scheduled unbans for this user to avoid duplicates
            await self.punishments.update_many(
                {"discordId": str(target_id), "action": "scheduled_unban", "executed": False},
                {"$set": {"executed": True, "extraInfo": "Cancelled/Overwritten by new schedule"}}
            )

            schedule_doc = {
                "discordId": str(user.id),
                "issuerId": str(staff.id),
                "action": "scheduled_unban",
                "reason": reason,
                "timestamp": datetime.utcnow(),
                "scheduledTime": unban_time,
                "executed": False,
                "extraInfo": f"Scheduled to automatically unban in {duration}"
            }
            
            result = await self.punishments.insert_one(schedule_doc)
            
            embed = discord.Embed(
                title="⏳ Unban Scheduled",
                description=(
                    f"**User:** {user.name} (`{user.id}`)\n"
                    f"**Staff:** {staff.mention}\n"
                    f"**Reason:** {reason}\n"
                    f"**Unban Time:** <t:{int(unban_time.timestamp())}:R>\n"
                    f"🆔 **Log ID:** `{result.inserted_id}`"
                ),
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="This user will be unbanned automatically.")
            return await interaction.followup.send(embed=embed)

        # 🕊️ Immediate Unban Logic
        try:
            await interaction.guild.unban(user, reason=f"Unbanned by {staff.name}: {reason}")
        except discord.Forbidden:
            return await interaction.followup.send("❌ I do not have permission to unban users.")
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to unban: {e}")

        # 🗃️ Database Update
        await self.punishments.update_many(
            {"discordId": str(target_id), "action": "ban", "active": True},
            {"$set": {"active": False}}
        )

        unban_doc = {
            "discordId": str(user.id),
            "issuerId": str(staff.id),
            "action": "unban",
            "reason": reason,
            "timestamp": datetime.utcnow(),
            "extraInfo": "Manual Immediate Unban",
            "active": False
        }
        
        result = await self.punishments.insert_one(unban_doc)
        punishment_id = str(result.inserted_id)

        # 📄 Build Embed
        embed = discord.Embed(
            title="🔊 User Unbanned",
            description=(
                f"**User:** {user.name} (`{user.id}`)\n"
                f"**Staff:** {staff.mention} (`{staff.id}`)\n"
                f"**Reason:** {reason}\n"
                f"🆔 **Log ID:** `{punishment_id}`"
            ),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="Ban revoked and logged")

        await interaction.followup.send(embed=embed)

        # 📢 Log to Channel
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except:
                pass

    # ===============================
    # 🔄 Background Task
    # ===============================
    @tasks.loop(minutes=1)
    async def check_scheduled_unbans(self):
        """Periodically checks MongoDB for scheduled unbans that are due."""
        await self.bot.wait_until_ready()
        now = datetime.utcnow()
        
        # Find all pending scheduled unbans where the time has passed
        cursor = self.punishments.find({"action": "scheduled_unban", "executed": False, "scheduledTime": {"$lte": now}})
        pending_unbans = await cursor.to_list(length=100)

        for doc in pending_unbans:
            user_id = int(doc["discordId"])
            guild = self.bot.guilds[0] # Assuming bot is mainly used in one guild
            
            try:
                user = await self.bot.fetch_user(user_id)
                await guild.unban(user, reason=f"Scheduled Auto-Unban | Reason: {doc.get('reason', 'None')}")
                status_msg = "Successfully unbanned."
                color = discord.Color.green()
                
                # Mark original ban as inactive
                await self.punishments.update_many(
                    {"discordId": str(user_id), "action": "ban", "active": True},
                    {"$set": {"active": False}}
                )
            except discord.NotFound:
                status_msg = "User was already unbanned manually."
                user = discord.Object(id=user_id)
                color = discord.Color.yellow()
            except Exception as e:
                status_msg = f"Failed to unban: {e}"
                user = discord.Object(id=user_id)
                color = discord.Color.red()

            # Mark this scheduled task as executed
            await self.punishments.update_one(
                {"_id": doc["_id"]},
                {"$set": {"executed": True, "extraInfo": status_msg}}
            )

            # Log to the staff channel
            log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="⏰ Scheduled Unban Executed",
                    description=(
                        f"**User ID:** `{user_id}`\n"
                        f"**Original Issuer:** <@{doc['issuerId']}>\n"
                        f"**Original Reason:** {doc.get('reason', 'N/A')}\n"
                        f"**Status:** {status_msg}"
                    ),
                    color=color,
                    timestamp=datetime.utcnow()
                )
                try:
                    await log_channel.send(embed=embed)
                except:
                    pass

async def setup(bot):
    await bot.add_cog(Unban(bot))