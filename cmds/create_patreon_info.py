import discord
from discord.ext import commands
from discord import app_commands

PATREON_INFO_CHANNEL_ID = 1362502211220930581

class PatreonInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_patreon_info", description="Post Patreon tier info embeds.")
    async def create_patreon_info(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(PATREON_INFO_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Could not find the Patreon info channel.", ephemeral=True)
            return

        # Intro Embed
        intro = discord.Embed(
            title="🎉 Support Kitty Kingdom on Patreon!",
            description=(
                "Thank you for considering supporting **Kitty Kingdom**! 🐾\n\n"
                "Becoming a patron not only helps keep our community running, but it also unlocks exclusive perks, roles, boosts, and monthly <:leaf:1524758896659660831> rewards!\n\n"
                "All supporters gain access to custom Discord roles, private lounges, powerful XP bonuses, and **Dating Profile Boosts**!\n\n"
                "**What is a Dating Profile Boost?**\n"
                "If you use our `/profile` system, Patrons receive a higher \"Profile Weight.\" This means the algorithm will prioritize your profile, drastically increasing your chances of being shown off in the Hourly Featured Matches feed!\n\n"
                "The more you support, the more you unlock — from giveaways and custom commands to profile customization and top-tier recognition!\n\n"
                "👉 [Click here to view our Patreon tiers and sign up](https://www.patreon.com/c/thekittykingdom/membership)\n\n"
                "You can also type `/patreon` anytime to view the link."
            ),
            color=discord.Color.blurple()
        )
        intro.set_footer(text="Your support makes a huge difference. Thank you!")

        # $5 Tier
        tier5 = discord.Embed(
            title="✨ Royal Kitten — $5/mo",
            color=discord.Color.from_str("#1dadd1")
        )
        tier5.add_field(name="Perks", value=(
            "• Access to exclusive Patreon-only channels\n"
            "• Gain 1,000 <:leaf:1524758896659660831> Leaves at the start of each month\n"
            "• Enjoy a +10% XP gain boost across all server activity\n"
            "• **1.5x Dating Profile Weight** (Appear 2.5x more often in hourly intros)\n"
            "• Recognition on our Public Thank-You Board\n"
            "• Receive 5% off all items in the `/store`\n"
            "• Have priority when participating in polls and community votes\n\n"
            "_Includes Discord-linked Patreon benefits._"
        ), inline=False)

        # $10 Tier
        tier10 = discord.Embed(
            title="🌿 Kitten Guardian — $10/mo",
            color=discord.Color.from_str("#19cd8e")
        )
        tier10.add_field(name="Perks", value=(
            "• All perks from <@&1362102163693633818> tier\n"
            "• Gain 2,000 <:leaf:1524758896659660831> Leaves at the start of each month\n"
            "• +20% XP gain to help you level up faster\n"
            "• **2.0x Dating Profile Weight** (Appear 3x as often in hourly intros)\n"
            "• 10% discount in the `/store` for all items\n"
            "• Guaranteed entry into server giveaways\n"
            "• Access to exclusive shop items only for patrons\n"
            "• One custom emoji slot (redeemable via ticket)\n"
            "• One custom command (redeemable via ticket)\n"
            "• Recognition on our Thank-You Board & poll influence\n\n"
            "_Includes Discord-linked Patreon benefits._"
        ), inline=False)

        # $20 Tier
        tier20 = discord.Embed(
            title="🔥 Legendary Neko — $20/mo",
            color=discord.Color.from_str("#ff980a")
        )
        tier20.add_field(name="Perks", value=(
            "• All perks from <@&1362502662721114245> tier\n"
            "• Gain 4,000 <:leaf:1524758896659660831> Leaves at the start of each month\n"
            "• Boost your XP gain by +40% server-wide\n"
            "• **2.5x Dating Profile Weight** (Appear 3.5x as often in hourly intros)\n"
            "• 15% discount on every item in the `/store`\n"
            "• Entry into giveaways with an additional bonus ticket\n"
            "• Special access to ultra-exclusive shop rewards\n"
            "• Request a custom role color to personalize your name (via ticket)\n"
            "• 3 custom emoji slots and up to 3 custom commands (via ticket)\n"
            "• Premium visibility on Thank-You Board and poll priority\n\n"
            "_Includes all Discord-linked Patreon features._"
        ), inline=False)

        await channel.send(embed=intro)
        await channel.send(embed=tier5)
        await channel.send(embed=tier10)
        await channel.send(embed=tier20)
        await interaction.response.send_message("✅ Patreon info has been posted.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PatreonInfo(bot))
    print("Loaded PatreonInfo Cog")