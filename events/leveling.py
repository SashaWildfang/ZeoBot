import discord
from discord.ext import commands
import random
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from db.database import get_connection

LEVEL_UP_CHANNEL_ID = 1358485848953327900
XP_RANGE = (15, 25)
XP_GAIN_COOLDOWN = 60  # seconds

LEVEL_ROLE_THRESHOLDS = [
    (0, 1361677978421035180),
    (5, 1361678583713759363),
    (11, 1361678717197221968),
    (21, 1361678760327512185),
    (31, 1361679050632073398),
    (41, 1361679477700038828),
    (51, 1361680109953876049),
    (61, 1361680599672422540),
    (71, 1361680699563966605),
    (81, 1361680852064407683),
    (91, 1361681482946576504),
]

UNVERIFIED_ROLE_ID = 1358469817191104716

# --- MEDIA PERMS CONSTANTS ---
MEDIA_PERMS_ROLE_ID = 1502679664894677063
MEDIA_ANNOUNCEMENT_CHANNEL_ID = 1358485891361804358
MEMBER_ROLE_ID = 1358469854725931038
REQUIRED_MEDIA_LEVEL = 5

user_cooldowns = {}

# -------------------------------
# ⭐ XP CURVE
# -------------------------------
def xp_required_for(level: int) -> int:
    return 100 if level <= 1 else int(100 * (level ** 1.2))


def get_level_role(level: int):
    role_id = None
    for lvl, rid in LEVEL_ROLE_THRESHOLDS:
        if level >= lvl:
            role_id = rid
        else:
            break
    return role_id


def next_role_info(level: int):
    for lvl, rid in LEVEL_ROLE_THRESHOLDS:
        if lvl > level:
            return lvl, rid
    return None, None


class LevelManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_connection()

    # ------------------------------------------
    # ⭐ Get user data
    # ------------------------------------------
    async def get_user_data(self, user_id: int):
        user = await self.db.users.find_one({"discordId": int(user_id)})

        if not user:
            return 0, 1, 0

        total_xp = user.get("totalXp", 0)
        leftover = user.get("xp", 0)
        level = user.get("level", 1)

        return total_xp, level, leftover

    # ------------------------------------------
    # Save user
    # ------------------------------------------
    async def update_user_record(self, user_id: int, total_xp: int, leftover_xp: int, level: int):
        await self.db.users.update_one(
            {"discordId": int(user_id)},
            {"$set": {"totalXp": total_xp, "xp": leftover_xp, "level": level}},
            upsert=True
        )

    # ------------------------------------------
    # Daily Stats
    # ------------------------------------------
    async def update_daily_stats(self, user_id: int, xp_gain: int, level_gain: int):
        today_str = date.today().isoformat()
        await self.db.daily_stats.update_one(
            {"discordId": int(user_id), "stat_date": today_str},
            {"$inc": {"xp": xp_gain, "levels": level_gain}},
            upsert=True
        )

    # ------------------------------------------
    # Role Assignment
    # ------------------------------------------
    async def apply_level_role(self, member: discord.Member, old_level: int, new_level: int):
        new_role_id = get_level_role(new_level)
        old_role_id = get_level_role(old_level)

        if new_role_id == old_role_id:
            return None

        new_role = member.guild.get_role(new_role_id)
        old_role = member.guild.get_role(old_role_id)

        if old_role:
            await member.remove_roles(old_role)
        if new_role:
            await member.add_roles(new_role)

        return new_role

    # ------------------------------------------
    # ⭐ Core Logic: Update XP, Level, and Balance
    # ------------------------------------------
    async def add_xp(self, member: discord.Member, xp_gain: int, balance_gain: int):
        # 1. Fetch current data from the DB
        total_xp, level, leftover = await self.get_user_data(member.id)

        # 2. Update the totals
        new_total_xp = total_xp + xp_gain
        new_leftover = leftover + xp_gain
        
        old_level = level
        xp_needed = xp_required_for(level)

        # 3. Check for Level Up (loop handles multiple level gains at once)
        while new_leftover >= xp_needed:
            new_leftover -= xp_needed
            level += 1
            xp_needed = xp_required_for(level)

        # 4. Save XP and Level data
        await self.update_user_record(member.id, new_total_xp, new_leftover, level)

        # 5. Save Balance/Daily Stat data
        await self.db.users.update_one(
            {"discordId": int(member.id)},
            {"$inc": {"balance": balance_gain}},
            upsert=True
        )
        await self.update_daily_stats(member.id, xp_gain, level - old_level)

        # 6. Trigger Level-Up Announcement if they progressed
        if level > old_level:
            await self.on_level_up(member, old_level, level, new_leftover)

    # ------------------------------------------
    # XP & Leaf Gain per message
    # ------------------------------------------
    async def on_xp_gain(self, message: discord.Message):
        user_id = str(message.author.id)
        now = datetime.now(timezone.utc).timestamp()

        if message.author.bot or not message.guild:
            return

        # Cooldown check (1 earning per minute)
        if user_id in user_cooldowns and now - user_cooldowns[user_id] < XP_GAIN_COOLDOWN:
            return

        # Skip unverified
        if message.guild.get_role(UNVERIFIED_ROLE_ID) in message.author.roles:
            return

        user_cooldowns[user_id] = now

        # Fetch Global and User configs from DB
        global_config = await self.db.globals.find_one({"id": 1})
        user_record = await self.db.users.find_one({"discordId": int(user_id)})

        is_weekend = global_config.get("isXpWeekend", 0) == 1 if global_config else False

        # ---------------------------------
        # 1. Fetch Multipliers from DB
        # ---------------------------------
        # These are accurately maintained by RoleChangeListener/Store!
        xp_multiplier = user_record.get("xpMultiplier", 1.0) if user_record else 1.0
        leaf_multiplier = user_record.get("multiplier", 1.0) if user_record else 1.0

        # Stack the 2x Weekend Boost (+1.0) onto XP ONLY
        if is_weekend:
            xp_multiplier += 1.0

        # ---------------------------------
        # 2. Apply Multipliers and Save
        # ---------------------------------
        base_xp = random.randint(*XP_RANGE)
        xp_gain = int(base_xp * xp_multiplier)

        base_leaves = 5
        balance_gain = int(base_leaves * leaf_multiplier)

        # Pass both gains to the database saver
        await self.add_xp(message.author, xp_gain, balance_gain)

    # ------------------------------------------
    # Level-Up Announce
    # ------------------------------------------
    async def on_level_up(self, member, old_level, new_level, xp):

        xp_needed = xp_required_for(new_level)
        next_rank_level, next_role_id = next_role_info(new_level)

        next_rank_name = "None"
        if next_role_id:
            role = member.guild.get_role(next_role_id)
            if role:
                clean = role.name.split(" [")[0].strip()
                away = next_rank_level - new_level
                next_rank_name = f"{clean} [in {away} Levels]"

        new_role = await self.apply_level_role(member, old_level, new_level)

        # ==========================================
        # INSTANT MEDIA PERMS CHECK
        # ==========================================
        if new_level >= REQUIRED_MEDIA_LEVEL:
            has_member_role = any(r.id == MEMBER_ROLE_ID for r in member.roles)
            has_media_role = any(r.id == MEDIA_PERMS_ROLE_ID for r in member.roles)

            if has_member_role and not has_media_role:
                media_role = member.guild.get_role(MEDIA_PERMS_ROLE_ID)
                if media_role:
                    # 1. Grant the role immediately
                    await member.add_roles(media_role, reason=f"Instant Level Up Sync: Reached Level {new_level}")
                    
                    # 2. Update the Database
                    await self.db.users.update_one(
                        {"discordId": member.id},
                        {"$set": {"hasMediaPerms": True}}
                    )

                    # 3. Send the Announcement
                    ann_channel = member.guild.get_channel(MEDIA_ANNOUNCEMENT_CHANNEL_ID)
                    if ann_channel:
                        try:
                            await ann_channel.send(
                                f"🎉 {member.mention}, you have been granted Media Perms! You can now post Embeds, Media, and add Reactions."
                            )
                        except discord.Forbidden:
                            pass
        # ==========================================

        # Fall/Autumn themed Embed
        embed = discord.Embed(
            title="🍂 You Leveled Up!",
            color=discord.Color.from_rgb(210, 105, 30), # Autumn Orange
            description=(
                f"Awesome job, {member.mention}! You're raking in the Leaves and reached **Level {new_level}**!\n\n"
                f"🍁 **XP:** `{xp}` / `{xp_needed}`\n"
                f"🎯 **Next Milestone:** `{next_rank_name}`"
            ),
            timestamp=datetime.now(ZoneInfo("America/New_York"))
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)

        if new_role:
            embed.add_field(name="🌟 New Rank!", value=f"You unlocked the **{new_role.name}** role!")

        channel = member.guild.get_channel(LEVEL_UP_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)


# ------------------------------------------
# Setup
# ------------------------------------------
async def setup(bot):
    leveling = LevelManager(bot)

    class LevelCog(commands.Cog):
        @commands.Cog.listener()
        async def on_message(self, message):
            await leveling.on_xp_gain(message)

    await bot.add_cog(LevelCog()) 
    bot.leveling = leveling