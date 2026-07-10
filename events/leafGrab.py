import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import random
import time  # <-- Added time to track how fast they clicked

from db.database import get_connection  # This should return an AsyncIOMotorDatabase object

LEAF_MIN = 50
LEAF_MAX = 100
EVENT_CHECK_INTERVAL = 60
EVENT_CHANCE = 0.05
CLAIM_TIMEOUT = 60

# --- NEW: Activity Tracking ---
MIN_ACTIVE_USERS = 2        # Minimum unique users chatting to trigger an event
CHATTER_TIMEOUT = 60        # Seconds before a user is removed from active chatters

# Categories to IGNORE
EXCLUDED_CATEGORIES = {
    1358485130242560020, 1358486463251091569, 1362459990245245151,
    1362461644768411758, 1448247633574363237, 1358487125661585658, 1358485995649237103
}

class LeafGrab(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Tracks active chatters: {channel_id: {user_id: timestamp_float}}
        self.recent_chatters = {} 
        self.event_loop.start()

    def cog_unload(self):
        self.event_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots, DMs, and excluded categories
        if message.author.bot or not message.guild:
            return
        
        if message.channel.category_id in EXCLUDED_CATEGORIES:
            return

        channel_id = message.channel.id

        # Initialize the channel tracker if it doesn't exist
        if channel_id not in self.recent_chatters:
            self.recent_chatters[channel_id] = {}

        # Log this user's latest message time
        self.recent_chatters[channel_id][message.author.id] = time.time()

    @tasks.loop(seconds=EVENT_CHECK_INTERVAL)
    async def event_loop(self):
        if not self.recent_chatters:
            return

        now_ts = time.time()
        eligible_channels = []
        
        # We use list() to avoid "dictionary changed size during iteration" error
        for channel_id, users in list(self.recent_chatters.items()):
            # Clean up users who haven't spoken in the last CHATTER_TIMEOUT seconds
            active_users = {uid: ts for uid, ts in users.items() if now_ts - ts <= CHATTER_TIMEOUT}
            
            # Save the cleaned-up dictionary back
            self.recent_chatters[channel_id] = active_users

            # Check if we meet the minimum active users requirement
            if len(active_users) >= MIN_ACTIVE_USERS:
                eligible_channels.append(channel_id)
            elif not active_users:
                # If no one is active anymore, remove the channel from tracking to save memory
                del self.recent_chatters[channel_id]

        if not eligible_channels:
            return

        # Roll for event globally across all eligible channels
        if random.random() < EVENT_CHANCE:
            target_id = random.choice(eligible_channels)
            channel = self.bot.get_channel(target_id)
            if channel:
                await self.spawn_leaf(channel)

    async def spawn_leaf(self, channel: discord.TextChannel):
        amount = random.randint(LEAF_MIN, LEAF_MAX)
        embed = discord.Embed(
            title="🍃 A Leaf Blew In!",
            description=f"Quick, first to react with <:leaf:1524758896659660831> catches it for **{amount} Leaves**!",
            color=discord.Color.from_rgb(34, 139, 34), # Forest Green
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="You have 60s before it blows away")

        try:
            event_msg = await channel.send(embed=embed)
            await event_msg.add_reaction("<:leaf:1524758896659660831>")
        except discord.Forbidden:
            return # Bot can't send messages or reactions here

        # Record the exact time the event started
        start_time = time.time()

        def check(reaction, user):
            return (
                reaction.message.id == event_msg.id and
                str(reaction.emoji) == "<:leaf:1524758896659660831>" and
                not user.bot
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=CLAIM_TIMEOUT, check=check)
            
            # Calculate how many seconds it took to click
            elapsed_time = time.time() - start_time
            
            # --- Success Logic ---
            claimed_embed = discord.Embed(
                title="🍂 Leaf was caught!",
                description=f"{user.mention} swooped in and caught **{amount} <:leaf:1524758896659660831>** in **{elapsed_time:.1f}s**!",
                color=discord.Color.from_rgb(32, 178, 170), # Light Sea Green
                timestamp=datetime.utcnow()
            )
            await event_msg.edit(embed=claimed_embed)
            
            try:
                await event_msg.clear_reactions()
            except discord.Forbidden:
                pass
            
            # Update Database
            try:
                db = get_connection()
                if db is not None:
                    await db["users"].update_one(
                        {"discordId": user.id},
                        {"$inc": {"balance": amount}},
                        upsert=True
                    )
            except Exception as e:
                print(f"❌ DB Update Error: {e}")

        except asyncio.TimeoutError:
            expired_embed = discord.Embed(
                title="💨 The Leaf Blew Away...",
                description="It carried off in the wind before anyone could grab it!",
                color=discord.Color.from_rgb(112, 128, 144), # Slate Gray
                timestamp=datetime.utcnow()
            )
            await event_msg.edit(embed=expired_embed)
            try: 
                await event_msg.clear_reactions()
            except: 
                pass

        # Cleanup message after 20 seconds
        await asyncio.sleep(20)
        try:
            await event_msg.delete()
        except:
            pass

async def setup(bot):
    await bot.add_cog(LeafGrab(bot))