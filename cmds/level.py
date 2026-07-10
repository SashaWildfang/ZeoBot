import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection
from datetime import datetime

# -------------------------------
# ⚙️ Configuration
# -------------------------------
ADMIN_ROLE_IDS = {
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

DENY_ROLE_ID = 1431581220386373712  # ❌ Hard deny role
BOT_LOG_CHANNEL_ID = 1360344042705256660

class LevelAdmin(commands.Cog):
    """Unified Admin-level command to manage user levels via MongoDB."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]

    def is_admin(self, member: discord.Member) -> bool:
        if any(role.id == DENY_ROLE_ID for role in member.roles):
            return False
        return any(role.id in ADMIN_ROLE_IDS for role in member.roles)

    async def apply_role_update(self, member: discord.Member, old_level: int, new_level: int):
        """Triggers the leveling API to update roles based on the new level."""
        leveling_api = getattr(self.bot, "leveling", None)
        if leveling_api:
            await leveling_api.on_level_up(
                member,
                old_level=old_level,
                new_level=new_level,
                xp=0
            )

    async def log_level_embed(self, guild, moderator, target, old_level, new_level):
        channel = guild.get_channel(BOT_LOG_CHANNEL_ID)
        if not channel: return

        delta = new_level - old_level
        
        # Dynamic Styling
        if delta > 0:
            embed_color = discord.Color.green()
            status_icon = "🔼"
            action_text = "Level Increased"
        elif delta < 0:
            embed_color = discord.Color.from_rgb(255, 114, 118) # Light Red
            status_icon = "🔽"
            action_text = "Level Decreased"
        else:
            embed_color = discord.Color.gold()
            status_icon = "⚖️"
            action_text = "Level Synchronized"

        embed = discord.Embed(
            title=f"{status_icon} Level Log: {action_text}",
            color=embed_color,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(
            name="👤 Target User", 
            value=f"{target.mention}\nID: `{target.id}`", 
            inline=True
        )
        embed.add_field(
            name="🛠️ Moderator", 
            value=f"{moderator.mention}", 
            inline=True
        )
        
        embed.add_field(
            name="📊 Level Transaction",
            value=(
                f"**Old Level:** `{old_level}`\n"
                f"**Adjustment:** `{delta:+,}`\n"
                f"**New Level:** `{new_level}`\n"
                f"*Note: XP was reset to 0.*"
            ),
            inline=False
        )

        embed.set_footer(text="Zeo Level Management", icon_url=guild.icon.url if guild.icon else None)
        await channel.send(embed=embed)

    @app_commands.command(name="leveladmin", description="Unified command to manage user levels.")
    @app_commands.describe(
        action="Transaction type (Add, Remove, Set, Reset)",
        user="The user to modify",
        amount="Number of levels (Optional for Reset)",
        silent="Only show the response to you"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Reset", value="reset")
    ])
    async def level_admin(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str], 
        user: discord.Member, 
        amount: int = None, 
        silent: bool = False
    ):
        # 1. Security Check
        if not self.is_admin(interaction.user):
            return await interaction.response.send_message("❌ Admin+ permissions required.", ephemeral=True)

        if action.value != "reset":
            if amount is None:
                return await interaction.response.send_message("❌ Please provide an amount.", ephemeral=True)
            if amount < 0:
                return await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # 2. Fetch Data
        user_doc = await self.users_col.find_one({"discordId": user.id})
        old_level = user_doc.get("level", 1) if user_doc else 1
        new_level = old_level

        # 3. Process Actions
        if action.value == "add":
            new_level = old_level + amount
        elif action.value == "remove":
            new_level = max(1, old_level - amount)
        elif action.value == "set":
            new_level = max(1, amount)
        elif action.value == "reset":
            new_level = 1

        # 4. Database Update
        await self.users_col.update_one(
            {"discordId": user.id},
            {"$set": {"level": new_level, "xp": 0, "updatedAt": datetime.utcnow()}},
            upsert=True
        )

        # 5. Role & Log Synchronization
        await self.apply_role_update(user, old_level, new_level)
        await self.log_level_embed(interaction.guild, interaction.user, user, old_level, new_level)

        # 6. Response
        response_emoji = "📈" if new_level >= old_level else "📉"
        await interaction.followup.send(
            f"{response_emoji} **Level {action.name}** successful for {user.mention}.\n"
            f"**New Level:** `{new_level}` (XP Reset)",
            ephemeral=silent
        )

async def setup(bot):
    await bot.add_cog(LevelAdmin(bot))