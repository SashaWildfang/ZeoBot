import discord
from discord import app_commands
from discord.ext import commands
from ticketing.ui_buttons import StaffApplyButton

# The channel ID for #apply-staff
STAFF_CHANNEL_ID = 1495830924926128148

class StaffPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="create_staff_panel", description="Post the Staff Application panel")
    @discord.app_commands.default_permissions(administrator=True)
    async def create_staff_panel(self, interaction: discord.Interaction):
        if interaction.channel_id != STAFF_CHANNEL_ID:
            return await interaction.response.send_message(f"❌ This command must be used in <#{STAFF_CHANNEL_ID}>.", ephemeral=True)

        embed = discord.Embed(
            title="🛡️ Kitty Kingdom | Staff Applications",
            description=(
                "We are looking for dedicated individuals to join our team! "
                "Being part of the staff means helping maintain the kingdom as a safe and fun place for everyone.\n\n"
                
                "⬆️ **The Staff Ladder**\n"
                "Our team follows a structured growth path:\n"
                "• <@&1358470318087340342> (Entry Level)\n"
                "• <@&1358472557862457537>\n"
                "• <@&1358472532222808126>\n"
                "• <@&1358472588430676018>\n"
                "• <@&1358472511133585564>\n\n"
                
                "📝 **Your Starting Role: Helper**\n"
                "As a Helper, your primary focus is community support. You will:\n"
                "• **Help Members:** Assist with general questions about the server and the furry fandom.\n"
                "• **Verifications:** Help with quick user verification approvals/denials to keep the queue moving.\n"
                "• **Question Support:** Answer any questions users may have pertaining to the server.\n\n"
                
                "✅ **Requirements**\n"
                "• Must be **18+** years of age.\n"
                "• Must have the <@&1358469974552870913> role.\n"
                "  *(If you are not verified, go to <#1358485673991999721> to verify first)*\n"
                "• Account must be at least **30 days old**.\n"
                "• Must be in the server for a minimum of **30 days** (to get a feel for the community).\n"
                "• No recent warns/bans (30-day clean record).\n"
                "• A helpful attitude and high activity levels.\n\n"
                
                "⚠️ **Important Disclaimer**\n"
                "This is a **strictly voluntary** position. By applying, you understand that this is not a paid job and there is no financial compensation. You are donating your time to support the community.\n\n"
                
                "*Click the button below to start your application.*"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url="https://i.imgur.com/6EhF8A4.png") 

        await interaction.channel.send(embed=embed, view=StaffApplyButton())
        await interaction.response.send_message("✅ Staff application panel created.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(StaffPanel(bot))