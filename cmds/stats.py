import discord
import re
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import get_connection
from events.leveling import xp_required_for

# Now we only need the thresholds and their corresponding IDs
LEVEL_ROLE_THRESHOLDS = [
    (0, 1361677978421035180), (5, 1361678583713759363), (11, 1361678717197221968),
    (21, 1361678760327512185), (31, 1361679050632073398), (41, 1361679477700038828),
    (51, 1361680109953876049), (61, 1361680599672422540), (71, 1361680699563966605),
    (81, 1361680852064407683), (91, 1361681482946576504)
]

PATREON_TIER_1 = 1362102163693633818
PATREON_TIER_2 = 1362502662721114245
PATREON_TIER_3 = 1362502871639396362
BOOSTER_ROLE_ID = 1360260086500561237

STAFF_ROLE_IDS = {
    1358470318087340342, 1358472557862457537, 1358472532222808126,
    1358472588430676018, 1358472511133585564, 1358472635234779207,
    1358473248534167663
}

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users = self.db["users"]
        self.globals = self.db["globals"]
        self.temp_boosters = self.db["temporary_boosters"] # Added connection to temp boosters!

    @app_commands.command(name="stats", description="View a user's level, XP, Leaves, and other details.")
    @app_commands.describe(user="The user to view (defaults to yourself)")
    async def stats(self, interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer()
        
        user = user or interaction.user
        user_data = await self.users.find_one({"discordId": user.id})

        if not user_data:
            await interaction.followup.send(f"{user.mention} has no stats yet.", ephemeral=True)
            return

        level = user_data.get("level", 1)
        xp = user_data.get("xp", 0)
        balance = user_data.get("balance", 0)
        messages_sent = user_data.get("msgCount", 0)

        # --- RANKINGS FILTERED BY SERVER MEMBERS ---
        # Get a list of IDs for everyone currently in the server
        server_member_ids = [member.id for member in interaction.guild.members]
        
        total_users = await self.users.count_documents({"discordId": {"$in": server_member_ids}})
        
        balance_rank = await self.users.count_documents({
            "discordId": {"$in": server_member_ids},
            "balance": {"$gt": balance}
        }) + 1
        
        level_rank = await self.users.count_documents({
            "discordId": {"$in": server_member_ids},
            "level": {"$gt": level}
        }) + 1

        # XP Bar
        next_level_xp = xp_required_for(level)
        xp_progress = min(xp / next_level_xp, 1.0)
        filled = int(xp_progress * 20)
        progress_bar = f"[{'█' * filled}{'░' * (20 - filled)}] {xp_progress * 100:.1f}%"

        # --- DYNAMIC ROLE FETCHING ---
        current_role_id = None
        for threshold, role_id in reversed(LEVEL_ROLE_THRESHOLDS):
            if level >= threshold:
                current_role_id = role_id
                break

        # Get role object from guild to fetch the name dynamically
        role_obj = interaction.guild.get_role(current_role_id)
        rank_name = role_obj.name if role_obj else "Tribal Paw"

        # Determine next reward dynamically
        next_reward = "None (Max Reached)"
        for threshold, role_id in LEVEL_ROLE_THRESHOLDS:
            if threshold > level:
                next_role_obj = interaction.guild.get_role(role_id)
                next_role_name = next_role_obj.name if next_role_obj else f"Level {threshold} Role"
                next_reward = f"{next_role_name} in {threshold - level} lvl(s)"
                break

        # Multipliers Logic
        is_booster = any(r.id == BOOSTER_ROLE_ID for r in user.roles)
        patreon_tier = "None"
        patreon_bonus = 0.0

        if any(r.id == PATREON_TIER_3 for r in user.roles):
            patreon_bonus, patreon_tier = 0.40, "Legendary Neko"
        elif any(r.id == PATREON_TIER_2 for r in user.roles):
            patreon_bonus, patreon_tier = 0.20, "Feral Guardian"
        elif any(r.id == PATREON_TIER_1 for r in user.roles):
            patreon_bonus, patreon_tier = 0.10, "Royal Kitten"

        global_data = await self.globals.find_one({}) or {}
        weekend_mult = global_data.get("xpWeekendMultiplier", 1.0) if global_data.get("isXpWeekend") else 1.0
        booster_mult = global_data.get("boosterMultiplier", 1.0) if global_data.get("isBoosterActive") else 1.0
        
        xp_multiplier = 1.0 + patreon_bonus + (0.15 if is_booster else 0.0) + (weekend_mult - 1.0) + (booster_mult - 1.0)
        multiplier = 1.0 + (0.15 if is_booster else 0.0)

        # --- ACTIVE TEMP BOOSTER CHECK ---
        active_booster = await self.temp_boosters.find_one({"discordId": str(user.id)})
        active_booster_text = "None"

        if active_booster:
            end_time_ts = int(active_booster['end_time'].timestamp())
            item_name = active_booster.get("item_name", "Unknown Booster")
            active_booster_text = f"**{item_name}** (Ends <t:{end_time_ts}:R>)"

            # Apply the 2x multiplier directly to the stat card!
            if active_booster.get("item_id") == "booster_xp":
                xp_multiplier *= 2.0
            elif active_booster.get("item_id") == "booster_balance":
                multiplier *= 2.0

        # Build Embed
        embed = discord.Embed(
            title=f"{user.display_name}'s Stats",
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="☀️ Level", value=f"{level}", inline=True)
        embed.add_field(name="📈 XP", value=f"{xp:,}/{next_level_xp:,}", inline=True)
        embed.add_field(name="<:leaf:1524758896659660831> Leaves", value=f"{balance:,}", inline=True)
        embed.add_field(name="🏆 Level Rank", value=f"#{level_rank}/{total_users}", inline=True)
        embed.add_field(name="🏅 Rank", value=rank_name, inline=True)
        embed.add_field(name="🎯 Next Reward", value=next_reward, inline=True)
        embed.add_field(name="<:leaf:1524758896659660831> Leaf Rank", value=f"#{balance_rank}/{total_users}", inline=True)
        embed.add_field(name="✨ XP Multiplier", value=f"{xp_multiplier:.2f}x", inline=True)
        embed.add_field(name="<:leaf:1524758896659660831> Leaf Multiplier", value=f"{multiplier:.2f}x", inline=True)
        embed.add_field(name="📆 Joined Server", value=user.joined_at.strftime('%B %d, %Y') if user.joined_at else "Unknown", inline=True)
        embed.add_field(name="📛 Highest Role", value=user.top_role.mention if user.top_role else "None", inline=True)
        embed.add_field(name="💬 Messages Sent", value=f"{messages_sent:,}", inline=True)
        embed.add_field(name="🛡️ Staff Member?", value="✅ Yes" if any(r.id in STAFF_ROLE_IDS for r in user.roles) else "❌ No", inline=True)
        embed.add_field(name="🎗️ Patreon Tier", value=patreon_tier, inline=True)
        
        # Add the new Consumable Field right before the XP bar!
        embed.add_field(name="🔥 Active Consumable", value=active_booster_text, inline=False)
        embed.add_field(name="📊 XP Progress", value=progress_bar, inline=False)
        embed.set_footer(text="Keep chatting to earn more XP!")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))