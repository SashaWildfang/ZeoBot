import discord
from discord.ext import commands
import random
import asyncio
from datetime import datetime, timedelta
from db.database import get_connection  # MongoDB

# ===============================
# ⚙️ Configuration
# ===============================

ALLOWED_CHANNELS = {
    1358452494660796448,  # SFW
    1358487735811182682,  # NSFW
}

WORD_FILE = "word_scramble.txt"

REWARD_XP = 250
REWARD_LEAVES = 125

EVENT_DURATION = 120        # time to guess/type (2 minutes)
EVENT_CHANCE = 0.02         # 2% chance per message
CHANNEL_COOLDOWN = 300      # 5 minutes

# --- NEW: Activity Tracking ---
MIN_ACTIVE_USERS = 2        # Minimum unique users chatting to trigger an event
CHATTER_TIMEOUT = 60        # Seconds before a user is removed from active chatters


# ===============================
# 🔤 Chat Minigames (Scramble & Fast Typer)
# ===============================

class ChatEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.db = get_connection()
        self.users_col = self.db["users"]   # unified schema: _id = discordId

        self.active_events = {}  # {channel_id: {...}}
        self.cooldowns = {}      # {channel_id: datetime}
        self.streaks = {}        # {channel_id: {"user_id": int, "streak": int}}
        
        # Tracks active chatters: {channel_id: {user_id: timestamp_float}}
        self.recent_chatters = {} 

    # -----------------------------------
    # 🔁 Word Helpers
    # -----------------------------------

    def scramble_word(self, word: str):
        """Shuffle word but ensure it's not identical to the original."""
        letters = list(word)
        while True:
            random.shuffle(letters)
            scrambled = ''.join(letters)
            if scrambled.lower() != word.lower():
                return scrambled

    def get_hint_line(self, word: str):
        """Generates a blank line of underscores with no letters revealed."""
        if not word:
            return ""
        hint = " ".join("_" for _ in word)
        return f"`{hint}`"

    def format_duration(self, seconds: int):
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s" if m else f"{s}s"

    # -----------------------------------
    # 🧠 Auto Trigger Logic
    # -----------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot:
            return

        channel_id = message.channel.id

        if channel_id not in ALLOWED_CHANNELS:
            return

        if channel_id in self.active_events:
            return  # an event is already active

        now = datetime.utcnow()
        now_ts = now.timestamp()

        # --- 1. Track Recent Chatters ---
        if channel_id not in self.recent_chatters:
            self.recent_chatters[channel_id] = {}
            
        # Log this user's latest message time
        self.recent_chatters[channel_id][message.author.id] = now_ts
        
        # Clean up users who haven't spoken in the last CHATTER_TIMEOUT seconds
        self.recent_chatters[channel_id] = {
            uid: ts for uid, ts in self.recent_chatters[channel_id].items() 
            if now_ts - ts <= CHATTER_TIMEOUT
        }
        
        # Check if we meet the minimum active users requirement
        if len(self.recent_chatters[channel_id]) < MIN_ACTIVE_USERS:
            return 

        # --- 2. Channel cooldown check ---
        last_trigger = self.cooldowns.get(channel_id)
        if last_trigger and (now - last_trigger).total_seconds() < CHANNEL_COOLDOWN:
            return

        # --- 3. Random chance ---
        if random.random() > EVENT_CHANCE:
            return

        # Passed → TRIGGER EVENT
        self.cooldowns[channel_id] = now
        asyncio.create_task(self._trigger_event(message.channel))

    # -----------------------------------
    # 🎮 Manual Trigger
    # -----------------------------------
    async def manual_event(self, channel):
        if isinstance(channel, int):
            channel = self.bot.get_channel(channel)

        if not isinstance(channel, discord.TextChannel):
            raise TypeError("manual_event requires a TextChannel")

        if channel.id in self.active_events:
            return

        self.cooldowns[channel.id] = datetime.utcnow()
        asyncio.create_task(self._trigger_event(channel))

    # -----------------------------------
    # 🔤 Event Core (Handles both Types)
    # -----------------------------------
    async def _trigger_event(self, channel: discord.TextChannel):
        try:
            with open(WORD_FILE, "r") as f:
                words = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            await channel.send("❌ Missing `word_scramble.txt` file.")
            return

        word = random.choice(words)
        event_type = random.choice(["scramble", "fast_type"])
        start_time = datetime.utcnow()

        # Build the specific embed based on the chosen event
        if event_type == "scramble":
            scrambled = self.scramble_word(word)
            hint = self.get_hint_line(word)
            spaced_scrambled = " ".join(scrambled.upper())
            
            embed = discord.Embed(
                title="🍂 A gust of autumn wind scattered these letters!",
                description=(
                    f"Quick! Unscramble them before they blow away:\n\n"
                    f"🍁 *` {spaced_scrambled} `*\n"
                    f"💡 Hint: {hint} *({len(word)} letters)*\n\n"
                    f"⏳ *You have **{EVENT_DURATION // 60} minutes** before they vanish!*"
                ),
                color=discord.Color.from_rgb(210, 105, 30), # Autumn Orange / Chocolate
                timestamp=start_time
            )
        else:
            embed = discord.Embed(
                title="🍃 Catch the falling leaf!",
                description=(
                    f"Quick! Be the first to type this exact word to catch it before it hits the ground:\n\n"
                    f"🔤 **`{word.upper()}`**\n\n"
                    f"⏳ *You have **{EVENT_DURATION // 60} minutes** before it blows away!*"
                ),
                color=discord.Color.from_rgb(218, 165, 32), # Goldenrod / Autumn Yellow
                timestamp=start_time
            )

        msg = await channel.send(embed=embed)

        self.active_events[channel.id] = {
            "word": word.lower(),
            "type": event_type,
            "start": start_time,
            "message": msg
        }

        def check(m: discord.Message):
            return (
                m.channel.id == channel.id
                and not m.author.bot
                and m.content.lower().strip() == word.lower()
            )

        try:
            guess_msg = await self.bot.wait_for("message", timeout=EVENT_DURATION, check=check)

            if channel.id in self.active_events:
                del self.active_events[channel.id]

            try:
                # Rolling List Fix to prevent double logging of deleted messages
                if not hasattr(self.bot, "ignored_deletes"):
                    self.bot.ignored_deletes = []
                self.bot.ignored_deletes.append(guess_msg.id)
                if len(self.bot.ignored_deletes) > 50:
                    self.bot.ignored_deletes.pop(0)

                await guess_msg.delete()
            except discord.Forbidden:
                pass  
            except discord.HTTPException:
                pass  

            elapsed = (datetime.utcnow() - start_time).total_seconds()

            # Award XP safely
            try:
                if hasattr(self.bot, "leveling") and hasattr(self.bot.leveling, "add_xp"):
                    # This call matches your new LevelManager.add_xp(member, xp, balance_gain)
                    await self.bot.leveling.add_xp(guess_msg.author, REWARD_XP, balance_gain=REWARD_LEAVES)
                else:
                    # Fallback: Manually update using the CORRECT key "discordId"
                    await self.users_col.update_one(
                        {"discordId": guess_msg.author.id}, 
                        {"$inc": {"balance": REWARD_LEAVES, "xp": REWARD_XP}},
                        upsert=True
                    )
            except Exception as e:
                print(f"[ChatEvents] Payout Error: {e}")

            # -------------------------------
            # 🔥 STREAK LOGIC (Fall Themed!)
            # -------------------------------
            streak_text = ""
            current_streak = self.streaks.get(channel.id)

            if current_streak:
                if current_streak["user_id"] == guess_msg.author.id:
                    # Continuing the streak
                    current_streak["streak"] += 1
                    streak_text = f"\n\n🔥 **AUTUMN BLAZE!** {guess_msg.author.mention} has won **{current_streak['streak']}** times in a row!"
                else:
                    # Broke the streak
                    old_user_id = current_streak["user_id"]
                    old_streak = current_streak["streak"]
                    if old_streak >= 2:
                        streak_text = f"\n\n🌬️ **GUST OF WIND!**\n{guess_msg.author.mention} just broke <@{old_user_id}>'s streak of **{old_streak}**!"
                    
                    # Reset to new winner
                    self.streaks[channel.id] = {"user_id": guess_msg.author.id, "streak": 1}
            else:
                # First time setting a streak here
                self.streaks[channel.id] = {"user_id": guess_msg.author.id, "streak": 1}

            # -------------------------------
            win_title = "🍁 Scramble Solved!" if event_type == "scramble" else "🍃 Leaf Caught!"
            
            win_embed = discord.Embed(
                title=win_title,
                description=(
                    f"The word was **`{word.upper()}`**!\n\n"
                    f"🏆 **Winner:** {guess_msg.author.mention} *(in {self.format_duration(elapsed)})*\n"
                    f"🎁 **Reward:** `+{REWARD_XP} ✨` & `+{REWARD_LEAVES} <:leaf:1524758896659660831>`"
                    f"{streak_text}\n\n"
                    f"_*(This message will disappear in 10 seconds)*_"
                ),
                color=discord.Color.from_rgb(139, 69, 19), # Saddle Brown
                timestamp=datetime.utcnow()
            )
            win_embed.set_thumbnail(url=guess_msg.author.display_avatar.url)

            await msg.edit(embed=win_embed)
            
            try:
                await msg.delete(delay=10.0)
            except discord.HTTPException:
                pass

        except asyncio.TimeoutError:
            if channel.id in self.active_events:
                del self.active_events[channel.id]

            # If nobody guesses it, the reigning champion's streak is lost!
            lost_streak_text = ""
            old_streak = self.streaks.pop(channel.id, None)
            if old_streak and old_streak["streak"] >= 2:
                lost_streak_text = f"\n\n🍂 <@{old_streak['user_id']}>'s streak of **{old_streak['streak']}** was lost to the wind!"

            fail_embed = discord.Embed(
                title="💨 Blown Away! (Time's Up)",
                description=(
                    f"The autumn wind picked up and carried the word away...\n"
                    f"The correct word was: **`{word.upper()}`**"
                    f"{lost_streak_text}\n\n"
                    f"_*(This message will disappear in 10 seconds)*_"
                ),
                color=discord.Color.from_rgb(139, 0, 0), # Dark Red
                timestamp=datetime.utcnow()
            )

            await msg.edit(embed=fail_embed)
            
            try:
                await msg.delete(delay=10.0)
            except discord.HTTPException:
                pass
            
        except Exception as e:
            print(f"[ChatEvents] Unexpected error: {e}")
            if channel.id in self.active_events:
                del self.active_events[channel.id]

    def cog_unload(self):
        self.active_events.clear()
        self.cooldowns.clear()
        self.streaks.clear()
        self.recent_chatters.clear()

# ===============================
# ⚙️ Setup
# ===============================
async def setup(bot):
    await bot.add_cog(ChatEvents(bot))