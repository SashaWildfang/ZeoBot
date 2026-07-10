import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import get_connection
from events.leveling import xp_required_for

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

class XPAdmin(commands.Cog):
    """Unified Admin-level XP management (Async Motor)."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users = self.db["users"]

    def is_admin(self, member: discord.Member) -> bool:
        if any(role.id == DENY_ROLE_ID for role in member.roles):
            return False
        return any(role.id in ADMIN_ROLE_IDS for role in member.roles)

    async def log_xp_embed(self, guild, moderator, target, old_xp, new_xp, old_lvl, new_lvl, delta, action_name):
        channel = guild.get_channel(BOT_LOG_CHANNEL_ID)
        if not channel: return

        # Dynamic Styling
        if delta > 0:
            embed_color = discord.Color.green()
            status_icon = "📈"
        elif delta < 0:
            embed_color = discord.Color.from_rgb(255, 114, 118) # Light Red
            status_icon = "📉"
        else:
            embed_color = discord.Color.gold()
            status_icon = "⚖️"

        embed = discord.Embed(
            title=f"{status_icon} XP Log: {action_name}",
            color=embed_color,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(name="👤 User", value=f"{target.mention}\nID: `{target.id}`", inline=True)
        embed.add_field(name="🛠️ Moderator", value=f"{moderator.mention}", inline=True)
        
        level_str = f"`{old_lvl}`" if old_lvl == new_lvl else f"`{old_lvl}` ➜ `{new_lvl}`"
        
        embed.add_field(
            name="📊 Transaction Details",
            value=(
                f"**Action:** `{action_name}`\n"
                f"**Old XP:** `{old_xp:,}`\n"
                f"**Adjustment:** `{delta:+,}`\n"
                f"**New XP:** `{new_xp:,}`\n"
                f"**Level Status:** {level_str}"
            ),
            inline=False
        )

        embed.set_footer(text="Zeo XP Management", icon_url=guild.icon.url if guild.icon else None)
        await channel.send(embed=embed)

    @app_commands.command(name="xpadmin", description="Unified command to manage user XP.")
    @app_commands.describe(
        action="Transaction type (Add, Remove, Set)",
        user="The user to modify",
        amount="The amount of XP",
        silent="Only show the response to you"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="Set", value="set")
    ])
    async def xp_admin(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str], 
        user: discord.Member, 
        amount: int, 
        silent: bool = False
    ):
        # 1. Security Check
        if not self.is_admin(interaction.user):
            return await interaction.response.send_message("❌ Admin+ permissions required.", ephemeral=True)

        if amount < 0:
            return await interaction.response.send_message("❌ XP amount cannot be negative.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # 2. Fetch User Data
        doc = await self.users.find_one({"discordId": user.id}) or {"xp": 0, "level": 1}
        old_xp = int(doc.get("xp", 0))
        old_level = int(doc.get("level", 1))
        
        current_xp = old_xp
        current_level = old_level

        # 3. Process Actions
        if action.value == "add":
            current_xp += amount
        elif action.value == "remove":
            # Policy: Never level down, clamp at 0
            current_xp = max(0, old_xp - amount)
        elif action.value == "set":
            current_xp = amount

        # 4. Handle Level Carry-Over (Carry UP only)
        # Note: If removing XP, current_level remains same as old_level
        if action.value != "remove":
            while True:
                req = xp_required_for(current_level)
                if current_xp >= req:
                    current_xp -= req
                    current_level += 1
                else:
                    break

        delta = current_xp - old_xp # Note: This tracks current-level XP change

        # 5. Database Update
        await self.users.update_one(
            {"discordId": user.id},
            {"$set": {"xp": int(current_xp), "level": int(current_level), "updatedAt": datetime.utcnow()}},
            upsert=True
        )

        # 6. Notify Leveling System & Log
        if current_level != old_level:
            leveling_api = getattr(self.bot, "leveling", None)
            if leveling_api:
                await leveling_api.on_level_up(user, old_level=old_level, new_level=current_level, xp=current_xp)

        await self.log_xp_embed(
            interaction.guild, interaction.user, user, 
            old_xp, current_xp, old_level, current_level, delta, action.name
        )

        # 7. Response
        await interaction.followup.send(
            f"✅ **XP {action.name}** successful for {user.mention}.\n"
            f"**Level:** `{current_level}` | **Current XP:** `{current_xp:,}`",
            ephemeral=silent
        )

async def setup(bot):
    await bot.add_cog(XPAdmin(bot))
    print("✅ Loaded XPAdmin Cog (Unified System)")