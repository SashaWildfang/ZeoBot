import discord
from discord.ext import commands
import random
import asyncio
from datetime import datetime, timedelta

SFW_CHANNEL_ID = 1358452494660796448
NSFW_CHANNEL_ID = 1358487735811182682
REWARD_XP = 100
REWARD_BUTTERFLIES = 100
SCRAMBLE_DURATION = 120  # 2 minutes
TRIGGER_WINDOW_SECONDS = 120
MIN_UNIQUE_USERS = 2
WORD_FILE = "word_scramble.txt"

class WordScramble(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_scramble = {}
        self.active_scramble = {}

    def scramble_word(self, word):
        word_list = list(word)
        while True:
            random.shuffle(word_list)
            scrambled = ''.join(word_list)
            if scrambled != word:
                return scrambled

    def format_duration(self, seconds):
        minutes, seconds = divmod(int(seconds), 60)
        return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in [SFW_CHANNEL_ID, NSFW_CHANNEL_ID]:
            return
        if message.channel.id in self.active_scramble:
            return

        now = datetime.utcnow()
        if self.last_scramble.get(message.channel.id):
            delta = (now - self.last_scramble[message.channel.id]).total_seconds()
            if delta < 180:
                return

        # Check if chat is active (at least 3 unique users in last 5 messages within 20s)
        history = [message] + [msg async for msg in message.channel.history(limit=4)]
        recent_msgs = [msg for msg in history if (now - msg.created_at).total_seconds() <= TRIGGER_WINDOW_SECONDS]
        unique_users = set(msg.author.id for msg in recent_msgs if not msg.author.bot)

        if len(unique_users) < MIN_UNIQUE_USERS:
            return

        self.last_scramble[message.channel.id] = now

        try:
            with open(WORD_FILE, "r") as f:
                words = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print("❌ word_scramble.txt not found.")
            return

        word = random.choice(words)
        scrambled = self.scramble_word(word)

        embed = discord.Embed(
            title="🔤 Word Scramble!",
            description=(
                f"Unscramble this word: **`{scrambled}`**\n"
                f"Type your guess in chat! You have 2 minutes to solve it"
            ),
            color=discord.Color.blue()
        )

        msg = await message.channel.send(embed=embed)

        self.active_scramble[message.channel.id] = {
            "word": word.lower(),
            "start": now,
            "message": msg,
        }

        def check(m: discord.Message):
            return (
                m.channel.id == message.channel.id and
                not m.author.bot and
                m.content.lower().strip() == word.lower()
            )

        try:
            guess = await self.bot.wait_for("message", timeout=SCRAMBLE_DURATION, check=check)
            elapsed = (datetime.utcnow() - now).total_seconds()
            del self.active_scramble[message.channel.id]

            await self.bot.leveling.add_xp(guess.author.id, REWARD_XP)

            conn = self.bot.db.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (user_id, butterflies)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE butterflies = butterflies + %s
                """, (guess.author.id, REWARD_BUTTERFLIES, REWARD_BUTTERFLIES))
            conn.commit()

            await msg.delete()
            win_embed = discord.Embed(
                title="✅ Word Guessed!",
                description=(
                    f"{guess.author.mention} guessed the word **{word}** correctly in {self.format_duration(elapsed)}!\n"
                    f"🎉 They earned **{REWARD_XP} XP** and **{REWARD_BUTTERFLIES} Butterflies**!"
                ),
                color=discord.Color.blue()
            )
            followup = await message.channel.send(embed=win_embed)
            await asyncio.sleep(10)
            await followup.delete()

        except asyncio.TimeoutError:
            del self.active_scramble[message.channel.id]
            await msg.delete()
            fail_embed = discord.Embed(
                title="⌛ Time's Up!",
                description=f"Sorry, nobody guessed the word. The word was **{word}**.",
                color=discord.Color.blue()
            )
            followup = await message.channel.send(embed=fail_embed)
            await asyncio.sleep(10)
            await followup.delete()

async def setup(bot):
    await bot.add_cog(WordScramble(bot))
