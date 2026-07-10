import discord
from discord.ext import commands
from discord import app_commands, Interaction
from db.database import get_connection

SETTINGS_CHANNEL_ID = 1382735420747419761
NITRO_ROLE_ID = 1360260086500561237

# ==================================================
# 🧱 Base Mongo Utility
# ==================================================

def settings_collection():
    db = get_connection()
    return db["settings"]

async def update_user_setting(interaction: Interaction, field: str, value: bool):
    """Reusable Mongo update helper for all setting buttons."""
    user_id = interaction.user.id
    try:
        col = settings_collection()
        # FIX: Added 'await' here. Async MongoDB queries must be awaited!
        await col.update_one(
            {"discordId": user_id},
            {"$set": {field: value}},
            upsert=True
        )
        await interaction.response.send_message(
            f"✅ **{field.replace('_', ' ').title()}** {'enabled' if value else 'disabled'}.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message("❌ Database error while saving your setting.", ephemeral=True)
        print(f"❌ Error updating {field} for {user_id}: {e}")

# ==================================================
# 🎯 Individual Setting Views
# ==================================================

class HugSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enable Hugs", style=discord.ButtonStyle.success, custom_id="hug_enable")
    async def enable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "allowHugs", True)

    @discord.ui.button(label="Disable Hugs", style=discord.ButtonStyle.danger, custom_id="hug_disable")
    async def disable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "allowHugs", False)

class BoopSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enable Boops", style=discord.ButtonStyle.success, custom_id="boop_enable")
    async def enable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "allowBoop", True)

    @discord.ui.button(label="Disable Boops", style=discord.ButtonStyle.danger, custom_id="boop_disable")
    async def disable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "allowBoop", False)

class DailyReminderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def verify_nitro(self, interaction: Interaction) -> bool:
        if not any(role.id == NITRO_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ Only Nitro Boosters can use the Daily Reminder feature.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Enable Daily Reminder", style=discord.ButtonStyle.success, custom_id="daily_enable")
    async def enable(self, interaction: Interaction, button: discord.ui.Button):
        if await self.verify_nitro(interaction):
            await update_user_setting(interaction, "dailyReminder", True)

    @discord.ui.button(label="Disable Daily Reminder", style=discord.ButtonStyle.danger, custom_id="daily_disable")
    async def disable(self, interaction: Interaction, button: discord.ui.Button):
        if await self.verify_nitro(interaction):
            await update_user_setting(interaction, "dailyReminder", False)

class MilestoneNotifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enable Milestone Notices", style=discord.ButtonStyle.success, custom_id="milestone_enable")
    async def enable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "milestoneNotify", True)

    @discord.ui.button(label="Disable Milestone Notices", style=discord.ButtonStyle.danger, custom_id="milestone_disable")
    async def disable(self, interaction: Interaction, button: discord.ui.Button):
        await update_user_setting(interaction, "milestoneNotify", False)

# ==================================================
# ⚙️ Settings Command
# ==================================================

class UserSettings(commands.Cog):
    """Allows staff to post or refresh the user settings menu."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="createsettings", description="Post or update the interactive settings menu.")
    @app_commands.default_permissions(manage_guild=True) # Makes the command show up only for staff in the UI
    async def createsettings(self, interaction: discord.Interaction):
        """Create or update the settings embed menu in the configured channel."""
        
        # Defer the response since deleting and sending messages takes a moment
        await interaction.response.defer(ephemeral=True)

        channel = interaction.guild.get_channel(SETTINGS_CHANNEL_ID)
        if not channel:
            return await interaction.followup.send("❌ Settings channel not found.", ephemeral=True)

        # Build embeds
        general_embed = discord.Embed(
            title="🛠️ User Settings Overview",
            description=(
                "Customize your experience in Kitty Kingdom.\n"
                "Some settings are exclusive to Nitro Boosters or Patreon supporters.\n"
                "See <#1358485493020496004> or <#1362502211220930581> for details."
            ),
            color=discord.Color.blurple()
        )

        hug_embed = discord.Embed(
            title="🤗 Allow Hugs",
            description="Toggle whether other members can hug you using `/hug`.",
            color=discord.Color.teal()
        )

        boop_embed = discord.Embed(
            title="🐾 Allow Boops",
            description="Toggle whether other members can boop you using `/boop`.",
            color=discord.Color.teal()
        )

        milestone_embed = discord.Embed(
            title="🏆 Milestone Notifications",
            description="Toggle whether to be notified when you reach message milestones (100, 500, 1000...).",
            color=discord.Color.teal()
        )

        daily_embed = discord.Embed(
            title="📅 Daily Streak Reminder (Nitro Only)",
            description="Toggle reminders when your `/daily` streak is about to expire.",
            color=discord.Color.orange()
        )

        try:
            # Safely clear out old bot messages in the settings channel to avoid duplicates or misordering
            async for msg in channel.history(limit=20):
                if msg.author.id == self.bot.user.id:
                    await msg.delete()

            # Send everything fresh in the exact desired order
            await channel.send(embed=general_embed)
            await channel.send(embed=hug_embed, view=HugSettingsView())
            await channel.send(embed=boop_embed, view=BoopSettingsView())
            await channel.send(embed=milestone_embed, view=MilestoneNotifyView())
            await channel.send(embed=daily_embed, view=DailyReminderView())

            await interaction.followup.send("✅ Settings menu refreshed successfully.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to post or update settings: `{e}`", ephemeral=True)
            print(f"❌ Error updating settings UI: {e}")


# ==================================================
# 🧩 Cog Setup
# ==================================================

async def setup(bot):
    await bot.add_cog(UserSettings(bot))
