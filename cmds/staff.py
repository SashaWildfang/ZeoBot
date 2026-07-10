import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from zoneinfo import ZoneInfo

# Role name → (role ID, emoji)
STAFF_ROLE_INFO = [
    ("Owner", 1358473248534167663, "👑"),
    ("Sr Admin", 1358472635234779207, "⭐"),
    ("Admin", 1358472511133585564, "🛡️"),
    ("Sr Mod", 1358472588430676018, "🟣"),
    ("Mod", 1358472532222808126, "🔵"),
    ("Jr Mod", 1358472557862457537, "🟢"),
    ("Helper", 1358470318087340342, "👋")
]

class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staff", description="View a list of all current staff members.")
    async def staff(self, interaction: discord.Interaction):
        guild = interaction.guild
        eastern = ZoneInfo("America/New_York")
        current_time = datetime.now(eastern).strftime("%B %d, %Y at %I:%M %p %Z")

        embed = discord.Embed(
            title="📋 Kitty Kingdom Staff",
            description=(
                "Here's a list of all current staff members (✅ = Online, ❌ = Offline):\n\n\n"
            ),
            color=discord.Color.from_str("#d69238")
        )

        online_staff_mentions = []

        for role_name, role_id, emoji in STAFF_ROLE_INFO:
            role = guild.get_role(role_id)
            if not role:
                continue

            if not role.members:
                value = "*No one currently holds this role*"
            else:
                value = ""
                for member in role.members:
                    status_emoji = "✅" if member.status != discord.Status.offline else "❌"
                    value += f"{status_emoji} {member.mention}\n"
                    if member.status != discord.Status.offline:
                        online_staff_mentions.append(member.mention)

            embed.add_field(name=f"{emoji} {role_name}", value=value.strip(), inline=False)

        embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

        if online_staff_mentions:
            embed.add_field(
                name="🟢 Staff Currently Online",
                value=", ".join(online_staff_mentions),
                inline=False
            )
        else:
            embed.add_field(
                name="🟢 Staff Currently Online",
                value="No staff are currently online.",
                inline=False
            )

        embed.set_footer(text=f"Generated on {current_time}")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    print("✅ Loaded Staff Cog")
    await bot.add_cog(Staff(bot))
