import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime, timedelta, timezone
from typing import Literal
from db.database import get_connection

# ==========================================
# CONFIGURATION
# ==========================================
MESSAGE_THRESHOLD = 50       # Number of user messages required to trigger an ad
COOLDOWN_MINUTES = 30        # Minimum minutes between ads in the SAME channel

# Set this to the path of your icon. 
# Note: If you start your bot from the root folder (e.g. `python main.py`), 
# the path is likely just "icon.png" even if this cog is inside an /events folder.
ICON_PATH = "icon.png" 

# Categories where ads will NOT trigger
EXCLUDED_CATEGORIES = [
    1358485995649237103, 
    1362459990245245151, 
    1362461644768411758, 
    1448247633574363237, 
    1358486463251091569, 
    1358485130242560020, 
    1495849806395084862, 
    1499431359284908083
] 

# Specific Channels where ads will NOT trigger
EXCLUDED_CHANNELS = [
    1358487325944057918, 
    1496875154314231828, 
    1496743217390157935, 
    1497237389741920446, 
    1359520996561781009, 
    1358487818057289848, 
    1358487300245295104
]

# ==========================================
# UI COMPONENTS FOR /PLAYAD
# ==========================================
class AdSelect(discord.ui.Select):
    def __init__(self, cog, target_channel):
        self.cog = cog
        self.target_channel = target_channel
        
        options = [
            discord.SelectOption(label="🎲 Random Ad", description="Play a random tip from the pool.", value="random"),
            discord.SelectOption(label="💖 Patreon", description="Advertise supporter perks and link.", value="patreon"),
            discord.SelectOption(label="🚀 Server Boost", description="Advertise Nitro boosting perks.", value="boost"),
            discord.SelectOption(label="⬆️ Disboard Bump", description="Advertise the /bump command and leaderboard.", value="bump"),
            discord.SelectOption(label="🛒 Server Store", description="Advertise the daily/weekly rotating store.", value="store"),
            discord.SelectOption(label="🎰 Slots", description="Advertise the jackpot and slot machines.", value="gambling"),
            discord.SelectOption(label="🃏 Blackjack", description="Advertise the Blackjack tables.", value="blackjack"),
            discord.SelectOption(label="🚀 Crash", description="Advertise the Crash gambling game.", value="crash"),
            discord.SelectOption(label="🆘 Help Command", description="Advertise the /help directory.", value="help"),
            discord.SelectOption(label="⭐ Disboard Review", description="Advertise the 5k Leaves review reward.", value="review"),
            discord.SelectOption(label="🍃 Wordle", description="Advertise the daily Wordle game.", value="wordle"),
            discord.SelectOption(label="📅 Daily Rewards", description="Advertise /daily and Nitro streaks.", value="daily"),
        ]
        super().__init__(placeholder="Choose an advertisement to drop...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_val = self.values[0]
        ad_type_arg = None if selected_val == "random" else selected_val

        channel_id = self.target_channel.id
        last_played = None
        if channel_id in self.cog.channel_activity:
            last_played = self.cog.channel_activity[channel_id].get("last_ad_type")

        # Fetch the embed AND the file from the cog
        ad_embed, new_ad_type, ad_file = await self.cog.get_ad_embed(specific_ad=ad_type_arg, last_played=last_played)
        
        # Edit the original ephemeral message to remove the dropdown and confirm
        await interaction.response.edit_message(
            content=f"✅ Dropped the **{new_ad_type}** tip into {self.target_channel.mention}. (It will auto-delete in 5 minutes)", 
            view=None
        )
        
        now_utc = datetime.now(timezone.utc)
        # --- FIX: Update channel tracking in the cog BEFORE sending ---
        if channel_id not in self.cog.channel_activity:
            self.cog.channel_activity[channel_id] = {"count": 0, "last_ad": now_utc}
            
        self.cog.channel_activity[channel_id]["count"] = 0
        self.cog.channel_activity[channel_id]["last_ad"] = now_utc
        self.cog.channel_activity[channel_id]["last_ad_type"] = new_ad_type
        
        # Send ad to the target channel with the local file and self-delete after 300 seconds (5 minutes)
        await self.target_channel.send(embed=ad_embed, file=ad_file, delete_after=300)

class AdSelectView(discord.ui.View):
    def __init__(self, cog, target_channel: discord.TextChannel, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(AdSelect(cog, target_channel))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

# ==========================================
# MAIN COG
# ==========================================
class AdManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_activity = {}
        self.db = get_connection()
        print("📢 AdManager COG LOADED")

    async def get_ad_embed(self, specific_ad: str = None, last_played: str = None) -> tuple[discord.Embed, str, discord.File]:
        """Selects and builds an advertisement embed, returning the embed, its type, and the local file."""
        ad_options = ["patreon", "boost", "gambling", "bump", "store", "blackjack", "crash", "help", "review", "wordle", "daily"]
        
        # Determine which ad to play
        if specific_ad and specific_ad in ad_options:
            ad_type = specific_ad
        else:
            # Prevent the same ad from playing twice in a row
            if last_played in ad_options:
                ad_options.remove(last_played)
            ad_type = random.choice(ad_options)

        if ad_type == "patreon":
            embed = discord.Embed(
                title="💡 Did you know?",
                description=(
                    "You can basically unlock cheat codes for the server economy by linking up on Patreon.\n\n"
                    "Supporters get a monthly Leaf allowance dropped right into their accounts, plus custom name colors and much more.\n\n"
                    "👉 **[Check out the loot tiers here!](https://www.patreon.com/c/thekittykingdom/membership)**"
                ),
                color=discord.Color.from_str("#F96854") 
            )
            embed.set_footer(text="Ad System - Showing advertisement 1/11")

        elif ad_type == "boost":
            embed = discord.Embed(
                title="💡 Pro Tip: Boost The Server!",
                description=(
                    "Think of a boost as a key: it unlocks a better server for everyone and a list of private perks just for you!\n\n"
                    "Boosters get an exclusive <@&1360260086500561237> role, a shiny badge, and bonus economy payouts. Head to the top of the channel list and hit 'Server Boost' to grab your perks."
                ),
                color=discord.Color.from_str("#F47FFF") 
            )
            embed.set_footer(text="Ad System - Showing advertisement 2/11")

        elif ad_type == "bump":
            embed = discord.Embed(
                title="💡 Did you know?",
                description=(
                    "You get paid **250 <:leaf:1524758896659660831> & 300 ✨** literally just for typing `/bump` in <#1358485820100706314>.\n\n"
                    "You can do this every 2 hours. If you grind it out, you might snipe a top 3 spot on the `/leaderboard Monthly Bumps` and walk away with up to **5,000 <:leaf:1524758896659660831>** at the end of the month."
                ),
                color=discord.Color.from_str("#24b7b7") 
            )
            embed.set_footer(text="Ad System - Showing advertisement 3/11")

        elif ad_type == "store":
            embed = discord.Embed(
                title="💡 Pro Tip: Check the Shop",
                description=(
                    "The server store rotates its stock daily and weekly. If you're hoarding Leaves from chatting and bumping, you're missing out!\n\n"
                    "Type `/store view` to snag rare roles, boosters, and consumables before they cycle out of the shop."
                ),
                color=discord.Color.gold() 
            )
            embed.set_footer(text="Ad System - Showing advertisement 4/11")

        elif ad_type == "gambling":
            # Fetch the live jackpot from MongoDB
            globals_coll = self.db["globals"]
            jackpot_data = await globals_coll.find_one({"_id": "casino_jackpot"})
            jackpot_amount = jackpot_data.get("amount", 100000) if jackpot_data else 100000

            embed = discord.Embed(
                title="🎰 Did you know?",
                description=(
                    "99% of gamblers quit right before they hit the jackpot. (Okay, maybe not, but still).\n\n"
                    f"💰 **Current Progressive Jackpot:** **{jackpot_amount:,} <:leaf:1524758896659660831>**\n\n"
                    "If you've got extra Leaves burning a hole in your pocket, head over to <#1508896560266612756> and try `/slots action:Play`.\n\n"
                    "✨ *Boosters (<@&1360260086500561237>) get the exclusive perk of spinning up to 25 slots at a time!* May RNG be in your favor."
                ),
                color=discord.Color.from_str("#2ecc71") 
            )
            embed.set_footer(text="Ad System - Showing advertisement 5/11")
            
        elif ad_type == "blackjack":
            embed = discord.Embed(
                title="🃏 Pro Tip: Beat the Dealer",
                description=(
                    "Think you can outsmart the house? Hit the tables with `/blackjack action:Play` in <#1508896560266612756>.\n\n"
                    "Blackjack pays out a clean **3:2**, but be careful—all losing wagers are fed directly into the server's Progressive Jackpot!\n\n"
                    "Play smart, stand on 17, and don't let the dealer take your Leaves."
                ),
                color=discord.Color.dark_green() 
            )
            embed.set_footer(text="Ad System - Showing advertisement 6/11")
            
        elif ad_type == "crash": 
            embed = discord.Embed(
                title="🚀 Did you know?",
                description=(
                    "You can turn a pocketful of Leaves into thousands... if you pull out in time.\n\n"
                    "Type `/crash action:Play` in <#1508896560266612756> to watch the multiplier skyrocket. Will you cash out early for the safe money, or hold on for the massive 100x max win?\n\n"
                    "Don't let it explode! 💥"
                ),
                color=discord.Color.brand_red() 
            )
            embed.set_footer(text="Ad System - Showing advertisement 7/11")

        elif ad_type == "help":
            embed = discord.Embed(
                title="🆘 Need Help?",
                description=(
                    "Lost or confused? Don't worry, we've got you covered!\n\n"
                    "Use the `/help` command anywhere in the server to pull up an interactive directory of all our available commands, categories, and features.\n\n"
                    "If you still need assistance, don't hesitate to reach out to a staff member!"
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Ad System - Showing advertisement 8/11")

        elif ad_type == "review":
            embed = discord.Embed(
                title="⭐ Earn 5,000 Leaves!",
                description=(
                    "Want an easy boost to your balance? Rate our server 5 stars and leave an honest review on Disboard!\n\n"
                    "**[Review Kitty Kingdom Here](https://disboard.org/server/1358452494128250940)**\n\n"
                    "Once you've submitted your review, simply open a ticket in <#1495841072423899276> with a screenshot of your review to claim your **5,000 <:leaf:1524758896659660831>** reward!"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="Ad System - Showing advertisement 9/11")

        elif ad_type == "wordle":
            embed = discord.Embed(
                title="🍃 Play the Daily Wordle!",
                description=(
                    "Love word games? You can play our custom Daily Wordle right here in the server!\n\n"
                    "Head over to <#1358485820100706314> and run `/wordle` to try and guess the word of the day.\n\n"
                    "Solving the puzzle scores you a sweet **300 <:leaf:1524758896659660831> and 300 🌟**! You can play once every 24 hours."
                ),
                color=discord.Color.brand_green()
            )
            embed.set_footer(text="Ad System - Showing advertisement 10/11")

        elif ad_type == "daily":
            embed = discord.Embed(
                title="📅 Claim your Daily Rewards!",
                description=(
                    "Don't leave free money on the table! Use the `/daily` command every day to claim your free Leaves.\n\n"
                    "✨ **Want to earn even more?** Server Boosters (<@&1360260086500561237>) unlock exclusive access to **Daily Streaks**, multiplying your daily earnings every consecutive day you claim!"
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="Ad System - Showing advertisement 11/11")

        # Load the local file and attach it to the embed via "attachment://"
        file = discord.File(ICON_PATH, filename="icon.png")
        embed.set_thumbnail(url="attachment://icon.png")

        return embed, ad_type, file

    @app_commands.command(name="playad", description="Admin: Manually play a tip/ad in the current channel via a dropdown menu.")
    @app_commands.default_permissions(administrator=True)
    async def playad(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            
        view = AdSelectView(cog=self, target_channel=interaction.channel, author_id=interaction.user.id)
        
        await interaction.response.send_message(
            "Select which tip/advertisement you want to drop in this channel:", 
            view=view, 
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return
            
        if message.channel.category_id in EXCLUDED_CATEGORIES or message.channel.id in EXCLUDED_CHANNELS:
            return

        channel_id = message.channel.id
        now = datetime.now(timezone.utc)

        if channel_id not in self.channel_activity:
            self.channel_activity[channel_id] = {
                "count": 0,
                "last_ad": now - timedelta(days=1),
                "last_ad_type": None
            }

        self.channel_activity[channel_id]["count"] += 1

        count = self.channel_activity[channel_id]["count"]
        last_ad = self.channel_activity[channel_id]["last_ad"]
        last_ad_type = self.channel_activity[channel_id]["last_ad_type"]

        if count >= MESSAGE_THRESHOLD:
            time_since_last_ad = (now - last_ad).total_seconds() / 60.0

            if time_since_last_ad >= COOLDOWN_MINUTES:
                try:
                    # Unpack the file object alongside the embed and ad_type
                    ad_embed, new_ad_type, ad_file = await self.get_ad_embed(last_played=last_ad_type)
                    
                    # --- FIX: Reset the tracker BEFORE awaiting the send ---
                    self.channel_activity[channel_id]["count"] = 0
                    self.channel_activity[channel_id]["last_ad"] = now
                    self.channel_activity[channel_id]["last_ad_type"] = new_ad_type
                    
                    # Post in the active channel with the file attachment and self-delete after 300 seconds
                    await message.channel.send(embed=ad_embed, file=ad_file, delete_after=300)
                    
                except discord.Forbidden:
                    pass

async def setup(bot):
    await bot.add_cog(AdManager(bot))