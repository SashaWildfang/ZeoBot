import discord
from discord.ext import commands
from discord import app_commands

# -------------------------------
# ⚙️ Role Config
# -------------------------------

MOD_AND_HIGHER_ROLE_IDS = {
    1358472557862457537,   # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

DENY_ROLE_ID = 1431581220386373712  # ❌ Hard deny role (overrides everything)

# -------------------------------
# 🐢 Slowmode Cog
# -------------------------------

class Slowmode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -------------------------------
    # 🔐 Permission Helpers
    # -------------------------------

    def has_deny_role(self, member: discord.Member) -> bool:
        return any(role.id == DENY_ROLE_ID for role in member.roles)

    def is_mod_or_higher(self, member: discord.Member) -> bool:
        return any(role.id in MOD_AND_HIGHER_ROLE_IDS for role in member.roles)

    # -------------------------------
    # ⏱️ Set Slowmode
    # -------------------------------

    @app_commands.command(
        name="slowmode",
        description="Set slowmode delay in this channel."
    )
    @app_commands.describe(seconds="Number of seconds to set slowmode to.")
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: int
    ):
        # ❌ Hard deny role
        if self.has_deny_role(interaction.user):
            return await interaction.response.send_message(
                "🚫 You are not allowed to use this command.",
                ephemeral=True
            )

        # 🔐 Mod+ check
        if not self.is_mod_or_higher(interaction.user):
            return await interaction.response.send_message(
                "🚫 You do not have permission to use this command. (Mod+ only)",
                ephemeral=True
            )

        try:
            await interaction.channel.edit(
                slowmode_delay=seconds,
                reason=f"Set by {interaction.user}"
            )
            await interaction.response.send_message(
                f"⏱️ Slowmode set to `{seconds}` seconds in {interaction.channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to edit this channel.",
                ephemeral=True
            )

    # -------------------------------
    # 🧹 Clear Slowmode
    # -------------------------------

    @app_commands.command(
        name="clearslowmode",
        description="Remove any slowmode from this channel."
    )
    async def clearslowmode(self, interaction: discord.Interaction):
        # ❌ Hard deny role
        if self.has_deny_role(interaction.user):
            return await interaction.response.send_message(
                "🚫 You are not allowed to use this command.",
                ephemeral=True
            )

        # 🔐 Mod+ check
        if not self.is_mod_or_higher(interaction.user):
            return await interaction.response.send_message(
                "🚫 You do not have permission to use this command. (Mod+ only)",
                ephemeral=True
            )

        try:
            await interaction.channel.edit(
                slowmode_delay=0,
                reason=f"Cleared by {interaction.user}"
            )
            await interaction.response.send_message(
                f"✅ Slowmode cleared in {interaction.channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to edit this channel.",
                ephemeral=True
            )

# -------------------------------
# ⚙️ Setup
# -------------------------------

async def setup(bot):
    await bot.add_cog(Slowmode(bot))
