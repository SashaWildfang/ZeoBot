import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import datetime

# --- Constants ---
MOD_AND_HIGHER_ROLE_IDS = {1358472557862457537, 1358472532222808126, 1358472588430676018, 1358472511133585564, 1358472635234779207, 1358473248534167663}
BLACKLISTED_CHANNEL_IDS = {1445923851178610718, 1381975737808191599, 1358486649360748665}
BOT_LOGS_CHANNEL_ID = 1360344042705256660

class Clear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_mod_or_higher(self, member: discord.Member) -> bool:
        return any(role.id in MOD_AND_HIGHER_ROLE_IDS for role in member.roles)

    async def create_transcript(self, messages, channel, executor):
        """Generates a text file transcript of deleted messages."""
        transcript_content = f"--- DELETION TRANSCRIPT ---\n"
        transcript_content += f"Channel: #{channel.name} ({channel.id})\n"
        transcript_content += f"Executed By: {executor} ({executor.id})\n"
        transcript_content += f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        transcript_content += f"Total Messages: {len(messages)}\n"
        transcript_content += "---------------------------\n\n"

        for msg in reversed(messages):
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = msg.content if msg.content else "[No Text]"
            attachments = ", ".join([a.url for a in msg.attachments]) if msg.attachments else "None"
            
            line = f"[{timestamp}] {msg.author} ({msg.author.id}): {content}\n"
            if attachments != "None":
                line += f" > Attachments: {attachments}\n"
            transcript_content += line + "\n"

        # Create the file in memory
        buffer = io.BytesIO(transcript_content.encode('utf-8'))
        return discord.File(fp=buffer, filename=f"transcript_{channel.name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    async def log_messages_batch(self, messages, executor, channel):
        """Logs detailed embeds and a full transcript file."""
        log_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
        if not log_channel:
            return

        # 1. Send the Transcript File first
        file = await self.create_transcript(messages, channel, executor)
        await log_channel.send(
            content=f"📑 **Bulk Clear Transcript**\nChannel: {channel.mention}\nExecutor: {executor.mention}", 
            file=file
        )

        # 2. Send individual embeds for messages with MEDIA only (to avoid clutter)
        # We only send full embeds for things with images/videos so the log isn't 100 messages long
        for msg in reversed(messages):
            if msg.attachments or len(messages) <= 5: # Always log if it's a small clear or has media
                embed = discord.Embed(
                    description=msg.content or "*[No text content]*",
                    color=discord.Color.red(),
                    timestamp=msg.created_at
                )
                embed.set_author(name=f"{msg.author} ({msg.author.id})", icon_url=msg.author.display_avatar.url)
                embed.add_field(name="Context", value=f"In {channel.mention} | By {executor.mention}", inline=False)

                if msg.attachments:
                    attach_links = []
                    for attachment in msg.attachments:
                        attach_links.append(f"[{attachment.filename}]({attachment.url})")
                        if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']):
                            embed.set_image(url=attachment.url)
                    embed.add_field(name="Attachments", value="\n".join(attach_links), inline=False)

                await log_channel.send(embed=embed)
                await asyncio.sleep(0.5)

    @app_commands.command(name="clear", description="Bulk delete messages with a full text transcript log")
    @app_commands.describe(amount="Number of messages", user="Optional: Filter by user")
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], user: discord.Member = None):
        if interaction.channel_id in BLACKLISTED_CHANNEL_IDS:
            return await interaction.response.send_message("❌ **Fatal Error:** Clearing is prohibited here.", ephemeral=True)
        if not self.is_mod_or_higher(interaction.user):
            return await interaction.response.send_message("🚫 Mod+ only.", ephemeral=True)

        await interaction.response.defer(thinking=True)

        to_delete = []
        async for msg in interaction.channel.history(limit=amount + 5):
            if msg.id == interaction.id: continue
            if user and msg.author != user: continue
            if msg.flags.value & 64: continue
            to_delete.append(msg)
            if len(to_delete) >= amount: break

        if not to_delete:
            return await interaction.followup.send("No messages found.")

        await self.log_messages_batch(to_delete, interaction.user, interaction.channel)
        await interaction.channel.delete_messages(to_delete)
        await interaction.followup.send(f"✅ Deleted {len(to_delete)} messages and generated transcript.")

    @app_commands.command(name="clearall", description="Wipe a user's history in this channel with transcript")
    async def clearall(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.channel_id in BLACKLISTED_CHANNEL_IDS:
            return await interaction.response.send_message("❌ Prohibited channel.", ephemeral=True)
        if not self.is_mod_or_higher(interaction.user):
            return await interaction.response.send_message("🚫 Mod+ only.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        to_delete = []
        async for msg in interaction.channel.history(limit=1000):
            if msg.author == user: to_delete.append(msg)

        if not to_delete:
            return await interaction.followup.send("No messages found.")

        await self.log_messages_batch(to_delete, interaction.user, interaction.channel)
        
        for i in range(0, len(to_delete), 100):
            await interaction.channel.delete_messages(to_delete[i:i+100])
            await asyncio.sleep(1)

        await interaction.followup.send(f"✅ Cleared {len(to_delete)} messages from {user.mention}. Transcript uploaded to logs.")

async def setup(bot):
    await bot.add_cog(Clear(bot))