import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta, time, timezone
from db.database import get_connection

# Import the LevelManager directly from your events folder
from events.leveling import LevelManager

# Discord.me strict bump reset windows (UTC)
DISCORD_ME_TIMES = [
    time(hour=0, minute=0, tzinfo=timezone.utc),
    time(hour=6, minute=0, tzinfo=timezone.utc),
    time(hour=12, minute=0, tzinfo=timezone.utc),
    time(hour=18, minute=0, tzinfo=timezone.utc)
]

class BumpReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DISBOARD_ID = 302050872383242240
        self.NOTIFY_CHANNEL_ID = 1485825407654559846
        
        # List of roles to ping when it's time to bump
        self.PING_ROLE_IDS = [1358470318087340342, 1358472557862457537]
        
        self.BUMP_COOLDOWN = 7200  # 2 hours in seconds
        
        # Start both background loops when the cog is loaded
        self.bump_check_loop.start()
        self.discord_me_loop.start()

    def cog_unload(self):
        self.bump_check_loop.cancel()
        self.discord_me_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ------------------------------------------------------
        # 1. DISBOARD BUMP LOGIC
        # ------------------------------------------------------
        if message.author.id == self.DISBOARD_ID:
            # Check if the message contains an embed
            if not message.embeds:
                return

            embed = message.embeds[0]

            # Verify it's a SUCCESSFUL bump, not a cooldown error (DISBOARD)
            if embed.description and "Bump done!" in embed.description:
                try:
                    await message.add_reaction("⏰")
                except discord.Forbidden:
                    pass 

                # --- REWARD THE USER & TRACK BUMPS (DISBOARD) ---
                bumper = message.interaction.user if message.interaction else None
                
                if bumper:
                    try:
                        db = get_connection()
                        users_col = db["users"]
                        
                        # Get the current year and month
                        current_month_str = datetime.utcnow().strftime("%Y-%m")
                        
                        # Fetch the user first to check their last bump month
                        user_doc = await users_col.find_one({"discordId": bumper.id})
                        
                        if user_doc and user_doc.get("last_bump_month") == current_month_str:
                            # It is still the same month, increment bumps only
                            await users_col.update_one(
                                {"discordId": bumper.id},
                                {
                                    "$inc": {
                                        "bumps": 1, 
                                        "monthly_bumps": 1
                                    }
                                }
                            )
                        else:
                            # It's a new month (or their first bump)! 
                            await users_col.update_one(
                                {"discordId": bumper.id},
                                {
                                    "$inc": {
                                        "bumps": 1
                                    },
                                    "$set": {
                                        "last_bump_month": current_month_str,
                                        "monthly_bumps": 1
                                    }
                                },
                                upsert=True
                            )

                        # --- GRANT XP AND BALANCE VIA LEVELMANAGER ---
                        leveling_system = LevelManager(self.bot)
                        await leveling_system.add_xp(bumper, 300, 250)
                        
                        # Fetch the updated document to show accurate stats
                        updated_doc = await users_col.find_one({"discordId": bumper.id})
                        new_balance = updated_doc.get("balance", 250)
                        total_bumps = updated_doc.get("bumps", 1)
                        monthly_bumps = updated_doc.get("monthly_bumps", 1)
                        
                        # Format the balance with commas
                        formatted_balance = f"{new_balance:,}"
                        
                        # Send the confirmation message
                        await message.channel.send(
                            f"🎉 Thank you for bumping, {bumper.mention}! You've been rewarded **300 ✨** and **250** <:leaf:1524758896659660831>\n"
                            f"**New Balance:** {formatted_balance} <:leaf:1524758896659660831> | **Total Bumps:** {total_bumps} | **Monthly Bumps:** {monthly_bumps}"
                        )
                        
                        # --- SAVE PERSISTENT TIMER TO GLOBALS TABLE ---
                        next_bump_time = datetime.utcnow() + timedelta(seconds=self.BUMP_COOLDOWN)
                        globals_col = db["globals"]
                        
                        # Update the existing global document
                        await globals_col.update_one(
                            {}, 
                            {"$set": {"next_bump_time": next_bump_time}},
                            upsert=True
                        )

                    except Exception as e:
                        print(f"Error rewarding user for Disboard bump: {e}")
            
            # Exit the function early since we handled the Disboard message
            return 

        # ------------------------------------------------------
        # 2. DISCORD.ME BUMP LOGIC
        # ------------------------------------------------------
        # Listen in the specific channel and look for the specific notification phrasing
        if message.channel.id == self.NOTIFY_CHANNEL_ID and "bumped the server at" in message.content and "on Discord Me." in message.content:
            try:
                await message.add_reaction("💙")
            except discord.Forbidden:
                pass 

            # Extract the username. 
            # E.g., "sashathesnep bumped the server at 12:01:16 on Discord Me." -> gets "sashathesnep"
            extracted_username = message.content.split(" bumped the server at")[0].strip()

            # Find the user object in the server by their username
            bumper = discord.utils.get(message.guild.members, name=extracted_username)

            if bumper:
                try:
                    db = get_connection()
                    users_col = db["users"]
                    
                    # Get the current year and month
                    current_month_str = datetime.utcnow().strftime("%Y-%m")
                    
                    # Track bumps just like we do for Disboard
                    user_doc = await users_col.find_one({"discordId": bumper.id})
                    
                    if user_doc and user_doc.get("last_bump_month") == current_month_str:
                        await users_col.update_one(
                            {"discordId": bumper.id},
                            {"$inc": {"bumps": 1, "monthly_bumps": 1}}
                        )
                    else:
                        await users_col.update_one(
                            {"discordId": bumper.id},
                            {
                                "$inc": {"bumps": 1},
                                "$set": {"last_bump_month": current_month_str, "monthly_bumps": 1}
                            },
                            upsert=True
                        )

                    # --- GRANT XP AND BALANCE VIA LEVELMANAGER (500 for Discord.me) ---
                    leveling_system = LevelManager(self.bot)
                    await leveling_system.add_xp(bumper, 500, 500)
                    
                    # Fetch the updated document to show accurate stats
                    updated_doc = await users_col.find_one({"discordId": bumper.id})
                    new_balance = updated_doc.get("balance", 500)
                    total_bumps = updated_doc.get("bumps", 1)
                    monthly_bumps = updated_doc.get("monthly_bumps", 1)
                    
                    # Format the balance with commas
                    formatted_balance = f"{new_balance:,}"
                    
                    await message.channel.send(
                        f"🎉 Thank you for bumping on Discord.me, {bumper.mention}! You've been rewarded **500 ✨** and **500** <:leaf:1524758896659660831>\n"
                        f"**New Balance:** {formatted_balance} <:leaf:1524758896659660831> | **Total Bumps:** {total_bumps} | **Monthly Bumps:** {monthly_bumps}"
                    )
                except Exception as e:
                    print(f"Error rewarding user for Discord.me bump: {e}")
            else:
                # Fallback if the user can't be found in the server cache
                await message.channel.send(f"⚠️ A Discord.me bump was recorded for `{extracted_username}`, but I couldn't find them in the server to issue the reward! Ensure my 'Server Members Intent' is enabled.")


    # ==========================================
    # DISBOARD: DYNAMIC 2-HOUR LOOP
    # ==========================================
    @tasks.loop(seconds=60)
    async def bump_check_loop(self):
        try:
            db = get_connection()
            globals_col = db["globals"]
            
            # Fetch the main global document
            global_doc = await globals_col.find_one({})
            
            # If a timer exists in the database
            if global_doc and "next_bump_time" in global_doc:
                next_bump = global_doc["next_bump_time"]
                
                # Check if 2 hours have passed
                if datetime.utcnow() >= next_bump:
                    notify_channel = self.bot.get_channel(self.NOTIFY_CHANNEL_ID)
                    
                    if notify_channel:
                        embed_reminder = discord.Embed(
                            title="⏰ Time to Bump Disboard!",
                            description="It's been 2 hours! Please run `/bump` to keep the server growing.",
                            color=discord.Color.brand_green()
                        )
                        
                        ping_content = " ".join([f"<@&{role_id}>" for role_id in self.PING_ROLE_IDS])
                        
                        await notify_channel.send(
                            content=ping_content, 
                            embed=embed_reminder
                        )
                    
                    # Clear the timer from the database so it doesn't spam every minute
                    await globals_col.update_one(
                        {},
                        {"$unset": {"next_bump_time": ""}}
                    )
        except Exception as e:
            print(f"Error in bump_check_loop: {e}")

    @bump_check_loop.before_loop
    async def before_bump_check_loop(self):
        await self.bot.wait_until_ready()


    # ==========================================
    # DISCORD.ME: FIXED TIME SCHEDULE LOOP
    # ==========================================
    @tasks.loop(time=DISCORD_ME_TIMES)
    async def discord_me_loop(self):
        try:
            notify_channel = self.bot.get_channel(self.NOTIFY_CHANNEL_ID)
            
            if notify_channel:
                embed_reminder = discord.Embed(
                    title="🌐 Time to Bump Discord.me!",
                    description="A new block has started! Head over to our [Discord.me Page](https://discord.me/dashboard) and give us a bump!",
                    color=discord.Color.blurple()
                )
                
                ping_content = " ".join([f"<@&{role_id}>" for role_id in self.PING_ROLE_IDS])
                
                await notify_channel.send(
                    content=ping_content, 
                    embed=embed_reminder
                )
        except Exception as e:
            print(f"Error in discord_me_loop: {e}")

    @discord_me_loop.before_loop
    async def before_discord_me_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(BumpReminder(bot))