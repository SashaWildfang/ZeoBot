import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from db.punishments import log_punishment
from db.database import get_connection

# ==========================================
# CONFIGURATION
# ==========================================
STAFF_TEAM_ROLE_ID = 1358470109965979859
UNVERIFIED_ROLE_ID = 1358469817191104716
BOT_LOGS_CHANNEL_ID = 1360344042705256660

BAN_APPEAL_LINK = "https://forms.gle/AgbY3XDFFVmVTjab9"
REJOIN_LINK = "https://discord.gg/SYm3Z7fr7c"

# ==========================================
# CONFIRMATION UI VIEW
# ==========================================
class ConfirmMassKick(discord.ui.View):
    def __init__(self, invoker: discord.Member, targets: list[discord.Member], reason: str, silent: bool, bot: commands.Bot, dry_run: bool):
        super().__init__(timeout=120)
        self.invoker = invoker
        self.targets = targets
        self.reason = reason
        self.silent = silent
        self.bot = bot
        self.dry_run = dry_run

    # Prevent other staff from clicking the buttons
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.invoker:
            await interaction.response.send_message("❌ Only the command runner can use these buttons.", ephemeral=True)
            return False
        return True

    def disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Execute Kick", style=discord.ButtonStyle.danger, emoji="👢")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_all()
        await interaction.response.edit_message(content="⏳ **Processing...** Please wait.", view=self)

        # Handle Dry Run
        if self.dry_run:
            members_text = "\n".join(f"• {m.mention} (`{m.id}`)" for m in self.targets[:20])
            if len(self.targets) > 20:
                members_text += f"\n*...and {len(self.targets) - 20} more.*"
            return await interaction.followup.send(f"📊 **DRY RUN:** Would have kicked **{len(self.targets)}** members:\n{members_text}", ephemeral=True)

        kicked, failed = [], []

        # Execution Loop
        for member in self.targets:
            try:
                # 1. Log to DB
                pid = log_punishment(member.id, self.invoker.id, "kick_unverified", self.reason, extra_info="Mass Unverified Kick")

                # 2. Try DMing the user (Silently ignore if their DMs are closed)
                try:
                    await member.send(
                        f"👢 You were kicked from **{interaction.guild.name}**.\n"
                        f"📝 **Reason:** {self.reason} (ID: `{pid}`)\n\n"
                        f"🔗 **Appeal:** {BAN_APPEAL_LINK}\n🔗 **Rejoin:** {REJOIN_LINK}"
                    )
                except discord.Forbidden:
                    pass 

                # 3. Handle silent mode
                if self.silent and (leave_cog := self.bot.get_cog("MemberLeave")):
                    leave_cog.mark_silent(member.id)

                # 4. Kick them
                await member.kick(reason=f"[Mass Kick by {self.invoker.name}] {self.reason}")
                kicked.append(f"{member.name} (`{member.id}`)")
                
                # Protect the bot from rate limits
                await asyncio.sleep(0.5) 

            except Exception as e:
                failed.append(f"{member.name} (Error: {e})")

        # Create Final Log Embed
        log_embed = discord.Embed(
            title="👢 Mass Kick Complete",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="Invoker", value=self.invoker.mention, inline=True)
        log_embed.add_field(name="Total Kicked", value=str(len(kicked)), inline=True)
        log_embed.add_field(name="Failed", value=str(len(failed)), inline=True)

        # Show a sample of who was kicked/failed so the embed doesn't break character limits
        if kicked:
            log_embed.add_field(name="Kicked (Sample)", value="\n".join(kicked[:10]) + ("\n..." if len(kicked) > 10 else ""), inline=False)
        if failed:
            log_embed.add_field(name="Failures (Sample)", value="\n".join(failed[:10]) + ("\n..." if len(failed) > 10 else ""), inline=False)

        # Send Log
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=log_embed)

        await interaction.followup.send(f"✅ Mass kick finished. **{len(kicked)}** kicked, **{len(failed)}** failed.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_all()
        await interaction.response.edit_message(content="✅ **Operation Cancelled.**", embed=None, view=self)

# ==========================================
# COMMAND COG
# ==========================================
class KickUnverified(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="kickunverified", description="(Staff Team) Mass kick members holding ONLY the Unverified role.")
    @app_commands.describe(
        reason="Reason for kick", 
        silent="Hide leave logs?", 
        dry_run="Simulate who would be kicked without actually doing it?"
    )
    async def kickunverified(self, interaction: discord.Interaction, reason: str = "Unverified cleanup", silent: bool = False, dry_run: bool = False):
        
        # 1. Staff Team Check
        if not any(r.id == STAFF_TEAM_ROLE_ID for r in interaction.user.roles):
            return await interaction.response.send_message("❌ You need the **Staff Team** role to use this.", ephemeral=True)

        # 2. Gather Unverified Users
        # A user holding strictly "Unverified" only has 2 roles: @everyone and Unverified.
        targets = [
            m for m in interaction.guild.members 
            if len(m.roles) == 2 and UNVERIFIED_ROLE_ID in [r.id for r in m.roles]
        ]

        if not targets:
            return await interaction.response.send_message("✅ No strictly unverified members found to kick.", ephemeral=True)

        # 3. Confirmation Menu
        embed = discord.Embed(
            title="⚠️ Mass Kick Confirmation",
            description=f"You are about to kick **{len(targets)}** strictly unverified members.\n\n**Reason:** {reason}\n**Dry Run:** {dry_run}",
            color=discord.Color.brand_red()
        )

        await interaction.response.send_message(
            embed=embed, 
            view=ConfirmMassKick(interaction.user, targets, reason, silent, self.bot, dry_run), 
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(KickUnverified(bot))