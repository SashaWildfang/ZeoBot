import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection

SETTINGS_CHANNEL_ID = 1382735420747419761

class GetSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def settings_col(self):
        db = get_connection()
        return db["settings"]

    @app_commands.command(name="settings", description="View your current user settings.")
    async def settings(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        col = self.settings_col()

        try:
            # FIX: Added 'await' before col.find_one
            doc = await col.find_one(
                {"discordId": user_id},
                {"allowHugs": 1, "allowBoop": 1, "dailyReminder": 1, "milestoneNotify": 1}
            )

            allow_hugs = doc.get("allowHugs") if doc else None
            allow_boop = doc.get("allowBoop") if doc else None
            daily_reminder = doc.get("dailyReminder") if doc else None
            milestone_notify = doc.get("milestoneNotify") if doc else None

            def format_bool(val):
                if val is None:
                    return "Not Set ❓"
                return "Enabled ✅" if val else "Disabled ❌"

            embed = discord.Embed(
                title="🔧 Your Settings",
                description=f"To change these, visit <#{SETTINGS_CHANNEL_ID}>.",
                color=discord.Color.purple()
            )

            embed.add_field(name="Hugs", value=format_bool(allow_hugs), inline=True)
            embed.add_field(name="Boops", value=format_bool(allow_boop), inline=True)
            embed.add_field(name="Daily Reminders", value=format_bool(daily_reminder), inline=True)
            embed.add_field(name="Milestone Alerts", value=format_bool(milestone_notify), inline=True)
            embed.set_footer(text="If a setting is not set, it is treated as enabled by default.")

            await interaction.response.send_message(embed=embed, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message("❌ Error fetching your settings.", ephemeral=True)
            print(f"❌ Error in /settings: {e}")

async def setup(bot):
    await bot.add_cog(GetSettings(bot))
    print("✅ Loaded GetSettings Cog (Mongo Edition)")