import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import re

# ===============================
# ⚙️ Role Configuration
# ===============================
# Your specific Staff Team role ID
STAFF_TEAM_ROLE_ID = 1358470109965979859

# ===============================
# 🕵️ Whois Cog
# ===============================
class Whois(commands.Cog):
    """Lookup a user's Discord info via mention, username, or ID."""

    def __init__(self, bot):
        self.bot = bot

    def is_staff(self, member: discord.Member) -> bool:
        """Checks if the member has the Staff Team role."""
        return any(role.id == STAFF_TEAM_ROLE_ID for role in member.roles)

    @app_commands.command(
        name="whois",
        description="Lookup a user's information using their Discord ID or mention. (Staff Only)"
    )
    @app_commands.describe(discord_input="Mention a user or enter their Discord ID.")
    async def whois(self, interaction: discord.Interaction, discord_input: str):
        # 🔒 Staff check
        if not self.is_staff(interaction.user):
            await interaction.response.send_message(
                "❌ You must have the **Staff Team** role to use this command.", 
                ephemeral=True
            )
            return

        # Defer (public response)
        await interaction.response.defer(ephemeral=False)

        # 🧩 Extract ID from input (mentions look like <@ID> or <@!ID>)
        match = re.search(r"\d{17,20}", discord_input)
        if not match:
            await interaction.followup.send("❌ Please provide a valid Discord ID or mention.", ephemeral=True)
            return

        user_id = int(match.group())

        # 🎣 Fetch user from Discord API (works even if not in server)
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            await interaction.followup.send("❌ User not found.")
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"⚠️ Failed to fetch user info: {e}")
            return

        # 👥 Check if the user is currently in the server
        member = interaction.guild.get_member(user_id)

        # 🪪 Create Embed
        embed = discord.Embed(
            title="🕵️ User Lookup Result",
            color=discord.Color.teal(),
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Global Account Info
        embed.add_field(name="👤 Global Name", value=user.name, inline=True)
        embed.add_field(name="🆔 User ID", value=f"`{user.id}`", inline=True)
        embed.add_field(
            name="📅 Account Created", 
            value=f"{discord.utils.format_dt(user.created_at, style='F')} ({discord.utils.format_dt(user.created_at, style='R')})", 
            inline=False
        )

        # Server-Specific Info
        if member:
            embed.add_field(name="🪞 Server Nickname", value=member.display_name, inline=True)
            embed.add_field(
                name="📥 Joined Server", 
                value=f"{discord.utils.format_dt(member.joined_at, style='F')} ({discord.utils.format_dt(member.joined_at, style='R')})", 
                inline=False
            )

            # Get roles (exclude @everyone)
            roles = [r.mention for r in member.roles if r.name != "@everyone"]
            role_list = " ".join(roles) if roles else "None"
            embed.add_field(name=f"🏷️ Roles [{len(roles)}]", value=role_list[:1024], inline=False)

            embed.add_field(name="💬 Top Role", value=member.top_role.mention if member.top_role else "None", inline=True)
            # member.status requires Presence Intent enabled in bot and dev portal
            status_text = str(member.status).replace("dnd", "Do Not Disturb").title()
            embed.add_field(name="🎯 Status", value=status_text, inline=True)
        else:
            embed.add_field(name="⚠️ Server Status", value="This user is not currently in this server.", inline=False)

        embed.set_footer(text=f"Requested by {interaction.user.name}")
        await interaction.followup.send(embed=embed)


# ===============================
# ⚙️ Cog Setup
# ===============================
async def setup(bot):
    await bot.add_cog(Whois(bot))
