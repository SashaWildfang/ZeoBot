import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import pytz  # To handle the timezone rollover issue
from db.database import get_connection

VC_ROLE_ID = 1503200525527810269
# Change this to your preferred timezone (e.g., 'US/Mountain', 'US/Eastern', 'UTC')
LOCAL_TZ = pytz.timezone('US/Mountain') 

class VCSignatureModal(discord.ui.Modal, title="VC Terms Agreement"):
    discord_name = discord.ui.TextInput(
        label="Your Discord Name:",
        style=discord.TextStyle.short,
        placeholder="Type your Discord username...",
        required=True,
        max_length=50
    )

    date_field = discord.ui.TextInput(
        label="Today's Date (M/D/YEAR):",
        style=discord.TextStyle.short,
        placeholder="Loading date...",
        required=True,
        max_length=20
    )

    agree_field = discord.ui.TextInput(
        label="Type 'I agree' below to accept terms:",
        style=discord.TextStyle.short,
        placeholder="I agree",
        required=True,
        max_length=50
    )

    def __init__(self):
        super().__init__()
        # Get local time instead of UTC to fix the "tomorrow" bug
        now_local = datetime.now(LOCAL_TZ)
        dynamic_date = f"{now_local.month}/{now_local.day}/{now_local.year}"
        self.date_field.placeholder = f"e.g. {dynamic_date}"

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Date Validation (Using Local Time)
        now_local = datetime.now(LOCAL_TZ)
        expected_date = f"{now_local.month}/{now_local.day}/{now_local.year}"
        expected_date_padded = now_local.strftime("%m/%d/%Y") 

        user_date = self.date_field.value.strip()
        
        if user_date not in [expected_date, expected_date_padded]:
            return await interaction.response.send_message(
                f"❌ **Signature Rejected:** Invalid date format or incorrect date.\n"
                f"Please try again and use today's date: **{expected_date}**", 
                ephemeral=True
            )

        # 2. "I agree" Validation
        if self.agree_field.value.strip().lower() != "i agree":
            return await interaction.response.send_message(
                "❌ **Signature Rejected:** You must type exactly `I agree` in the final box.", 
                ephemeral=True
            )

        # 3. Process the Signature
        db = get_connection()
        vc_signatures = db["vc_signatures"]

        user = interaction.user
        role = interaction.guild.get_role(VC_ROLE_ID)

        # Log to Database
        doc = {
            "discordId": user.id,
            "username": str(user),
            "signed_name": self.discord_name.value.strip(),
            "signed_date": user_date,
            "timestamp": datetime.now(timezone.utc) # Actual DB entry in UTC
        }
        await vc_signatures.insert_one(doc)

        # Give Role
        if role:
            try:
                await user.add_roles(role, reason="Signed VC terms and conditions.")
                await interaction.response.send_message("✅ You have signed the agreement and received VC access. Have fun!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I do not have permission to give you the VC role.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ VC role not found. Contact an admin.", ephemeral=True)

class VCAcceptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="I Accept these terms and give up my rights", style=discord.ButtonStyle.danger, custom_id="vc_accept_persistent_button", emoji="📝")
    async def accept_vc_terms(self, interaction: discord.Interaction, button: discord.ui.Button):
        if any(role.id == VC_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("You already have VC access!", ephemeral=True)
            return
        
        await interaction.response.send_modal(VCSignatureModal())


class VCEmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vc_setup", description="Spawns the VC Terms and Conditions Embed")
    @app_commands.default_permissions(administrator=True)
    async def vc_setup(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Voice Channel Terms & Conditions",
            description=(
                "Welcome to the Voice Channels! Before you join, please read the following rules and disclaimers carefully.\n\n"
                "**⚠️ Moderation Disclaimer & Hearsay**\n"
                "Staff are **not responsible** for anything said within Voice Channels. Verbal conversations are hearsay (he said, she said), and we **cannot properly moderate VC** without hard proof. "
                "If you choose to join a VC, you are doing so **at your own risk**.\n\n"
                "**Earn Rewards for Chilling!**\n"
                "We have a brand new rewards system for active VC users!\n"
                "• **Stay at least 5 minutes** to start earning rewards.\n"
                "• Earn **XP ✨ and Leaves <:leaf:1524758896659660831>** automatically while you hang out.\n"
                "• Earn your spot on the `/leaderboard` for total and monthly VC time.\n\n"
                "**📝 Agreement**\n"
                "To gain access to our Voice Channels, you must click the button below and digitally sign stating that you have read these rules and accept our moderation limitations."
            ),
            color=discord.Color.from_str("#0debd8")
        )

        await interaction.channel.send(embed=embed, view=VCAcceptView())
        await interaction.response.send_message("VC Embed posted successfully.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VCEmbedCog(bot))