import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re

BOT_LOGS_CHANNEL_ID = 1360344042705256660
DISCORD_MEMBER_ROLE_ID = 1358469854725931038

DENY_ROLE_ID = 1431581220386373712  # ❌ Hard deny role (overrides everything)

# Used to let staff continue talking in locked channels
HELPER_AND_HIGHER_ROLE_IDS = {
    1358470318087340342, # Helper
    1358472557862457537, # Jr Mod
    1358472532222808126, # Mod
    1358472588430676018, # Sr Mod
    1358472511133585564, # Admin
    1358472635234779207, # Sr Admin
    1358473248534167663  # Owner
}

# Used for command permissions
JR_MOD_AND_HIGHER_ROLE_IDS = {
    1358472557862457537, # Jr Mod
    1358472532222808126, # Mod
    1358472588430676018, # Sr Mod
    1358472511133585564, # Admin
    1358472635234779207, # Sr Admin
    1358473248534167663  # Owner
}

def parse_duration(duration: str) -> int | None:
    match = re.match(r"^(\d+)([smhd])$", duration.lower())
    if not match:
        return None
    value, unit = match.groups()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(value) * multipliers[unit]

class ChannelLock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locked_channels = set()

    # -------------------------------
    # 🔐 Permission Helpers
    # -------------------------------

    def has_deny_role(self, member: discord.Member) -> bool:
        return any(role.id == DENY_ROLE_ID for role in member.roles)

    def is_jrmod_or_higher(self, member: discord.Member) -> bool:
        return any(role.id in JR_MOD_AND_HIGHER_ROLE_IDS for role in member.roles)

    # -------------------------------
    # 🔒 Lock Channel
    # -------------------------------

    @app_commands.command(
        name="lockchannel",
        description="Lock the current channel (optionally for a set time)."
    )
    @app_commands.describe(duration="Optional duration (e.g. 30m, 1h, 2d)")
    async def lockchannel(
        self,
        interaction: discord.Interaction,
        duration: str = None
    ):
        # ❌ Hard deny role
        if self.has_deny_role(interaction.user):
            return await interaction.response.send_message(
                "🚫 You are not allowed to use this command.",
                ephemeral=True
            )

        # 🔐 Jr Mod+ check
        if not self.is_jrmod_or_higher(interaction.user):
            return await interaction.response.send_message(
                "🚫 You do not have permission to lock channels. (Jr Mod+ only)",
                ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        try:
            self.locked_channels.add(interaction.channel.id)

            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                send_messages=False
            )

            member_role = interaction.guild.get_role(DISCORD_MEMBER_ROLE_ID)
            if member_role:
                await interaction.channel.set_permissions(
                    member_role,
                    send_messages=False
                )

            for role_id in HELPER_AND_HIGHER_ROLE_IDS:
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.channel.set_permissions(
                        role,
                        send_messages=True
                    )

            log_channel = await self.bot.fetch_channel(BOT_LOGS_CHANNEL_ID)

            if duration:
                seconds = parse_duration(duration)
                if not seconds:
                    return await interaction.followup.send(
                        "❌ Invalid duration format. Use `30m`, `1h`, `2d`, etc."
                    )

                await interaction.followup.send(
                    f"🔒 Locked {interaction.channel.mention} for `{duration}`."
                )
                await log_channel.send(
                    f"🔒 {interaction.user.mention} locked {interaction.channel.mention} for `{duration}`."
                )

                await asyncio.sleep(seconds)
                await self._unlock(
                    interaction.channel,
                    auto=True,
                    actor=interaction.user,
                    duration=duration
                )
            else:
                await interaction.followup.send(
                    f"🔒 Locked {interaction.channel.mention} indefinitely."
                )
                await log_channel.send(
                    f"🔒 {interaction.user.mention} locked {interaction.channel.mention} indefinitely."
                )

        except Exception as e:
            await interaction.followup.send(f"❌ Lock failed: {e}")

    # -------------------------------
    # 🔓 Unlock Channel
    # -------------------------------

    @app_commands.command(
        name="unlockchannel",
        description="Unlock the current channel for @everyone."
    )
    async def unlockchannel(self, interaction: discord.Interaction):
        # ❌ Hard deny role
        if self.has_deny_role(interaction.user):
            return await interaction.response.send_message(
                "🚫 You are not allowed to use this command.",
                ephemeral=True
            )

        # 🔐 Jr Mod+ check
        if not self.is_jrmod_or_higher(interaction.user):
            return await interaction.response.send_message(
                "🚫 You do not have permission to unlock channels. (Jr Mod+ only)",
                ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        try:
            await self._unlock(
                interaction.channel,
                auto=False,
                actor=interaction.user
            )
            await interaction.followup.send(
                f"🔓 Unlocked {interaction.channel.mention}."
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Unlock failed: {e}")

    # -------------------------------
    # 🔓 Internal Unlock Logic
    # -------------------------------

    async def _unlock(
        self,
        channel: discord.TextChannel,
        auto: bool = False,
        actor: discord.Member | None = None,
        duration: str | None = None
    ):
        try:
            self.locked_channels.discard(channel.id)

            await channel.set_permissions(
                channel.guild.default_role,
                send_messages=None
            )

            member_role = channel.guild.get_role(DISCORD_MEMBER_ROLE_ID)
            if member_role:
                await channel.set_permissions(member_role, overwrite=None)

            for role_id in HELPER_AND_HIGHER_ROLE_IDS:
                role = channel.guild.get_role(role_id)
                if role:
                    await channel.set_permissions(role, overwrite=None)

            log_channel = await self.bot.fetch_channel(BOT_LOGS_CHANNEL_ID)
            if auto:
                await log_channel.send(
                    f"🔓 Auto-unlocked {channel.mention} after `{duration}` "
                    f"(locked by {actor.mention})."
                )
            else:
                await log_channel.send(
                    f"🔓 {actor.mention} manually unlocked {channel.mention}."
                )

        except Exception as e:
            print(f"❌ Unlock failed: {e}")

    # -------------------------------
    # 📋 Show Locked Channels
    # -------------------------------

    @app_commands.command(
        name="showlockedchannels",
        description="Show all currently locked channels."
    )
    async def showlockedchannels(self, interaction: discord.Interaction):
        # ❌ Hard deny role
        if self.has_deny_role(interaction.user):
            return await interaction.response.send_message(
                "🚫 You are not allowed to use this command.",
                ephemeral=True
            )

        # 🔐 Jr Mod+ check
        if not self.is_jrmod_or_higher(interaction.user):
            return await interaction.response.send_message(
                "🚫 You do not have permission to view locked channels. (Jr Mod+ only)",
                ephemeral=True
            )

        if not self.locked_channels:
            return await interaction.response.send_message(
                "🔓 No channels are currently locked.",
                ephemeral=True
            )

        channels = [
            interaction.guild.get_channel(cid)
            for cid in self.locked_channels
        ]
        visible = [ch.mention for ch in channels if ch]

        await interaction.response.send_message(
            "🔒 Currently locked channels:\n" + "\n".join(visible),
            ephemeral=True
        )

# -------------------------------
# ⚙️ Setup
# -------------------------------

async def setup(bot):
    await bot.add_cog(ChannelLock(bot))