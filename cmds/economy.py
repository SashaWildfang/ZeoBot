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

DENY_ROLE_ID = 1431581220386373712  
BOT_LOG_CHANNEL_ID = 1360344042705256660

class EconomyAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.col = self.db["users"]

    def is_admin(self, member: discord.Member) -> bool:
        if any(role.id == DENY_ROLE_ID for role in member.roles):
            return False
        return any(role.id in ADMIN_ROLE_IDS for role in member.roles)

    async def log_economy_embed(self, guild, title, moderator, target, old_val, new_val, delta):
        channel = guild.get_channel(BOT_LOG_CHANNEL_ID)
        if not channel: return

        # Dynamic Color & Emoji Logic
        if delta > 0:
            embed_color = discord.Color.green()
            action_text = "Leaves Added"
            status_icon = "📈"
        elif delta < 0:
            embed_color = discord.Color.from_rgb(255, 114, 118) # Light Red
            action_text = "Leaves Removed"
            status_icon = "📉"
        else:
            embed_color = discord.Color.light_grey()
            action_text = "Leaf Update"
            status_icon = "⚖️"

        embed = discord.Embed(
            title=f"{status_icon} Economy Log: {action_text}",
            color=embed_color,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(
            name="👤 Target User", 
            value=f"{target.mention}\n`{target.name}`\nID: `{target.id}`", 
            inline=True
        )
        embed.add_field(
            name="🛠️ Moderator", 
            value=f"{moderator.mention}\n`{moderator.name}`", 
            inline=True
        )
        
        embed.add_field(
            name="📊 Transaction Details",
            value=(
                f"**Old Balance:** `{old_val:,}`\n"
                f"**Adjustment:** `{delta:+,}`\n"
                f"**New Balance:** `{new_val:,}`"
            ),
            inline=False
        )

        await channel.send(embed=embed)

    @app_commands.command(name="economyadmin", description="Command to manage user leaves")
    @app_commands.describe(
        action="The transaction type (Add, Remove, Set, Reset)",
        user="The user to modify",
        amount="The amount of leaves (Optional for Reset)",
        silent="Only show the response to you"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="Set", value="set"),
        app_commands.Choice(name="Reset", value="reset")
    ])
    async def economy_admin(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str], 
        user: discord.Member, 
        amount: int = None, 
        silent: bool = False
    ):
        if not self.is_admin(interaction.user):
            return await interaction.response.send_message("❌ You lack permission to manage the economy.", ephemeral=True)

        if action.value != "reset":
            if amount is None:
                return await interaction.response.send_message("❌ Please provide an amount for this action.", ephemeral=True)
            if amount < 0:
                return await interaction.response.send_message("❌ Amounts cannot be negative.", ephemeral=True)

        await interaction.response.defer(ephemeral=silent)

        # Database fetch
        doc = await self.col.find_one({"discordId": user.id}, {"balance": 1})
        old_balance = doc.get("balance", 0) if doc else 0
        new_balance = old_balance
        title_suffix = action.name

        if action.value == "add":
            new_balance = old_balance + amount
        elif action.value == "remove":
            new_balance = max(0, old_balance - amount)
        elif action.value == "set":
            new_balance = amount
        elif action.value == "reset":
            new_balance = 0
            amount = 0 # for delta calculation

        delta = new_balance - old_balance

        # Apply update
        await self.col.update_one(
            {"discordId": user.id},
            {
                "$set": {"balance": new_balance, "updatedAt": datetime.utcnow()},
                "$setOnInsert": {
                    "createdAt": datetime.utcnow(),
                    "level": 1, "xp": 0, "xpNeeded": 100
                }
            },
            upsert=True
        )

        # Detailed Logging
        await self.log_economy_embed(
            interaction.guild, f"Leaves {title_suffix}", 
            interaction.user, user, 
            old_balance, new_balance, delta
        )

        # Final response
        response_emoji = "✅" if delta >= 0 else "🛑"
        await interaction.followup.send(
            f"{response_emoji} **{action.name}** successful for {user.mention}.\n"
            f"**Change:** `{delta:+,}` <:leaf:1524758896659660831> | **New Total:** `{new_balance:,}` <:leaf:1524758896659660831>",
            ephemeral=silent
        )

async def setup(bot):
    await bot.add_cog(EconomyAdmin(bot))