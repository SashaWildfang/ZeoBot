import discord
from discord.ext import commands, tasks
from datetime import datetime
from collections import defaultdict
import os
import aiohttp
import aiofiles
import shutil
import asyncio

# --- Configuration ---
LOG_CHANNEL_ID = 1360344042705256660
ROLE_BATCH_WINDOW = 5  # seconds to wait and batch role changes together

# --- Level Roles ---
# All your level tier role IDs (used to detect pure tier-ups)
LEVEL_ROLE_IDS = {
    1361677978421035180, # 0-5
    1361678583713759363, # 5-11
    1361678717197221968, # 11-21
    1361678760327512185, # 21-31
    1361679050632073398, # 31-41
    1361679477700038828, # 41-51
    1361680109953876049, # 51-61
    1361680599672422540, # 61-71
    1361680699563966605, # 71-81
    1361680852064407683, # 81-91
    1361681482946576504  # 91-200
}

class ServerUpdateLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_role_updates = defaultdict(lambda: {"added": set(), "removed": set(), "last_update": None})
        self.flush_pending_roles.start()
        
        # 🛡️ Track IDs to prevent double-logs from simultaneous Edit/Delete events
        self.recently_archived = set()

        # Ensure the local Media directory exists for temporary archiving
        if not os.path.exists("Media"):
            os.makedirs("Media")

    async def log_embed(self, guild: discord.Guild, embed: discord.Embed, files=None):
        """Send a log embed (and optional files) to the log channel."""
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed, files=files)

    def build_footer(self, user: discord.abc.User):
        return f"User ID: {user.id} • {datetime.now().strftime('%-m/%-d/%Y %-I:%M %p')}"

    # -------------------------------
    # 💎 Server Boost Notifications (on_message)
    # -------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.type in (
            discord.MessageType.premium_guild_subscription,
            discord.MessageType.premium_guild_tier_1,
            discord.MessageType.premium_guild_tier_2,
            discord.MessageType.premium_guild_tier_3,
        ):
            embed = discord.Embed(
                title="💎 Server Boosted!",
                description=f"{message.author.mention} just boosted the server! 🎉",
                color=discord.Color.magenta()
            )
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=self.build_footer(message.author))
            await self.log_embed(message.guild, embed)

    # -------------------------------
    #  Message Deletion (MASTER LOG - ARCHIVES MEDIA)
    # -------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        # 🛑 Check if Edit listener already flagged this ID
        if message.id in self.recently_archived:
            return

        # 1. Word Scramble Filter
        try:
            if os.path.exists("word_scramble.txt"):
                with open("word_scramble.txt", "r") as f:
                    scramble_words = {line.strip().lower() for line in f if line.strip()}
                if message.content and any(word in message.content.lower() for word in scramble_words):
                    return 
        except: pass

        # 2. Audit Log Lookup
        deleter = None
        try:
            async for entry in message.guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                if (entry.target.id == message.author.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 5):
                    deleter = entry.user
                    break
        except: pass

        # 3. Archive Media (Full Download/Upload)
        msg_media_dir = f"Media/del_{message.id}"
        os.makedirs(msg_media_dir, exist_ok=True)
        files_to_upload = []
        media_details = [] # Store name and type for the embed

        async with aiohttp.ClientSession() as session:
            # Combine attachments and embedded media
            urls = [a.url for a in message.attachments]
            for e in message.embeds:
                if e.image: urls.append(e.image.url)
                if e.video: urls.append(e.video.url)

            for url in urls:
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            # Extract filename and extension
                            filename = url.split('/')[-1].split('?')[0] or f"file_{message.id}"
                            extension = filename.split('.')[-1].upper() if '.' in filename else "Unknown"
                            
                            file_path = os.path.join(msg_media_dir, filename)
                            async with aiofiles.open(file_path, mode='wb') as f:
                                await f.write(await resp.read())
                            
                            files_to_upload.append(discord.File(file_path))
                            media_details.append(f"📁 `{filename}` (**{extension}**)")
                except: pass

        # 4. Build Embed
        embed = discord.Embed(
            title="🗑️ Message Deleted & Archived",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="User", value=message.author.mention, inline=True)
        
        if deleter:
            embed.add_field(name="Deleted By", value=deleter.mention, inline=True)

        # Main Content
        content = message.content or "*(No text content)*"
        embed.add_field(name="Content", value=content[:1024], inline=False)

        # 5. Add Media Info Field (Filename & Format)
        if media_details:
            embed.add_field(
                name="📦 Archived Media Info", 
                value="\n".join(media_details), 
                inline=False
            )

        embed.set_footer(text=self.build_footer(message.author))

        # 6. Send and Cleanup
        try:
            # Sending files here makes them appear directly below the embed
            await self.log_embed(message.guild, embed, files=files_to_upload)
        finally:
            shutil.rmtree(msg_media_dir, ignore_errors=True)

    # -------------------------------
    # ✏️ Message Edits (TEXT ONLY)
    # -------------------------------
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return

        text_changed = before.content != after.content
        media_removed = len(before.attachments) > len(after.attachments)

        if not text_changed and not media_removed:
            return

        # 🛑 Flag this ID briefly to ensure on_message_delete handles full wipes
        self.recently_archived.add(before.id)

        embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="User", value=before.author.mention, inline=True)

        if text_changed:
            embed.add_field(name="Before", value=(before.content or "*(empty)*")[:1024], inline=False)
            embed.add_field(name="After", value=(after.content or "*(empty)*")[:1024], inline=False)
        
        if media_removed:
            # Just log that media was removed without downloading it
            after_urls = [a.url for a in after.attachments]
            removed_names = [a.filename for a in before.attachments if a.url not in after_urls]
            embed.add_field(name="🗑️ Attachment Removed", value=", ".join(removed_names), inline=False)

        embed.set_footer(text=self.build_footer(before.author))
        await self.log_embed(before.guild, embed)

        # Allow 2 seconds for any following Delete event to be ignored
        await asyncio.sleep(2)
        self.recently_archived.discard(before.id)

    # -------------------------------
    # 👤 User Updates (Avatar/Name)
    # -------------------------------
    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.display_avatar.url != after.display_avatar.url:
            embed = discord.Embed(title=f"🖼️ Avatar Changed: {after.name}", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Old Avatar", value=f"[Link]({before.display_avatar.url})")
            embed.set_footer(text=self.build_footer(after))
            for guild in self.bot.guilds:
                if guild.get_member(after.id): await self.log_embed(guild, embed)
        
        if before.name != after.name:
            embed = discord.Embed(title="✏️ Username Changed", color=discord.Color.yellow(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Before", value=before.name, inline=True)
            embed.add_field(name="After", value=after.name, inline=True)
            embed.set_footer(text=self.build_footer(after))
            for guild in self.bot.guilds:
                if guild.get_member(after.id): await self.log_embed(guild, embed)

    # -------------------------------
    # 👤 Member Updates (Nicks/Roles/Timeouts/Unboost)
    # -------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # 1. Role Batching
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            entry = self.pending_role_updates[after.id]
            entry["added"].update(added)
            entry["removed"].update(removed)
            entry["last_update"] = datetime.utcnow()

        # 2. Nickname Changes
        if before.nick != after.nick:
            embed = discord.Embed(title="🏷️ Nickname Changed", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="Before", value=before.nick or "*None*", inline=False)
            embed.add_field(name="After", value=after.nick or "*None*", inline=False)
            embed.set_footer(text=self.build_footer(after))
            await self.log_embed(after.guild, embed)

        # 3. Timeouts
        if before.timed_out_until != after.timed_out_until:
            if after.communication_disabled_until:
                until = discord.utils.format_dt(after.communication_disabled_until, style='F')
                embed = discord.Embed(title="⏳ Member Timed Out", description=f"{after.mention} was timed out until {until}.", color=discord.Color.dark_gold())
            else:
                embed = discord.Embed(title="✅ Timeout Removed", description=f"{after.mention}'s timeout has been lifted.", color=discord.Color.green())
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=self.build_footer(after))
            await self.log_embed(after.guild, embed)

        # 4. Unboost Detection
        if before.premium_since and not after.premium_since:
            embed = discord.Embed(title="💔 Member Unboosted", description=f"{after.mention} is no longer boosting the server.", color=discord.Color.greyple())
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text=self.build_footer(after))
            await self.log_embed(after.guild, embed)

    # -------------------------------
    # ⏱️ Batch Role Logger Task
    # -------------------------------
    @tasks.loop(seconds=ROLE_BATCH_WINDOW)
    async def flush_pending_roles(self):
        now = datetime.utcnow()
        for user_id, entry in list(self.pending_role_updates.items()):
            if entry["last_update"] and (now - entry["last_update"]).total_seconds() >= ROLE_BATCH_WINDOW:
                for g in self.bot.guilds:
                    member = g.get_member(user_id)
                    if member:
                        added_roles = entry["added"]
                        removed_roles = entry["removed"]
                        
                        # --- LEVEL TIER CHECK ---
                        # Verify if ALL changed roles are strictly level roles
                        all_level_roles = True
                        for r in added_roles.union(removed_roles):
                            if r.id not in LEVEL_ROLE_IDS:
                                all_level_roles = False
                                break
                        
                        # If the batch ONLY contains level roles being swapped:
                        if all_level_roles and added_roles and removed_roles:
                            desc = ""
                            desc += "➕ **Unlocked:** " + ", ".join(r.mention for r in added_roles) + "\n"
                            desc += "➖ **Removed:** " + ", ".join(r.mention for r in removed_roles)
                            
                            embed = discord.Embed(
                                title="🎉 New Level Tier Reached!", 
                                description=f"{member.mention} just reached a new level tier!\n\n{desc}", 
                                color=discord.Color.gold(), 
                                timestamp=discord.utils.utcnow()
                            )
                        # Otherwise, fall back to standard role change embed
                        else:
                            desc = ""
                            if added_roles: desc += "➕ **Added:** " + ", ".join(r.mention for r in added_roles) + "\n"
                            if removed_roles: desc += "➖ **Removed:** " + ", ".join(r.mention for r in removed_roles)
                            
                            embed = discord.Embed(
                                title="🎭 Roles Updated", 
                                description=desc, 
                                color=discord.Color.teal(), 
                                timestamp=discord.utils.utcnow()
                            )
                            
                        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                        embed.set_footer(text=self.build_footer(member))
                        await self.log_embed(g, embed)
                        break
                
                # Delete the user from the dict after processing
                del self.pending_role_updates[user_id]

    def cog_unload(self):
        self.flush_pending_roles.cancel()

async def setup(bot):
    await bot.add_cog(ServerUpdateLogger(bot))