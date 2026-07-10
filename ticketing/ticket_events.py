import discord
from discord.ext import commands
from db.database import get_connection
from ticketing.ticket_manager import TicketManager
from ticketing.ticket_controls import TicketControlButtons
import asyncio

# ==========================================================
# CATEGORY IDs & CHANNELS
# ==========================================================
NSFW_OPEN_CATEGORY = 1362459990245245151
NSFW_CLAIMED_CATEGORY = 1362461644768411758
NSFW_CLOSED_CATEGORY = 1448247633574363237

STAFF_ALERT_CHANNEL = 1485825407654559846
STAFF_ROLE_ID = 1358470109965979859
BOT_LOGS_CHANNEL = 1360344042705256660  # Added bot-logs channel

# ==========================================================
# PERMANENT IMAGE URLS
# ==========================================================
ICON_URL = "https://i.imgur.com/6EhF8A4.png"
VERIFY_URL = "https://i.imgur.com/0hDznIi.jpeg"

class TicketEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.tm = TicketManager(self.db)
        self.last_user_message = {}  # {channel_id: datetime}
        print("🟦 TicketEvents COG LOADED")

    # ==========================================================
    # LOGGING HELPER
    # ==========================================================
    async def send_log(self, action: str, ticket: dict, actor, guild: discord.Guild, channel_name: str = None):
        log_channel = guild.get_channel(BOT_LOGS_CHANNEL)
        if not log_channel: return
        
        # Color assignments based on action
        colors = {
            "OPEN": 0x2ecc71,    # Green
            "CLOSE": 0xe67e22,   # Orange
            "REOPEN": 0x3498db,  # Blue
            "DELETE": 0xe74c3c   # Red
        }

        # Attempt to get the channel name if not explicitly provided
        if not channel_name:
            chan_id = int(ticket.get("channel_id", 0))
            chan = guild.get_channel(chan_id)
            if chan:
                channel_name = chan.name
            else:
                # If channel is already deleted, reconstruct its name
                t_type = ticket.get("ticket_type", "")
                if t_type == "support": prefix = "sup"
                elif t_type == "nsfw": prefix = "nsfw"
                elif t_type == "staff-application": prefix = "staff"
                else: prefix = "ticket"

                user_id = int(ticket.get("user_id", 0))
                member = guild.get_member(user_id)
                clean_name = member.name.lower().replace(" ", "-") if member else str(user_id)
                
                channel_name = f"{prefix}-{clean_name}"
        
        embed = discord.Embed(
            title=f"🎫 Ticket Action: {action}",
            color=colors.get(action.upper(), 0x95a5a6),
            timestamp=discord.utils.utcnow()
        )
        
        # Handle cases where actor is a string (like "SYSTEM_INACTIVITY") vs a Member object
        if isinstance(actor, str):
            actor_mention = actor
            actor_id = "System"
        else:
            actor_mention = actor.mention
            actor_id = actor.id
            
        embed.add_field(name="Channel", value=f"`{channel_name}`", inline=True)
        embed.add_field(name="Database ID", value=f"`{ticket.get('ticket_id', 'Unknown')}`", inline=True)
        embed.add_field(name="Ticket Type", value=f"{ticket.get('topic', 'Unknown')} (`{ticket.get('ticket_type', 'Unknown')}`)", inline=False)
        embed.add_field(name="Action By", value=f"{actor_mention} (`{actor_id}`)", inline=False)
        
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        
        ticket = await self.tm.get_by_channel(message.channel.id)
        if not ticket: return

        if message.author.id == int(ticket["user_id"]):
            self.last_user_message[message.channel.id] = discord.utils.utcnow()

    # ==========================================================
    # EVENT — Ticket Created
    # ==========================================================
    @commands.Cog.listener()
    async def on_ticket_opened(self, interaction: discord.Interaction, channel: discord.TextChannel):
        user = interaction.user
        guild = interaction.guild

        # ------------------------------------------------------
        # DETECT TICKET TYPE
        # ------------------------------------------------------
        if channel.name.startswith("apply-") or channel.name.startswith("staff-"):
            t_type = "staff-application"
            topic = "Staff Application"
            color = 0xADD8E6 # Light Blue
        elif channel.name.startswith("ticket-") or channel.name.startswith("sup-"):
            t_type = "support"
            topic = "General Support"
            color = 0xFFFF00 # Yellow
        else:
            t_type = "nsfw"
            topic = "NSFW Verification"
            color = 0xE57373 # Red

        # DB entry
        ticket = await self.tm.create_ticket(
            user_id=user.id,
            guild_id=guild.id,
            channel_id=channel.id,
            topic=topic,
            ticket_type=t_type
        )

        # ------------------------------------------------------
        # BUILD WELCOME EMBED (USER SIDE)
        # ------------------------------------------------------
        embed = discord.Embed(title=f"Welcome — {topic}", color=color)
        embed.set_thumbnail(url=ICON_URL)

        if t_type == "staff-application":
            embed.description = (
                f"Hello {user.mention}, thank you for your interest in joining the **Kitty Kingdom** staff team!\n\n"
                "**Section 1: General Background**\n"
                "> • Tell us a bit about yourself and your history in this community.\n"
                "> • Do you have experience with Discord moderation or bot management?\n\n"
                "**Section 2: Scenarios & Skills**\n"
                "> • How would you handle a heated argument between two members in a public channel?\n"
                "> • What do you believe is the most important trait for a staff member to have?\n\n"
                "**Section 3: Availability & Commitment**\n"
                "> • What is your timezone, and what times are you usually most active?\n"
                "> • Can you commit to checking staff pings and assisting with verifications?\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ **Note:** *Please answer all questions here. Admins will review it soon.*"
            )
        elif t_type == "support":
            embed.description = (
                f"Hello {user.mention}, welcome to support!\n\n"
                "Please describe your issue or question in detail below. "
                "Our <@&1358470318087340342> (Helpers) or other staff will be with you shortly.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ **Note:** *If you are reporting a user, please provide IDs and screenshots if possible.*"
            )
        else:
            # NSFW Verification content
            embed.description = (
                "Please follow these **strictly enforced** steps to verify your age:\n\n"
                "1️⃣ **Photo of your ID** (Face + DOB must be visible — *DOB = Date of Birth*) next to a piece of paper with your **Discord name**, **today's date**, and **the server name** written on it.\n"
                "2️⃣ **A clear selfie** of you holding that same ID.\n\n"
                "_Images are deleted immediately after review._"
            )
            embed.set_image(url=VERIFY_URL)

        # Send welcome message & pin it
        welcome_msg = await channel.send(content=user.mention, embed=embed)
        await welcome_msg.pin()

        # Send Control Buttons
        await channel.send(view=TicketControlButtons(ticket=ticket))

        # ------------------------------------------------------
        # LOG AND ALERT (ADMIN SIDE)
        # ------------------------------------------------------
        # Dispatch to the bot-logs channel
        await self.send_log("OPEN", ticket, user, guild, channel_name=channel.name)
        
        staff_ch = guild.get_channel(STAFF_ALERT_CHANNEL)
        if staff_ch:
            display_type = t_type.replace('-', ' ').title()
            
            alert = discord.Embed(
                title=f"🔔 New {topic} Ticket",
                description=(
                    f"👤 **User:** {user.mention} (`{user.id}`)\n"
                    f"🆔 **ID:** `{ticket['ticket_id']}`\n"
                    f"📂 **Type:** `{display_type}`\n"
                    f"🔗 **Channel:** {channel.mention}"
                ),
                color=color,
                timestamp=discord.utils.utcnow()
            )
            
            alert.set_thumbnail(url=user.display_avatar.url)
            
            # Dynamic content string to differentiate the notification ping
            await staff_ch.send(
                content=f"<@&{STAFF_ROLE_ID}> 📢 **New {display_type} Ticket Created!**", 
                embed=alert
            )

        # Activity Tracking
        self.last_user_message[channel.id] = discord.utils.utcnow()
        self.bot.loop.create_task(self.auto_close(channel.id))

    # ==========================================================
    # EXPOSED EVENTS FOR EXTERNAL TRIGGERS (Close, Reopen, Delete)
    # Your button/command cogs should dispatch these!
    # Example: bot.dispatch("ticket_closed", user, ticket)
    # ==========================================================
    @commands.Cog.listener()
    async def on_ticket_closed(self, user: discord.Member, ticket: dict):
        await self.send_log("CLOSE", ticket, user, user.guild)

    @commands.Cog.listener()
    async def on_ticket_reopened(self, user: discord.Member, ticket: dict):
        await self.send_log("REOPEN", ticket, user, user.guild)

    @commands.Cog.listener()
    async def on_ticket_deleted(self, user: discord.Member, ticket: dict):
        await self.send_log("DELETE", ticket, user, user.guild)

    # ==========================================================
    # AUTO-CLEANUP LOGIC
    # ==========================================================
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cursor = self.tm.tickets.find({
            "user_id": str(member.id), 
            "status": {"$in": ["open", "claimed"]}
        })

        async for ticket in cursor:
            channel_id = int(ticket["channel_id"])
            channel = member.guild.get_channel(channel_id)
            if channel:
                await self.process_auto_close(channel, ticket, "SYSTEM_AUTO_LEAVE")

    async def auto_close(self, channel_id: int):
        await asyncio.sleep(10)
        reminder_sent = False
        while True:
            await asyncio.sleep(60)
            
            # Fetch ticket to check if it was closed by staff
            tick = await self.tm.get_by_channel(channel_id)
            # If the ticket no longer exists or was closed by a staff member, break out and cancel the timer
            if not tick or tick.get("status") == "closed":
                break 
                
            last_msg = self.last_user_message.get(channel_id)
            if not last_msg: continue
            
            inactivity = (discord.utils.utcnow() - last_msg).total_seconds()
            
            # Reset the reminder flag if they talked recently!
            if inactivity < 12 * 3600:
                reminder_sent = False
            
            if inactivity >= 12 * 3600 and not reminder_sent:
                reminder_sent = True
                chan = self.bot.get_channel(channel_id)
                # Worded to specifically indicate deletion
                if chan: await chan.send("⏰ This ticket will auto-delete in 12h due to inactivity.")
                
            if inactivity >= 24 * 3600:
                chan = self.bot.get_channel(channel_id)
                if chan:
                    await self.process_auto_close(chan, tick, "SYSTEM_INACTIVITY")
                break

    async def process_auto_close(self, channel, ticket, staff_id):
        transcript_data = []
        channel_name = channel.name  # Store this before we delete the channel!
        
        try:
            async for msg in channel.history(limit=500, oldest_first=True):
                transcript_data.append({
                    "sender": str(msg.author),
                    "content": msg.content or "[Attachment]",
                    "time": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
            await self.tm.save_transcript(ticket["ticket_id"], transcript_data, staff_id)
        except: pass
        
        await self.tm.close(ticket["ticket_id"], staff_id)
        self.last_user_message.pop(channel.id, None)
        
        guild = channel.guild
        await channel.delete(reason="Automatic ticket deletion.")
        
        # Log the automatic deletion, passing the saved channel_name
        await self.send_log("DELETE", ticket, staff_id, guild, channel_name=channel_name)

async def setup(bot):
    await bot.add_cog(TicketEvents(bot))