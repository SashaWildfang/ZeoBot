import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import asyncio
import aiohttp
import aiofiles
import os
import shutil
import io

# ===============================
# CONFIG
# ===============================
BOT_LOGS_CHANNEL_ID = 1360344042705256660
ALLOWED_CATEGORY_ID = 1358486463251091569 # Category where the command can be run
PROGRESS_UPDATE_INTERVAL = 100
PROCESSING_CHUNK_SIZE = 1000 # How many messages to hold in memory before flushing

# Restricting scans only to these specific categories
ALLOWED_SCAN_CATEGORIES = {
    1358485130242560020,
    1358452494660796446,
    1499431359284908083,
    1358487125661585658,
    1358487031117906033,
    1358488251996045388,
    1358488573497708764
}

# ===============================
# CONFIRM VIEW
# ===============================
class ConfirmMassClear(discord.ui.View):
    def __init__(self, cog, interaction, user):
        super().__init__(timeout=60)
        self.cog = cog
        self.interaction = interaction
        self.user = user

    @discord.ui.button(label="CONFIRM", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.message.edit(content="✅ **Confirmed. Initializing targeted mass clear...**", view=None)
        asyncio.create_task(self.cog.run_mass_clear(self.interaction, self.user))
        self.stop()

    @discord.ui.button(label="CANCEL", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.message.edit(content="❌ **Mass clear cancelled.**", view=None)
        self.stop()

# ===============================
# COG
# ===============================
class MassClear(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="wipe", description="Wipes a user from the server")
    @app_commands.guild_only()
    async def massclearuser(self, interaction: discord.Interaction, user_id: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admin required.", ephemeral=True)
            
        if not interaction.channel.category or interaction.channel.category.id != ALLOWED_CATEGORY_ID:
            return await interaction.response.send_message("❌ Invalid category. Command must be run in the designated moderation category.", ephemeral=True)

        try:
            user = await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound):
            return await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)

        view = ConfirmMassClear(self, interaction, user)
        await interaction.response.send_message(
            f"⚠️ **CONFIRM TARGETED MASS CLEAR**\nTarget: **{user}** (`{user.id}`)\n"
            "This will scan **selected categories only** (including VCs and threads within them). This action is completely irreversible.",
            view=view
        )

    # ---------------------------------------------------------
    # BACKGROUND MEDIA WORKER (Producer/Consumer)
    # ---------------------------------------------------------
    async def media_downloader_worker(self, session, queue, downloaded_files):
        """Continuously downloads media in the background while the bot scans."""
        while True:
            task = await queue.get()
            if task is None:  # Poison pill to stop the worker
                queue.task_done()
                break
                
            url, save_dir, message_id = task
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        filename = url.split('/')[-1].split('?')[0] or f"file_{message_id}"
                        file_path = os.path.join(save_dir, f"{message_id}_{filename}")
                        async with aiofiles.open(file_path, mode='wb') as f:
                            await f.write(await resp.read())
                        downloaded_files.append(file_path)
            except Exception:
                pass
            finally:
                queue.task_done()

    # ---------------------------------------------------------
    # BATCH PROCESSOR (Memory Manager)
    # ---------------------------------------------------------
    async def process_delete_batch(self, channel, messages, logs_channel, transcript_lines, downloaded_files, user):
        """Logs and deletes a chunk of messages to keep memory usage flat."""
        if not messages: return 0
        
        # 1. Log to text file
        transcript_data = "\n".join(transcript_lines)
        transcript_file = discord.File(io.BytesIO(transcript_data.encode('utf-8')), filename=f"transcript_chunk.txt")
        
        log_embed = discord.Embed(
            title=f"🗑️ Batch Cleared: {channel.name}",
            description=f"Processed **{len(messages)}** messages.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        await logs_channel.send(embed=log_embed, file=transcript_file)

        # 2. Upload downloaded media chunks
        if downloaded_files:
            for i in range(0, len(downloaded_files), 10):
                chunk = downloaded_files[i:i+10]
                discord_files = [discord.File(f) for f in chunk]
                await logs_channel.send(content=f"📦 Media Chunk for {channel.mention}", files=discord_files)
            downloaded_files.clear() # Clear memory

        # 3. Smart Bulk Delete
        now = discord.utils.utcnow()
        bulk_deletes = [m for m in messages if (now - m.created_at).days < 14]
        single_deletes = [m for m in messages if (now - m.created_at).days >= 14]
        
        total_deleted = 0

        # Execute Bulk
        for i in range(0, len(bulk_deletes), 100):
            batch = bulk_deletes[i:i+100]
            try:
                await channel.delete_messages(batch)
                total_deleted += len(batch)
            except discord.HTTPException as e:
                if e.status == 429: # Explicitly handle rate limits
                    await asyncio.sleep(e.retry_after)
                    await channel.delete_messages(batch)
            await asyncio.sleep(1.2) # Baseline API padding

        # Execute Single
        for msg in single_deletes:
            try:
                await msg.delete()
                total_deleted += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.8)

        return total_deleted

    # ---------------------------------------------------------
    # MAIN EXECUTION LOOP
    # ---------------------------------------------------------
    async def run_mass_clear(self, interaction: discord.Interaction, user: discord.User):
        guild = interaction.guild
        logs_channel = guild.get_channel(BOT_LOGS_CHANNEL_ID)
        
        if not logs_channel: return await interaction.followup.send("❌ Logs channel missing.")

        total_deleted = 0
        per_channel = {}
        progress_msg = await interaction.channel.send(f"🚀 Initializing parallel execution engine for {user}...")

        # Gather ALL text channels, voice channels, and threads
        all_channels = guild.text_channels + guild.voice_channels + list(guild.threads)
        
        # Filter for channels that support message history, bot has perms, AND are in allowed categories
        channels_to_scan = []
        for ch in all_channels:
            if hasattr(ch, 'history'):
                perms = ch.permissions_for(guild.me)
                if perms.read_message_history and perms.manage_messages:
                    # Threads don't have 'category_id' directly; they inherit from their parent
                    category_id = getattr(ch, 'category_id', getattr(getattr(ch, 'parent', None), 'category_id', None))
                    
                    if category_id in ALLOWED_SCAN_CATEGORIES:
                        channels_to_scan.append(ch)

        async with aiohttp.ClientSession() as session:
            for channel in channels_to_scan:
                status_msg = await logs_channel.send(embed=discord.Embed(title=f"⚡ Scanning: {channel.name}", color=discord.Color.blue()))
                
                # Setup Channel-Specific Variables
                media_dir = f"Media/mass_{channel.id}"
                os.makedirs(media_dir, exist_ok=True)
                
                download_queue = asyncio.Queue()
                downloaded_files = []
                
                # Start Background Worker for this channel
                worker = asyncio.create_task(self.media_downloader_worker(session, download_queue, downloaded_files))

                scanned = 0
                chunk_messages = []
                chunk_transcript = []
                channel_deleted = 0

                # SCANNING LOOP
                async for message in channel.history(limit=None):
                    scanned += 1
                    
                    if scanned % PROGRESS_UPDATE_INTERVAL == 0:
                        await status_msg.edit(embed=discord.Embed(
                            title=f"⚡ Scanning: {channel.name}", 
                            description=f"Scanned: **{scanned}** | Target msgs found: **{len(chunk_messages) + channel_deleted}**",
                            color=discord.Color.blue()
                        ))

                    if message.author.id == user.id:
                        chunk_messages.append(message)
                        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        chunk_transcript.append(f"[{timestamp}] {message.id}: {message.content or '[NO TEXT]'}")

                        # Toss media to the background worker (DOES NOT BLOCK SCANNER)
                        urls = [a.url for a in message.attachments] + [e.image.url for e in message.embeds if e.image] + [e.video.url for e in message.embeds if e.video]
                        for url in urls:
                            download_queue.put_nowait((url, media_dir, message.id))

                        # If chunk is full, flush it to Discord
                        if len(chunk_messages) >= PROCESSING_CHUNK_SIZE:
                            deleted = await self.process_delete_batch(channel, chunk_messages, logs_channel, chunk_transcript, downloaded_files, user)
                            channel_deleted += deleted
                            chunk_messages.clear()
                            chunk_transcript.clear()

                # Cleanup Channel: Wait for queue to finish downloading remaining files
                await download_queue.put(None) # Send poison pill
                await worker # Wait for worker to close gracefully
                
                # Flush remaining messages in the final chunk
                if chunk_messages:
                    deleted = await self.process_delete_batch(channel, chunk_messages, logs_channel, chunk_transcript, downloaded_files, user)
                    channel_deleted += deleted

                # Final Channel Cleanup
                shutil.rmtree(media_dir, ignore_errors=True)
                if channel_deleted > 0:
                    per_channel[channel.id] = channel_deleted
                    total_deleted += channel_deleted
                
                await status_msg.delete()

        # Final Summary
        summary_desc = "\n".join(f"<#{cid}>: **{cnt}** deleted" for cid, cnt in per_channel.items()) or "No targets found."
        
        # If the summary is too long for a single embed field, cut it off
        if len(summary_desc) > 3000:
            summary_desc = summary_desc[:3000] + "\n... (truncated due to length)"
            
        await logs_channel.send(embed=discord.Embed(
            title=f"✅ Operations Concluded for {user}",
            description=f"{summary_desc}\n\n**Total Erased: {total_deleted}**",
            color=discord.Color.green()
        ))
        await progress_msg.edit(content=f"✅ Targeted execution complete. Erased **{total_deleted}** messages.")

async def setup(bot: commands.Bot):
    await bot.add_cog(MassClear(bot))