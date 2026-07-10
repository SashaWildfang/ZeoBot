import discord
from discord.ext import commands, tasks
from db.database import get_connection
import logging

# Configure logging
logger = logging.getLogger("MediaPerms")

# --- CONFIGURATION ---
MEDIA_PERMS_ROLE_ID = 1502679664894677063
MEMBER_ROLE_ID = 1358469854725931038
YOUR_GUILD_ID = 1358452494128250940  # Ensure this matches your server's ID
MEDIA_ANNOUNCEMENT_CHANNEL_ID = 1358485891361804358 # Channel to send the congratulatory message

# Define what "a certain amount of activity" means here:
# The user gets the role if they meet AT LEAST ONE of these requirements.
REQUIRED_LEVEL = 5          # Change this to your preferred level threshold
REQUIRED_MSG_COUNT = 100    # Change this to your preferred message count threshold
# ---------------------

class MediaPerms(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_media_perms.start()

    def cog_unload(self):
        self.sync_media_perms.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return
            
        # Only process for your specific guild
        if message.guild.id != YOUR_GUILD_ID:
            return

        member = message.author
        
        # 1. Check if they have the required base member role
        has_member_role = any(role.id == MEMBER_ROLE_ID for role in member.roles)
        if not has_member_role:
            return
            
        # 2. Check if they ALREADY have the Media Perms role
        has_media_role = any(role.id == MEDIA_PERMS_ROLE_ID for role in member.roles)
        if has_media_role:
            return # Skip database query to save resources if they already have it
            
        # 3. They are a member but don't have media perms yet. Check their activity in the DB.
        try:
            db = get_connection()
            users_col = db["users"]
            
            # Fetch user from DB (discordId is stored as an integer based on your member_join.py)
            user_doc = await users_col.find_one({"discordId": member.id})
            
            if not user_doc:
                return
                
            user_level = int(user_doc.get("level", 1))
            user_msg_count = int(user_doc.get("msgCount", 0))
            
            # Check if they meet either threshold
            if user_level >= REQUIRED_LEVEL or user_msg_count >= REQUIRED_MSG_COUNT:
                media_role = message.guild.get_role(MEDIA_PERMS_ROLE_ID)
                
                if media_role:
                    # Give them the role
                    await member.add_roles(media_role, reason=f"Reached activity threshold (Lvl {user_level}, Msgs: {user_msg_count})")
                    
                    # Update database to reflect they have the perms
                    await users_col.update_one(
                        {"discordId": member.id},
                        {"$set": {"hasMediaPerms": True}}
                    )
                    
                    logger.info(f"Granted Media Perms to {member.name} (Level: {user_level}, Msgs: {user_msg_count})")
                    
                    # Send plain text message to the specified channel
                    announcement_channel = message.guild.get_channel(MEDIA_ANNOUNCEMENT_CHANNEL_ID)
                    if announcement_channel:
                        try:
                            await announcement_channel.send(
                                f"🎉 {member.mention}, you have been granted Media Perms! You can now post Embeds, Media, and add Reactions."
                            )
                        except discord.Forbidden:
                            logger.error(f"Missing permissions to send message in channel {MEDIA_ANNOUNCEMENT_CHANNEL_ID}")
                            
        except Exception as e:
            logger.error(f"Error checking real-time media perms for {member.name}: {e}")

    # Background task to catch anyone who might have leveled up while the bot was offline, 
    # or was given levels manually via admin commands.
    @tasks.loop(hours=1)
    async def sync_media_perms(self):
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(YOUR_GUILD_ID)
        if not guild:
            return
            
        media_role = guild.get_role(MEDIA_PERMS_ROLE_ID)
        member_role = guild.get_role(MEMBER_ROLE_ID)
        
        if not media_role or not member_role:
            logger.warning("Media role or Member role not found in the server. Cannot sync.")
            return

        try:
            db = get_connection()
            users_col = db["users"]
            
            # Find all users in the DB who meet the activity threshold but don't have 'hasMediaPerms' set to True
            query = {
                "$or": [
                    {"level": {"$gte": REQUIRED_LEVEL}},
                    {"msgCount": {"$gte": REQUIRED_MSG_COUNT}}
                ],
                "hasMediaPerms": {"$ne": True}
            }
            
            cursor = users_col.find(query)
            
            async for user_doc in cursor:
                user_id = user_doc.get("discordId")
                if not user_id:
                    continue
                    
                member = guild.get_member(user_id)
                
                # If they are still in the server and have the base member role
                if member and member_role in member.roles:
                    granted_now = False
                    if media_role not in member.roles:
                        await member.add_roles(media_role, reason="Background sync: Reached activity threshold")
                        granted_now = True
                        
                    # Update DB
                    await users_col.update_one(
                        {"discordId": user_id},
                        {"$set": {"hasMediaPerms": True}}
                    )
                    logger.info(f"Background Sync: Granted Media Perms to {member.name}")
                    
                    # Announce in the specified channel if it was just granted
                    if granted_now:
                        announcement_channel = guild.get_channel(MEDIA_ANNOUNCEMENT_CHANNEL_ID)
                        if announcement_channel:
                            try:
                                await announcement_channel.send(
                                    f"🎉 {member.mention}, you have been granted Media Perms! You can now post Embeds, Media, and add Reactions."
                                )
                            except discord.Forbidden:
                                logger.error(f"Missing permissions to send message in channel {MEDIA_ANNOUNCEMENT_CHANNEL_ID}")
                                
        except Exception as e:
            logger.error(f"Error during background media perms sync: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(MediaPerms(bot))