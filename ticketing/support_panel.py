import discord
from discord.ext import commands
from ticketing.ui_buttons import SupportTicketButton

# The channel ID where you want to post the support panel
SUPPORT_PANEL_CHANNEL_ID = 1495841072423899276

class SupportPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="create_support_panel", description="Post the General Support panel")
    @discord.app_commands.default_permissions(administrator=True)
    async def create_support_panel(self, interaction: discord.Interaction):
        if interaction.channel_id != SUPPORT_PANEL_CHANNEL_ID:
            return await interaction.response.send_message(
                f"❌ This command must be used in <#{SUPPORT_PANEL_CHANNEL_ID}>.", 
                ephemeral=True
            )

        embed = discord.Embed(
            title="🎫 Kitty Kingdom | Support Tickets",
            description=(
                "Need assistance or have a question for our team? You've come to the right place! "
                "Open a ticket below and a member of our staff ladder will assist you as soon as possible.\n\n"
                
                "🛠️ **What can we help with?**\n"
                "• Reporting rule violations or member issues.\n"
                "• General questions regarding server features.\n"
                "• Technical issues with roles or bots.\n"
                "• Inquiries about server partnerships or events.\n\n"
                
                "⚠️ **Important Notes:**\n"
                "• For NSFW access, please go to <#1358485673991999721>\n"
                "• To apply for staff, please go to <#1495830924926128148>\n\n"
                "**Click the button below to open a support ticket!**"
            ),
            color=discord.Color.blue()
        )
        
        embed.set_thumbnail(url="https://i.imgur.com/6EhF8A4.png")

        await interaction.channel.send(embed=embed, view=SupportTicketButton())
        await interaction.response.send_message("✅ Support panel created successfully.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SupportPanel(bot))