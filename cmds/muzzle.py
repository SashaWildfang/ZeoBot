import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import re

MUTED_ROLE_ID = 1360956830263541950  # Your Muted role ID
GUILD_ID = 1358452494128250940       # Your Guild ID
LOGS_CHANNEL_ID = 1358486649360748665  # General Logs channel (Embeds)
UNMUZZLE_LOGS_CHANNEL_ID = 1358485891361804358 # Specific Unmuzzle logs channel (Text only)
BOT_LOGS_CHANNEL_ID = 1360344042705256660 # Bot logs channel for auto-unmuzzle

ADMIN_PLUS_ROLE_IDS = {
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

def parse_duration_string(duration_str: str) -> int:
    """Parses a duration like '2m30s' into seconds."""
    matches = re.findall(r'(\d+)([smh])', duration_str.lower())
    total_seconds = 0
    for value, unit in matches:
        if unit == 's':
            total_seconds += int(value)
        elif unit == 'm':
            total_seconds += int(value) * 60
        elif unit == 'h':
            total_seconds += int(value) * 3600
    return total_seconds

class Muzzle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_muzzles = {}      # user_id -> unmute time
        self.notified_users = set()   # user_ids who already received a muzzle message
        self.check_muzzle_expirations.start()

    def is_admin_plus(self, member: discord.Member) -> bool:
        return any(role.id in ADMIN_PLUS_ROLE_IDS for role in member.roles)

    @app_commands.command(name="muzzle", description="Mute a user for a set time.")
    @app_commands.describe(user="The user to muzzle or unmuzzle.", duration="e.g., 5m, 30s, 2m30s", reason="Optional reason for the muzzle")
    async def muzzle(self, interaction: discord.Interaction, user: discord.Member, duration: str = "1m", reason: str = "No reason provided."):
        if not self.is_admin_plus(interaction.user):
            await interaction.response.send_message("❌ **Permission Denied:** You do not have permission to use this command.")
            return

        muted_role = interaction.guild.get_role(MUTED_ROLE_ID)
        if not muted_role:
            await interaction.response.send_message("❌ **Error:** Muted role not found.")
            return

        logs_channel = self.bot.get_channel(LOGS_CHANNEL_ID)
        unmuzzle_logs_channel = self.bot.get_channel(UNMUZZLE_LOGS_CHANNEL_ID)

        # ==========================================
        # UNMUZZLE LOGIC
        # ==========================================
        if muted_role in user.roles:
            try:
                await user.remove_roles(muted_role, reason=f"Unmuzzled by {interaction.user}")
                self.active_muzzles.pop(user.id, None)
                self.notified_users.discard(user.id)

                await interaction.response.send_message(f"🔊 {user.mention} has been **unmuzzled** by {interaction.user.mention}.")

                # Send Embed to general logs
                if logs_channel:
                    embed = discord.Embed(
                        title="🔊 User Unmuzzled",
                        description=f"{user.mention} was manually unmuzzled by {interaction.user.mention}.",
                        color=discord.Color.green(),
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=f"User ID: {user.id}")
                    await logs_channel.send(embed=embed)
                
                # Send text-only to specific unmuzzle channel
                if unmuzzle_logs_channel:
                    await unmuzzle_logs_channel.send(f"🔊 **User Unmuzzled:** {user.mention} was manually unmuzzled by {interaction.user.mention}.")

            except Exception as e:
                await interaction.response.send_message(f"❌ **Failed to Unmuzzle:** {str(e)}")
        
        # ==========================================
        # MUZZLE LOGIC
        # ==========================================
        else:
            seconds = parse_duration_string(duration)
            if seconds <= 0:
                await interaction.response.send_message("❌ **Invalid Duration:** Please specify a valid duration like `30s`, `1m`, or `2m30s`.")
                return

            try:
                await user.add_roles(muted_role, reason=f"Muzzled by {interaction.user} for {duration} | Reason: {reason}")
                self.active_muzzles[user.id] = datetime.utcnow() + timedelta(seconds=seconds)
                self.notified_users.discard(user.id)

                await interaction.response.send_message(f"🔇 {user.mention} has been **muzzled** by {interaction.user.mention} for `{duration}`.\n**Reason:** {reason}")

                # Send Embed to general logs
                if logs_channel:
                    embed = discord.Embed(
                        title="🔇 User Muzzled",
                        description=f"{user.mention} was muzzled by {interaction.user.mention} for `{duration}`.\n\n**Reason:** {reason}",
                        color=discord.Color.orange(),
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=f"User ID: {user.id}")
                    await logs_channel.send(embed=embed)

            except Exception as e:
                await interaction.response.send_message(f"❌ **Failed to Muzzle:** {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.bot
            or message.guild is None
            or message.guild.id != GUILD_ID
        ):
            return

        muted_role = message.guild.get_role(MUTED_ROLE_ID)
        if muted_role and muted_role in message.author.roles:
            try:
                await message.delete()
                if message.author.id not in self.notified_users:
                    await message.channel.send(f"🔇 {message.author.mention} tried to speak but is muzzled... ahh, sweet silence.")
                    self.notified_users.add(message.author.id)
            except Exception as e:
                print(f"Error deleting muzzled message: {e}")

    @tasks.loop(seconds=10)
    async def check_muzzle_expirations(self):
        now = datetime.utcnow()
        to_unmute = [uid for uid, end in self.active_muzzles.items() if now >= end]

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return

        for user_id in to_unmute:
            member = guild.get_member(user_id)
            if not member:
                continue

            muted_role = guild.get_role(MUTED_ROLE_ID)
            if muted_role and muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role, reason="Muzzle expired")
                    self.notified_users.discard(member.id)
                    print(f"✅ Auto-unmuzzled {member.name}")

                    bot_logs_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)

                    # Send Embed directly to the bot logs instead of punishment logs
                    if bot_logs_channel:
                        embed = discord.Embed(
                            title="🔊 Auto-Unmuzzled",
                            description=f"{member.mention} was automatically unmuzzled after their timeout expired.",
                            color=discord.Color.green(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text=f"User ID: {member.id}")
                        await bot_logs_channel.send(embed=embed)

                except Exception as e:
                    print(f"❌ Failed to auto-unmute {member.name}: {e}")
            self.active_muzzles.pop(user_id, None)

    @check_muzzle_expirations.before_loop
    async def before_check_muzzle_expirations(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Muzzle(bot))