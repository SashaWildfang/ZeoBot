import asyncio
import discord
import sys
from discord import app_commands
from discord.ext import commands
from datetime import datetime

# ===== Configuration =====
ALLOWED_ROLES = {
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

BOT_LOGS_CHANNEL_ID = 1360344042705256660

class ConfirmRestartView(discord.ui.View):
    def __init__(self, invoker: discord.Member, cog, reason: str):
        super().__init__(timeout=30)
        self.invoker = invoker
        self.cog = cog
        self.reason = reason

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ This is not your prompt.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Restart", style=discord.ButtonStyle.danger, emoji="🔄")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="⚙️ System signal sent. Shutting down...", view=self)
        
        await self.cog.execute_shutdown(interaction, self.invoker, self.reason)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="❎ Restart aborted.", view=None)

class Restart(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_authorized(self, member: discord.Member) -> bool:
        return any(role.id in ALLOWED_ROLES for role in member.roles) or member.guild_permissions.administrator

    async def execute_shutdown(self, interaction: discord.Interaction, invoker: discord.Member, reason: str):
        # 1. Log to Channel
        channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🔄 Manual Restart Initiated",
                description=f"**Staff:** {invoker.mention}\n**Reason:** {reason}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await channel.send(embed=embed)

        # 2. Final Message
        await interaction.followup.send("👋 Zeobot is going offline for restart. See you in a few seconds!", ephemeral=True)
        
        # 3. Clean Exit
        print(f"SHUTDOWN: Restarted by {invoker.name} for: {reason}")
        await self.bot.close()
        sys.exit(0) # systemd will see this exit and restart the bot immediately

    @app_commands.command(name="restart", description="Cleanly restarts the bot via systemd.")
    async def restart(self, interaction: discord.Interaction, reason: str = "No reason provided"):
        if not self._is_authorized(interaction.user):
            return await interaction.response.send_message("🚫 Admin+ Only.", ephemeral=True)

        view = ConfirmRestartView(interaction.user, self, reason)
        await interaction.response.send_message(
            content=f"⚠️ **Warning:** This will kill the current process. Systemd will attempt to reboot the bot immediately.\n**Reason:** {reason}",
            view=view,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Restart(bot))