import discord
from discord.ext import commands
from discord import app_commands

NITRO_INFO_CHANNEL_ID = 1358485493020496004
NITRO_ROLE_ID = 1360260086500561237

class NitroInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_nitro_info", description="Post or update Nitro Booster perk information.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create_nitro_info(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        channel = guild.get_channel(NITRO_INFO_CHANNEL_ID)
        if not channel:
            await interaction.followup.send("❌ Could not find the Nitro info channel.", ephemeral=True)
            return

        nitro_role = guild.get_role(NITRO_ROLE_ID)
        nitro_mention = nitro_role.mention if nitro_role else "Nitro Booster"

        embed = discord.Embed(
            title="🚀 Nitro Booster Perks",
            description=(
                f"Thank you for boosting Kitty Kingdom! Boosting grants you the {nitro_mention} role and a variety of awesome benefits just for supporting the server."
            ),
            color=discord.Color.from_str("#393ed4")
        )

        embed.add_field(name="🎁 Perks You Receive", value=(
            f"• Access to the {nitro_mention} role\n"
            "• 15% more ✨\n"
            "• 15% more <:leaf:1524758896659660831>\n"
            "• 500 <:leaf:1524758896659660831> at the start of each month\n"
            "• Immediate 750 <:leaf:1524758896659660831> upon boosting (one-time)\n"
            "• Use of external emojis and stickers\n"
            "• Auto-access to media permissions and reaction usage\n"
            "• Streaks enabled in `/daily`\n"
            "• Exclusive Nitro items in `/store`\n"
            "• Unlimited Likes on Dating Profiles\n"  
            "• View full Dating Profile like history\n" 
            "• **1.0x Dating Profile Weight** (Appear 2x more often in hourly intros)\n" 
            "• **Spin the slot machine up to 25 times at once with `/slots spin`**\n"
            "• **Unlimited Daily Scratch-offs & exclusive Black Diamond ticket access**\n"
            "• Monthly shoutout recognizing your contribution!"
        ), inline=False)

        embed.set_footer(text="Boosting helps our server grow and unlocks amazing perks for you and everyone!")

        # Check for existing bot embed in the channel
        existing = [m async for m in channel.history(limit=10) if m.author.id == self.bot.user.id and m.embeds]
        if existing:
            try:
                await existing[0].edit(embed=embed)
                await interaction.followup.send("🔁 Nitro Booster info embed was updated.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to update existing embed: {e}", ephemeral=True)
                return

        # Otherwise send a new embed
        await channel.send(embed=embed)
        await interaction.followup.send("✅ Nitro Booster info has been posted!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(NitroInfo(bot))