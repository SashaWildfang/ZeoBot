import asyncio
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any, Optional, Literal

import discord
from discord.ext import commands
from discord import app_commands

from bson.objectid import ObjectId

from db.database import get_connection  # returns AsyncIOMotorDatabase

# =========================
# Config / Constants
# =========================

NITRO_ROLE_ID = 1360260086500561237
GIF_DOMAINS = ["tenor.com", "giphy.com", "gyazo.com", "imgur.com", "gfycat.com"]
BOT_LOGS_CHANNEL_ID = 1358486649360748665
MUTE_ALERTS_CHANNEL_ID = 1358485891361804358  # <-- Where mute notifications go
STAFF_NOTIFY_CHANNEL_ID = 1485825407654559846 # <-- 5th Offense alert channel

# Media Perms Roles & Channels
ROLE_LVL_1_4 = 1361677978421035180
ROLE_LVL_5_10 = 1361678583713759363
BOT_COMMANDS_CH = 1358485820100706314

# Role Permissions
STAFF_TEAM_ROLE_ID = 1358470109965979859
CLEAR_ALL_ROLE_IDS = {
    1358472511133585564, 
    1358472635234779207, 
    1416866395366359193, 
    1358473248534167663
}

FILTER_FILE = "word_filter.json"

# Relaxed Rule Zones
RELAXED_CATEGORIES = {
    1358487031117906033, 
    1358487125661585658, 
    1503207763352748154,
    1358488251996045388,
    1358488573497708764
}
SEVERE_WORDS = {"nigger", "nigga", "nig"} # Unforgivable regardless of category

SPAM_WINDOW = 3
SPAM_TRIGGER_COUNT = 3
SHORT_MSG_THRESHOLD = 5
DIVERSITY_THRESHOLD = 3
CAPS_RATIO_THRESHOLD = 0.90
MENTION_LIMIT = 5
DEFAULT_MUTE_SECONDS = 60

active_enforcements = set()

# =========================
# Mongo Utilities
# =========================

def mongo():
    return get_connection()

def users_col():
    return mongo()["users"]

def punish_col():
    return mongo()["punishments"]

async def ensure_indexes():
    """Ensure indexes exist — safe to call repeatedly."""
    pcol = punish_col()
    ucol = users_col()
    await pcol.create_index([("discordId", 1), ("timestamp", -1)])
    await pcol.create_index([("expiresAt", 1)])
    await ucol.create_index([("discordId", 1)], unique=True)

async def delete_offense_by_id(offense_id: str) -> bool:
    try:
        res = await punish_col().delete_one({"_id": ObjectId(offense_id)})
        return res.deleted_count > 0
    except Exception as e:
        print(f"❌ Error deleting offense by ID: {e}")
        return False

# =========================
# Core Helpers
# =========================

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"

def get_decay_time(reason: str) -> timedelta:
    """Returns the timedelta until an offense expires based on severity."""
    lesser_reasons = [
        "Extreme character repetition",
        "Keyboard smashing",
        "Low character diversity",
        "Excessive capital letters",
        "Excessive short messages"
    ]
    if any(lr in reason for lr in lesser_reasons):
        return timedelta(hours=1)  # 1 hour decay for lesser spam/formatting rules
    return timedelta(days=1)       # 1 day decay for severe offenses (slurs, invites, rapid spam)

async def ensure_muted_role(guild: discord.Guild) -> Optional[discord.Role]:
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if muted_role:
        return muted_role

    try:
        muted_role = await guild.create_role(name="Muted", reason="AutoMod mute role")
        for channel in guild.channels:
            try:
                await channel.set_permissions(
                    muted_role,
                    send_messages=False,
                    speak=False,
                    add_reactions=False
                )
            except Exception:
                pass
        return muted_role
    except Exception as e:
        print(f"❌ Failed creating Muted role in guild {guild.id}: {e}")
        return None

def is_staff(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    return any(role.id == STAFF_TEAM_ROLE_ID for role in member.roles)

def is_admin(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    return any(role.id in CLEAR_ALL_ROLE_IDS for role in member.roles)

def can_clear_all(member: discord.Member) -> bool:
    return is_admin(member)

async def user_level_and_nitro(member: discord.Member) -> Tuple[int, bool]:
    doc = await users_col().find_one({"discordId": member.id}, {"level": 1})
    level = int(doc["level"]) if doc and "level" in doc else 0
    has_nitro = any(r.id == NITRO_ROLE_ID for r in member.roles)
    return level, has_nitro

async def record_punishment(discord_id: int, issuer_id: int, action: str, reason: str,
                            duration_seconds: Optional[int] = None, extra_info: Optional[str] = None,
                            message_content: Optional[str] = None) -> str:
    now = datetime.utcnow()
    decay_time = get_decay_time(reason)
    expires_at = now + decay_time 
    
    doc = {
        "discordId": discord_id,
        "issuerId": issuer_id,
        "action": action,
        "reason": reason,
        "timestamp": now,
        "durationSeconds": duration_seconds, 
        "expiresAt": expires_at,            
        "extraInfo": extra_info or "",
        "messageContent": message_content or "",
    }
    res = await punish_col().insert_one(doc)
    return str(res.inserted_id)

async def recent_punishments(discord_id: int) -> List[Dict[str, Any]]:
    now = datetime.utcnow()
    # Pull ONLY offenses that have not yet expired
    cursor = punish_col().find(
        {"discordId": discord_id, "expiresAt": {"$gt": now}}
    ).sort("timestamp", -1)
    return [doc async for doc in cursor]

async def all_punishments(discord_id: int) -> List[Dict[str, Any]]:
    cursor = punish_col().find({"discordId": discord_id}).sort("timestamp", -1)
    return [doc async for doc in cursor]

async def delete_offense_by_timestamp(discord_id: int, ts: datetime) -> int:
    res = await punish_col().delete_one({"discordId": discord_id, "timestamp": ts})
    return res.deleted_count

async def delete_last_offense(discord_id: int) -> int:
    last = await punish_col().find({"discordId": discord_id}).sort("timestamp", -1).to_list(1)
    if not last:
        return 0
    res = await punish_col().delete_one({"_id": last[0]["_id"]})
    return res.deleted_count

async def delete_all_punishments(discord_id: int) -> int:
    res = await punish_col().delete_many({"discordId": discord_id})
    return res.deleted_count

# =========================
# AutoMod Core
# =========================

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: Dict[int, List[discord.Message]] = defaultdict(list)
        self.caps_history: Dict[int, float] = {}  # Tracks last caps message timestamp for users
        self.bad_words = self._load_filter()
        asyncio.create_task(ensure_indexes())
        
        # --- MEDIA PERM REGEX ---
        self.media_complaint_regex = re.compile(
            r"(can'?t|cannot|not able to|how do i|why can'?t i|no perms? to|unable to).{0,15}(post|send|upload|use|attach).{0,15}(pics?|photos?|images?|gifs?|media|attachments?|pictures?)",
            re.IGNORECASE
        )

        # --- SMART SPAM REGEXES ---
        self.char_repeat_regex = re.compile(r'(.)\1{12,}', re.IGNORECASE)
        self.long_word_regex = re.compile(r'(?<!\S)[a-zA-Z]{25,}(?!\S)')

    def _load_filter(self) -> list:
        default_words = [
            "nigger", "faggot", "cunt", "nigga", 
            "nig", "fag", "kys", "kill yourself"
        ]
        if not os.path.exists(FILTER_FILE):
            with open(FILTER_FILE, "w") as f:
                json.dump(default_words, f)
        
        with open(FILTER_FILE, "r") as f:
            raw_words = json.load(f)

        compiled_patterns = []
        
        leetspeak = {
            'a': r'[a@4\*]', 'b': r'[b8]', 'c': r'[c\(\[k]', 
            'e': r'[e3\*]', 'i': r'[i1!l\*\|]', 'o': r'[o0\*]', 
            's': r'[s5\$]', 't': r'[t7\+]', 'l': r'[l1!\|]', 
            'g': r'[gq69]', 'y': r'[yv]'
        }
        
        for word in raw_words:
            pattern_str = r'(?<![a-z])'
            
            for i, char in enumerate(word.lower()): 
                if char == ' ':
                    pattern_str += r'[\s\W]+'
                else:
                    p = leetspeak.get(char, re.escape(char))
                    pattern_str += rf'{p}+' 
                    
                    if i < len(word) - 1:
                        pattern_str += r'[\W_]*'
            
            pattern_str += r'(?:[s5\$]+)?'
            pattern_str += r'(?![a-z])'
            compiled_patterns.append((word, re.compile(pattern_str, re.IGNORECASE)))
            
        return compiled_patterns

    def _is_spam(self, uid: int, messages: List[discord.Message], current_msg: discord.Message) -> Tuple[bool, str]:
        now = time.time()
        contents = [m.content.strip().lower() for m in messages]
        current_content = (current_msg.content or "").strip()
        
        # 1. Rapid messages
        if len(messages) >= 3 and now - messages[0].created_at.timestamp() < 3:
            return True, "Rapid messages detected"

        # 2. Repeated Characters
        if self.char_repeat_regex.search(current_content):
            if '\n' in current_content or len(current_content) > 80:
                return True, "Extreme character repetition (>12 chars)"
            
        # 3. Keyboard Smashing
        content_no_urls = re.sub(r'https?://\S+', '', current_content)
        if self.long_word_regex.search(content_no_urls):
            if '\n' in current_content or len(current_content) > 80:
                return True, "Keyboard smashing (25+ letters without spaces)"

        # 4. Repeated identical messages
        if current_content and contents.count(current_content.lower()) >= 3:
            return True, "Repeated identical messages"

        # 5. Short message spam
        if len([c for c in contents if len(c) <= SHORT_MSG_THRESHOLD]) >= SPAM_TRIGGER_COUNT:
            return True, "Excessive short messages"
        
        # 6. Low Diversity
        chars = list(current_content.replace(" ", ""))
        if len(chars) > 80 and len(set(chars)) <= DIVERSITY_THRESHOLD:
            return True, "Low character diversity"

        # 7. Caps Lock Spam (Allows 1st message, blocks if 2nd occurs within 60s)
        alpha = ''.join(c for c in current_content if c.isalpha())
        if len(alpha) > 15:
            caps = sum(1 for c in current_content if c.isupper())
            if caps / len(alpha) > CAPS_RATIO_THRESHOLD:
                last_caps_time = self.caps_history.get(uid, 0)
                self.caps_history[uid] = now
                if now - last_caps_time < 60: # 60 seconds window
                    return True, "Excessive capital letters"
            
        return False, ""

    def _is_filtered(self, message: discord.Message, in_relaxed_zone: bool) -> Tuple[bool, str]:
        content = (message.content or "").lower()

        if "discord.gg/" in content or "discord.com/invite/" in content:
            return (True, "Server invite link")

        has_gif_link = any(domain in content for domain in GIF_DOMAINS)
        has_embeds = bool(message.embeds)
        if has_embeds or has_gif_link:
            return (False, "") 

        for original_word, pattern in self.bad_words:
            if pattern.search(content):
                # If we are in a relaxed zone, ignore everything except severe words
                if in_relaxed_zone and original_word not in SEVERE_WORDS:
                    continue
                return (True, f"Inappropriate language: `{original_word}`")

        if len(message.mentions) > MENTION_LIMIT:
            return (True, "Excessive mentions")

        return (False, "")

    async def _mute_user(self, member: discord.Member, duration_sec: int, reason: str, message_content: str = ""):
        role = await ensure_muted_role(member.guild)
        if not role:
            return
        try:
            await member.add_roles(role, reason=f"AutoMod Mute: {reason}")
            await record_punishment(member.id, self.bot.user.id, "mute", reason, duration_sec, "AutoMod", message_content)

            # --- Send public mute notification ---
            duration_str = format_duration(duration_sec)
            expires_unix = int(time.time() + duration_sec)
            
            try:
                alert_channel = self.bot.get_channel(MUTE_ALERTS_CHANNEL_ID) or await self.bot.fetch_channel(MUTE_ALERTS_CHANNEL_ID)
                if alert_channel:
                    await alert_channel.send(
                        f"{member.mention}, you have been muted for {duration_str}.\n"
                        f"**Reason:** {reason}\n"
                        f"**Expires:** <t:{expires_unix}:R>"
                    )
            except Exception as e:
                print(f"❌ Failed to send mute notification: {e}")

            async def unmute_later():
                await asyncio.sleep(duration_sec)
                try:
                    fresh = await member.guild.fetch_member(member.id)
                    if role in fresh.roles:
                        await fresh.remove_roles(role, reason="Auto unmute (AutoMod)")
                        
                        # --- Send public unmute notification ---
                        try:
                            alert_chan = self.bot.get_channel(MUTE_ALERTS_CHANNEL_ID) or await self.bot.fetch_channel(MUTE_ALERTS_CHANNEL_ID)
                            if alert_chan:
                                await alert_chan.send(f"{member.mention}, your mute has expired. You can now speak again.")
                        except Exception as e:
                            print(f"❌ Failed to send unmute notification: {e}")
                except Exception as e:
                    print(f"❌ Auto unmute failed for {member.id}: {e}")

            asyncio.create_task(unmute_later())
        except Exception as e:
            print(f"❌ Failed to mute {member.id}: {e}")

    async def _log_action(self, member: discord.Member, channel: discord.TextChannel, reason: str,
                          deleted: List[discord.Message], offense_num: int):
        
        # Calculate effective cycle (1-8 loop)
        effective_offense = ((offense_num - 1) % 8) + 1
        
        escalations = {
            1: "Warning", 2: "Warning", 3: "5m Mute", 4: "10m Mute",
            5: "15m Mute", 6: "30m Mute", 7: "1hr Mute", 8: "1D Mute"
        }
        
        current_action = escalations.get(effective_offense, "Unknown")
        next_action = escalations.get((offense_num % 8) + 1, "Unknown")

        log_color = discord.Color.orange() if effective_offense <= 4 else discord.Color.red()

        embed = discord.Embed(
            title="🚨 AutoMod Escalation Log",
            description=f"{member.mention} has reached **Offense #{offense_num}**.",
            color=log_color,
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention}\n`{member.id}`", inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Offense Count", value=f"**{offense_num}** (Cycle Step: {effective_offense}/8)", inline=True)
        embed.add_field(name="Action Taken", value=f"**{current_action}**", inline=True)
        embed.add_field(name="Next Step", value=f"**{next_action}**", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        if deleted:
            preview = "\n".join([f"`{m.content[:100]}`" for m in deleted if m.content])
            if preview:
                embed.add_field(name="🗑️ Deleted Content", value=preview[:1024], inline=False)

        decay_time = get_decay_time(reason)
        decay_str = "1 hour" if decay_time.total_seconds() <= 3600 else "1 day"
        embed.set_footer(text=f"Decay Period: {decay_str}")

        try:
            log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID) or await self.bot.fetch_channel(BOT_LOGS_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Failed to log to staff channel: {e}")

        try:
            await channel.send(content=f"⚠️ {member.mention} has been disciplined.", embed=embed, delete_after=120)
        except Exception as e:
            print(f"❌ Failed to log to public channel: {e}")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if self.media_complaint_regex.search(message.content):
            has_lvl_1_4 = message.author.get_role(ROLE_LVL_1_4) is not None
            has_lvl_5_10 = message.author.get_role(ROLE_LVL_5_10) is not None

            if has_lvl_1_4 and not has_lvl_5_10:
                embed = discord.Embed(
                    title="📸 Media Permissions",
                    description=(
                        f"Hey! To post pictures, GIFs, and reactions, you need to reach the "
                        f"<@&{ROLE_LVL_5_10}> role (Level 5).\n\n"
                        f"Head over to <#{BOT_COMMANDS_CH}> and type `/stats` to check your current level!"
                    ),
                    color=discord.Color.from_str("#ffb347") 
                )
                await message.reply(content=message.author.mention, embed=embed)
                return 

        if is_staff(message.author):
            return

        uid = message.author.id
        now = time.time()

        if uid in active_enforcements: return

        # Check if in a relaxed zone
        in_relaxed_zone = False
        if hasattr(message.channel, 'category_id') and message.channel.category_id in RELAXED_CATEGORIES:
            in_relaxed_zone = True

        filtered, reason = self._is_filtered(message, in_relaxed_zone)
        self.cache[uid] = [m for m in self.cache[uid] if now - m.created_at.timestamp() < SPAM_WINDOW]
        
        # Pass `uid` into `_is_spam` so it can check `caps_history`
        spam_detected, spam_reason = self._is_spam(uid, self.cache[uid], message) if not filtered else (False, "")

        if not (filtered or spam_detected):
            self.cache[uid].append(message)
            return

        active_enforcements.add(uid)
        try:
            reason_final = reason if filtered else spam_reason
            punishments = await recent_punishments(uid)
            offense_num = len(punishments) + 1
            
            # Cyclic 1-8 logic
            effective_offense = ((offense_num - 1) % 8) + 1
            
            offending_messages = [message] 
            trigger_content = message.content or ""

            try: 
                await message.delete()
            except: 
                pass

            escalations = {1: "Warning", 2: "Warning", 3: "5m Mute", 4: "10m Mute", 5: "15m Mute", 6: "30m Mute", 7: "1hr Mute", 8: "1D Mute"}
            next_action = escalations.get((offense_num % 8) + 1)
            
            await message.channel.send(
                f"⚠️ {message.author.mention}, removed for **{reason_final}**. (Offense #{offense_num}). Next: {next_action}", 
                delete_after=8
            )

            await self._log_action(message.author, message.channel, reason_final, offending_messages, offense_num)

            # Cycle Logic execution
            if effective_offense in [1, 2]:
                await record_punishment(uid, self.bot.user.id, "warn", reason_final, None, "AutoMod", trigger_content)
            elif effective_offense == 3: await self._mute_user(message.author, 300, reason_final, trigger_content)
            elif effective_offense == 4: await self._mute_user(message.author, 600, reason_final, trigger_content)
            elif effective_offense == 5: 
                await self._mute_user(message.author, 900, reason_final, trigger_content)
                
                # --- NEW: 5th Offense Staff Notification ---
                try:
                    notify_channel = self.bot.get_channel(STAFF_NOTIFY_CHANNEL_ID) or await self.bot.fetch_channel(STAFF_NOTIFY_CHANNEL_ID)
                    if notify_channel:
                        notify_embed = discord.Embed(
                            title="⚠️ High Violation Alert",
                            description=f"**{message.author.mention} (`{message.author.id}`) has reached their 5th offense!**\nStaff should consider reaching out to this user regarding their behavior.",
                            color=discord.Color.dark_red(),
                            timestamp=datetime.utcnow()
                        )
                        notify_embed.set_thumbnail(url=message.author.display_avatar.url)
                        
                        # Build history lines
                        history_lines = [f"**Current (5):** {reason_final}"]
                        for i, p in enumerate(punishments[:4], start=1):
                            p_reason = p.get("reason", "Unknown")
                            ts = p.get("timestamp")
                            ts_str = f"<t:{int(ts.replace(tzinfo=timezone.utc).timestamp())}:R>" if isinstance(ts, datetime) else "Unknown"
                            history_lines.append(f"**Prev {5-i}:** {p_reason} ({ts_str})")
                            
                        # Reverse list so the oldest shows first, newest at the bottom
                        history_lines.reverse()
                        notify_embed.add_field(name="Violation History", value="\n".join(history_lines), inline=False)
                        
                        await notify_channel.send(content=f"<@&{STAFF_TEAM_ROLE_ID}>", embed=notify_embed)
                except Exception as e:
                    print(f"❌ Failed to send 5th offense notification: {e}")
                # -------------------------------------------

            elif effective_offense == 6: await self._mute_user(message.author, 1800, reason_final, trigger_content)
            elif effective_offense == 7: await self._mute_user(message.author, 3600, reason_final, trigger_content)
            elif effective_offense == 8: await self._mute_user(message.author, 86400, reason_final, trigger_content)

            self.cache[uid].clear()
        finally:
            active_enforcements.discard(uid)


# =========================
# Cleanup Task
# =========================

async def cleanup_expired_punishments_task():
    while True:
        try:
            now = datetime.utcnow()
            res = await punish_col().delete_many({"expiresAt": {"$ne": None, "$lte": now}})
            if res.deleted_count:
                print(f"🧹 Cleaned {res.deleted_count} expired punishments")
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
        await asyncio.sleep(3600)


# =========================
# User Interface (UI) Components
# =========================

class ConfirmClearAllView(discord.ui.View):
    def __init__(self, target_user: discord.User, author_id: int):
        super().__init__(timeout=60)
        self.target_user = target_user
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Clear ALL", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Fetch the data before we wipe it out so we can log it
        entries = await all_punishments(self.target_user.id)
        
        # 2. Wipe the punishments
        count = await delete_all_punishments(self.target_user.id)
        
        # 3. Log to staff channel
        try:
            log_channel = interaction.client.get_channel(BOT_LOGS_CHANNEL_ID) or await interaction.client.fetch_channel(BOT_LOGS_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🧹 ALL Punishments Cleared",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="👤 Target User", value=f"{self.target_user.mention}\n`{self.target_user.id}`", inline=True)
                embed.add_field(name="🛡️ Cleared By", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
                embed.add_field(name="🗑️ Amount Cleared", value=f"**{count}** punishments", inline=False)
                
                # Format the history into the embed description
                if entries:
                    history_lines = []
                    # Limit to the most recent 15 to prevent hitting the 4000 character limit for embed descriptions
                    for i, entry in enumerate(entries[:15], start=1):
                        reason = entry.get("reason", "Unknown")
                        msg_content = entry.get("messageContent", "")
                        ts = entry.get("timestamp")
                        
                        ts_str = "Unknown"
                        if isinstance(ts, datetime):
                            ts_unix = int(ts.replace(tzinfo=timezone.utc).timestamp())
                            ts_str = f"<t:{ts_unix}:d>"
                            
                        # Format the content preview gracefully
                        content_preview = ""
                        if msg_content:
                            formatted_content = msg_content[:120] + "..." if len(msg_content) > 120 else msg_content
                            content_preview = f" \n> `{formatted_content}`"
                            
                        history_lines.append(f"**{i}.** [{ts_str}] **{reason}**{content_preview}")
                        
                    if len(entries) > 15:
                        history_lines.append(f"\n*...and {len(entries) - 15} more.*")
                        
                    embed.description = "**Cleared History:**\n" + "\n".join(history_lines)

                await log_channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Failed to send clear all log: {e}")

        await interaction.response.edit_message(content=f"Successfully cleared all {count} punishment(s) from {self.target_user.mention}.", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Action canceled.", view=None, embed=None)


class ConfirmClearView(discord.ui.View):
    def __init__(self, offense_data: dict, target_user: discord.User, author_id: int):
        super().__init__(timeout=60)
        self.offense_data = offense_data
        self.offense_id = str(offense_data["_id"])
        self.target_user = target_user
        self.offense_reason = offense_data.get("reason", "Unknown")
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        success = await delete_offense_by_id(self.offense_id)
        if success:
            # --- LOGGING TO STAFF CHANNEL ---
            try:
                log_channel = interaction.client.get_channel(BOT_LOGS_CHANNEL_ID) or await interaction.client.fetch_channel(BOT_LOGS_CHANNEL_ID)
                if log_channel:
                    embed = discord.Embed(
                        title="🧹 Punishment Cleared",
                        color=discord.Color.green(),
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="👤 Target User", value=f"{self.target_user.mention}\n`{self.target_user.id}`", inline=True)
                    embed.add_field(name="🛡️ Cleared By", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=True)
                    
                    ts = self.offense_data.get("timestamp")
                    if isinstance(ts, datetime):
                        ts_unix = int(ts.replace(tzinfo=timezone.utc).timestamp())
                        ts_str = f"<t:{ts_unix}:f>"
                    else:
                        ts_str = "Unknown"
                        
                    embed.add_field(name="📝 Original Reason", value=self.offense_reason, inline=False)
                    embed.add_field(name="📅 Original Date", value=ts_str, inline=True)
                    
                    msg_content = self.offense_data.get("messageContent")
                    if msg_content:
                        formatted_content = msg_content[:1020] + "..." if len(msg_content) > 1020 else msg_content
                        embed.add_field(name="💬 Message Content", value=f"`{formatted_content}`", inline=False)

                    await log_channel.send(embed=embed)
            except Exception as e:
                print(f"❌ Failed to send clear log: {e}")

            await interaction.response.edit_message(content=f"Successfully removed the punishment (`{self.offense_reason}`) from {self.target_user.mention}.", view=None, embed=None)
        else:
            await interaction.response.edit_message(content="Failed to remove punishment. It might have already been deleted.", view=None, embed=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Action canceled.", view=None, embed=None)


class punishmentselect(discord.ui.Select):
    def __init__(self, punishments: list, target_user: discord.User):
        self.target_user = target_user
        self.punishments_data = punishments
        
        options = []
        for i, off in enumerate(punishments[:25], start=1):
            reason = off.get("reason", "Unknown")
            label_text = f"{i}. {reason}"[:100]
            
            ts_str = off["timestamp"].strftime('%B %d, %Y at %I:%M %p')
            
            options.append(discord.SelectOption(
                label=label_text,
                description=ts_str,
                value=str(off["_id"])
            ))
            
        super().__init__(placeholder="Choose a punishment to delete...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        selected_offense = next((o for o in self.view.punishments if str(o["_id"]) == selected_id), {})
        reason = selected_offense.get("reason", "Unknown")
        
        # Pass the entire selected_offense dictionary so the logging view has full context
        confirm_view = ConfirmClearView(selected_offense, self.target_user, interaction.user.id)
        await interaction.response.edit_message(
            content=f"Are you sure you want to delete this punishment for {self.target_user.mention}?\n**Reason:** `{reason}`",
            embed=None,
            view=confirm_view
        )

class punishmentselectView(discord.ui.View):
    def __init__(self, punishments: list, target_user: discord.User, author: discord.Member):
        super().__init__(timeout=60)
        self.punishments = punishments
        self.author_id = author.id
        self.target_user = target_user
        
        # Add the dropdown
        self.add_item(punishmentselect(punishments, target_user))
        
        # If the user has permission, add the "Clear All" button below the dropdown
        if can_clear_all(author):
            clear_all_btn = discord.ui.Button(label="Clear ALL Punishments", style=discord.ButtonStyle.danger, row=1)
            clear_all_btn.callback = self.clear_all_callback
            self.add_item(clear_all_btn)

    async def clear_all_callback(self, interaction: discord.Interaction):
        confirm_view = ConfirmClearAllView(self.target_user, self.author_id)
        await interaction.response.edit_message(
            content=f"Are you sure you want to delete **ALL** punishments for {self.target_user.mention}? This action cannot be undone.",
            embed=None,
            view=confirm_view
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

# =========================
# Commands
# =========================

class AutoModCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _staff(self, m: discord.Member) -> bool:
        return is_staff(m)

    @app_commands.command(name="punishments", description="Check punishments for a user.")
    @app_commands.describe(silent="Whether to send the response ephemerally (only visible to you).")
    async def punishments(self, interaction: discord.Interaction, user: Optional[discord.User] = None, silent: bool = False):
        viewer = interaction.user
        if not self._staff(viewer):
            user = viewer
        elif user is None:
            await interaction.response.send_message("Please specify a user.", ephemeral=True)
            return

        entries = await all_punishments(user.id)
        if not entries:
            await interaction.response.send_message(f"{user.display_name} has no punishments.", ephemeral=silent)
            return

        embed = discord.Embed(
            title=f"Punishment Log for {user.display_name}",
            description=f"Total: {len(entries)} punishment(s)",
            color=discord.Color.orange()
        )
        for i, entry in enumerate(entries[:20], start=1):
            ts = entry["timestamp"]
            reason = entry.get("reason", "Unknown")
            issuer_id = entry.get("issuerId")
            expires = entry.get("expiresAt")
            
            msg_content = entry.get("messageContent", "")
            
            # Format the Staff field as a mention
            issuer_mention = f"<@{issuer_id}>" if issuer_id else "Unknown"
            
            # Use Discord timestamp markdown for the event time
            if isinstance(ts, datetime):
                ts_unix = int(ts.replace(tzinfo=timezone.utc).timestamp())
                ts_display = f"<t:{ts_unix}:f>"
            else:
                ts_display = str(ts)

            if isinstance(expires, datetime):
                expires_unix = int(expires.replace(tzinfo=timezone.utc).timestamp())
                expires_str = f"<t:{expires_unix}:F> (<t:{expires_unix}:R>)"
            else:
                expires_str = "Never"

            field_value = f"**Reason:** {reason}\n**Staff:** {issuer_mention}\n**Expires:** {expires_str}"
            if msg_content:
                formatted_content = msg_content[:150] + "..." if len(msg_content) > 150 else msg_content
                field_value += f"\n**Content:** `{formatted_content}`"

            embed.add_field(
                name=f"{i}. {ts_display}",
                value=field_value,
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=silent)

    @app_commands.command(name="clearpunishment", description="Remove a specific punishment for a user via dropdown (staff only).")
    async def clearpunishment(self, interaction: discord.Interaction, user: discord.User):
        if not self._staff(interaction.user):
            await interaction.response.send_message("You lack permission.", ephemeral=True)
            return
            
        entries = await all_punishments(user.id)
        if not entries:
            await interaction.response.send_message(f"{user.display_name} has no punishments to clear.", ephemeral=True)
            return

        context_lines = []
        for i, entry in enumerate(entries[:25], start=1):
            reason = entry.get("reason", "Unknown")
            msg_content = entry.get("messageContent", "")
            content_preview = f" \n> `{msg_content[:100]}...`" if msg_content else ""
            context_lines.append(f"**{i}.** {reason}{content_preview}")
            
        context_embed = discord.Embed(
            title=f"Punishments Context for {user.display_name}",
            description="\n".join(context_lines),
            color=discord.Color.from_rgb(44, 47, 51)
        )

        view = punishmentselectView(entries, user, interaction.user)
        await interaction.response.send_message(
            f"Select a punishment to remove from {user.mention}:", 
            embed=context_embed, 
            view=view, 
            ephemeral=True
        )

    # --- ALL-IN-ONE AUTOMOD COMMAND ---
    @app_commands.command(name="automod", description="Manage the AutoMod word blacklist.")
    @app_commands.describe(
        action="The action to perform: add, remove, or list",
        word="The word to add or remove (leave blank if selecting 'list')"
    )
    async def automod_cmd(self, interaction: discord.Interaction, action: Literal["add", "remove", "list"], word: Optional[str] = None):
        
        # Access control: Add/Remove require Admin privileges
        if action in ["add", "remove"] and not is_admin(interaction.user):
            return await interaction.response.send_message("❌ Administrative privileges required.", ephemeral=True)

        # Ensure word is provided if they are trying to add or remove
        if action in ["add", "remove"]:
            if not word:
                return await interaction.response.send_message("❌ You must provide a word to add or remove.", ephemeral=True)
            word = word.lower().strip()

        # Handle "add" logic
        if action == "add":
            if not os.path.exists(FILTER_FILE):
                words = []
            else:
                with open(FILTER_FILE, "r") as f:
                    words = json.load(f)
                    
            if word in words:
                return await interaction.response.send_message(f"⚠️ `{word}` is already in the blacklist.", ephemeral=True)
                
            words.append(word)
            with open(FILTER_FILE, "w") as f:
                json.dump(words, f)
                
            automod_cog = interaction.client.get_cog("AutoMod")
            if automod_cog:
                automod_cog.bad_words = automod_cog._load_filter()
                
            await interaction.response.send_message(f"✅ Successfully added `{word}` to the blacklist.", ephemeral=True)

        # Handle "remove" logic
        elif action == "remove":
            if not os.path.exists(FILTER_FILE):
                return await interaction.response.send_message("⚠️ The blacklist is currently empty.", ephemeral=True)
                
            with open(FILTER_FILE, "r") as f:
                words = json.load(f)
                
            if word not in words:
                return await interaction.response.send_message(f"⚠️ `{word}` is not in the blacklist.", ephemeral=True)
                
            words.remove(word)
            with open(FILTER_FILE, "w") as f:
                json.dump(words, f)
                
            automod_cog = interaction.client.get_cog("AutoMod")
            if automod_cog:
                automod_cog.bad_words = automod_cog._load_filter()
                
            await interaction.response.send_message(f"✅ Successfully removed `{word}` from the blacklist.", ephemeral=True)

        # Handle "list" logic
        elif action == "list":
            if not os.path.exists(FILTER_FILE):
                return await interaction.response.send_message("The blacklist is currently empty.", ephemeral=True)
                
            with open(FILTER_FILE, "r") as f:
                words = json.load(f)
                
            if not words:
                return await interaction.response.send_message("The blacklist is currently empty.", ephemeral=True)
                
            words.sort()
            word_list = "\n".join(f"• `{w}`" for w in words)
            
            # Handle Discord's 4096 character embed description limit
            if len(word_list) > 4000:
                word_list = word_list[:4000] + "\n... (List truncated)"
                
            embed = discord.Embed(title="AutoMod Blacklist", description=word_list, color=discord.Color.blue())
            embed.set_footer(text=f"Total Words: {len(words)}")
            
            # List can be sent publicly or ephemerally; currently defaults to public but only the command invoker will trigger it
            await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# Setup
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
    await bot.add_cog(AutoModCommands(bot))
    asyncio.create_task(cleanup_expired_punishments_task())