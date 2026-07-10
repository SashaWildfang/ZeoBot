import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import asyncio
from db.database import get_connection

# Import the LevelManager so we can process XP and level-ups natively
from events.leveling import LevelManager

# ==========================================
# CONFIGURATION
# ==========================================
NOTIFY_CHANNEL_ID = 1358485891361804358
VC_LOGS_CHANNEL_ID = 1503203701580365974
AFK_CHANNEL_ID = 1503213751862820984         # <--- AFK Channel

MINIMUM_MINUTES = 5          # Minimum time in VC to earn rewards
BUTTERFLIES_PER_MIN = 4     # INCREASED: Base crabs/butterflies earned per minute
XP_PER_MIN = 5              # INCREASED: Base XP earned per minute
MAX_GHOST_PAYOUT_HOURS = 12  # Max payout limit if bot crashes and user leaves offline

class VCManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.vc_info_col = self.db["vc_info"]  # Persistent table
        self.globals_col = self.db["globals"]  # Globals table for tax
        print("🎙️ VC Manager COG LOADED (Persistent, Stats, Tax & AFK Edition)")

    async def cog_load(self):
        """Fire and forget the sync task so it DOES NOT block the bot from booting!"""
        self.bot.loop.create_task(self.sync_vcs_on_startup())

    async def sync_vcs_on_startup(self):
        """Background task: Sync reality with the database upon bot startup."""
        await self.bot.wait_until_ready()
        print("🎙️ VC Manager: Bot is ready! Syncing live VCs with database...")
        now = discord.utils.utcnow()
        
        # 1. Identify everyone currently in VC across all servers (EXCLUDING AFK)
        live_vc_members = {}
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                if vc.id == AFK_CHANNEL_ID: 
                    continue # Completely ignore users currently in AFK
                for member in vc.members:
                    if not member.bot:
                        live_vc_members[member.id] = vc

        # 2. Fetch all active sessions stored in the database
        db_sessions = {}
        async for doc in self.vc_info_col.find({}):
            db_sessions[doc["discordId"]] = doc

        # 3. Handle 'Ghost' Sessions (User is in DB, but left VC/went AFK while bot was offline)
        ghost_ids = set(db_sessions.keys()) - set(live_vc_members.keys())
        for ghost_id in ghost_ids:
            session = db_sessions[ghost_id]
            await self._process_payout(ghost_id, session, now, is_ghost=True)

        # 4. Handle 'New' Sessions (User is in VC, but not in DB yet)
        new_ids = set(live_vc_members.keys()) - set(db_sessions.keys())
        for new_id in new_ids:
            vc_channel = live_vc_members[new_id]
            await self.vc_info_col.update_one(
                {"discordId": new_id},
                {"$setOnInsert": {
                    "start_time": now,
                    "companions": [],
                    "channel_id": vc_channel.id
                }},
                upsert=True
            )
            # Log their join time
            await self.users_col.update_one(
                {"discordId": new_id},
                {"$set": {"last_vc_join": now}},
                upsert=True
            )

        # 5. Cross-update companions for everyone currently in VC
        for user_id, vc_channel in live_vc_members.items():
            member = vc_channel.guild.get_member(user_id)
            if member:
                await self._update_companions_db(vc_channel, member)
        
        print("🎙️ VC Manager: Sync complete!")

    async def _update_companions_db(self, channel: discord.VoiceChannel, current_member: discord.Member):
        """Cross-adds users to each other's companion arrays in the database."""
        if current_member.bot: return
        
        companion_ids = [m.id for m in channel.members if not m.bot and m.id != current_member.id]
        
        if companion_ids:
            # 1. Add everyone to the current member's list
            await self.vc_info_col.update_one(
                {"discordId": current_member.id},
                {"$addToSet": {"companions": {"$each": companion_ids}}}
            )
            
            # 2. Add the current member to everyone else's list
            await self.vc_info_col.update_many(
                {"discordId": {"$in": companion_ids}},
                {"$addToSet": {"companions": current_member.id}}
            )

    def _format_duration(self, seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            return f"{int(minutes)}m {int(seconds)}s"
        else:
            return f"{int(seconds)}s"

    async def _log_vc_event(self, member: discord.Member, action: str, description: str, color: discord.Color):
        """Helper to send hyper-detailed logs to the VC Logs channel."""
        try:
            log_channel = self.bot.get_channel(VC_LOGS_CHANNEL_ID) or await self.bot.fetch_channel(VC_LOGS_CHANNEL_ID)
            if not log_channel: return
            
            embed = discord.Embed(
                title=f"🎙️ VC Event: {action}",
                description=description,
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url)
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Failed to send VC log: {e}")

    async def _process_payout(self, user_id: int, session_data: dict, leave_time: datetime, is_ghost: bool = False, member: discord.Member = None):
        """Calculates and applies the VC rewards, tax, and time stats to the database."""
        
        # Resolve member object if not explicitly provided (needed by the LevelManager)
        if not member:
            channel = self.bot.get_channel(session_data.get("channel_id"))
            if channel:
                member = channel.guild.get_member(user_id)

        # 1. Ensure start_time is UTC aware
        start_time = session_data["start_time"]
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
            
        duration_seconds = (leave_time - start_time).total_seconds()
        
        # Cap offline ghost payouts to prevent massive unearned rewards if bot was down for days
        if is_ghost and duration_seconds > (MAX_GHOST_PAYOUT_HOURS * 3600):
            duration_seconds = MAX_GHOST_PAYOUT_HOURS * 3600
            
        minutes = int(duration_seconds // 60)
        
        # 2. Fetch User Document
        user_doc = await self.users_col.find_one({"discordId": user_id}) or {}
        current_month_str = leave_time.strftime("%Y-%m")
        stored_month = user_doc.get("vc_month", "")

        # 3. Calculate Economy Rewards and Tax
        gross_bf = 0
        net_bf = 0
        tax_bf = 0
        earned_xp = 0
        
        if minutes >= MINIMUM_MINUTES:
            bf_mult = user_doc.get("butterfly_multiplier", 1.0)
            xp_mult = user_doc.get("xp_multiplier", 1.0)
            
            gross_bf = int(minutes * BUTTERFLIES_PER_MIN * bf_mult)
            earned_xp = int(minutes * XP_PER_MIN * xp_mult)
            
            # Apply 5% tax to crabs
            tax_bf = int(gross_bf * 0.05)
            net_bf = gross_bf - tax_bf
        
        # 4. Prepare Database Update (Stats Only)
        update_query = {
            "$inc": {
                "vc_time_total": duration_seconds
            },
            "$set": {}
        }

        # Handle Lazy Monthly Reset for Stats
        if stored_month != current_month_str:
            # It's a new month! Reset the monthly counter to JUST this session's time
            update_query["$set"]["vc_month"] = current_month_str
            update_query["$set"]["vc_time_monthly"] = duration_seconds
        else:
            # Same month, just increment the tracker
            update_query["$inc"]["vc_time_monthly"] = duration_seconds

        # Grant Economy Resources via LevelManager (if valid) or via DB Fallback
        if net_bf > 0 or earned_xp > 0:
            if member:
                # Let the XP event handle storing XP, totalXp, levels, daily stats, and butterflies
                leveling = LevelManager(self.bot)
                await leveling.add_xp(member, xp_gain=earned_xp, butterflies_gain=net_bf)
            else:
                # Fallback: User completely left the server while offline, so just silently add it to DB
                if net_bf > 0: update_query["$inc"]["butterflies"] = net_bf
                if earned_xp > 0: 
                    update_query["$inc"]["xp"] = earned_xp
                    update_query["$inc"]["totalXp"] = earned_xp

        # Cleanup empty $set to prevent Mongo errors
        if not update_query["$set"]:
            del update_query["$set"]

        # 5. Push Updates to User and Clean up Session
        await self.users_col.update_one({"discordId": user_id}, update_query, upsert=True)
        await self.vc_info_col.delete_one({"discordId": user_id})
        
        # 6. Add Tax to Casino Jackpot
        if tax_bf > 0:
            await self.globals_col.update_one(
                {"_id": "casino_jackpot"},
                {"$inc": {"amount": tax_bf}},
                upsert=True
            )
        
        # 7. Send Notification Embed (ONLY if they met the minimum time for rewards)
        if minutes >= MINIMUM_MINUTES:
            companions = session_data.get("companions", [])
            if companions:
                comp_list = [f"<@{uid}>" for uid in companions[:15]]
                comp_str = ", ".join(comp_list)
                if len(companions) > 15:
                    comp_str += f" and {len(companions) - 15} others..."
            else:
                comp_str = "No one (Solo)"

            try:
                notify_channel = self.bot.get_channel(NOTIFY_CHANNEL_ID) or await self.bot.fetch_channel(NOTIFY_CHANNEL_ID)
                if notify_channel:
                    # Build Embed Description with optional Ghost / Tax tags
                    desc = f"Thanks for hanging out in voice chat, <@{user_id}>!"
                    if is_ghost:
                        desc += " *(Offline Recovery)*"
                    if tax_bf > 0:
                        desc += f"\n*(A 5% tax of **{tax_bf} 🦀** went towards the server jackpot)*"

                    embed = discord.Embed(
                        title="🎧 VC Rewards Claimed!",
                        description=desc,
                        color=discord.Color.gold(),
                        timestamp=leave_time
                    )
                    
                    guild_member = notify_channel.guild.get_member(user_id)
                    if guild_member:
                        embed.set_thumbnail(url=guild_member.display_avatar.url)
                        
                    embed.add_field(name="⏱️ Duration", value=f"**{self._format_duration(int(duration_seconds))}**", inline=True)
                    embed.add_field(name="💰 Earned", value=f"**+{net_bf} 🦀**\n**+{earned_xp} ✨**", inline=True)
                    embed.add_field(name="👥 In VC With", value=comp_str, inline=False)
                    
                    # Show total monthly time as a nice touch
                    new_monthly = (duration_seconds if stored_month != current_month_str else user_doc.get("vc_time_monthly", 0) + duration_seconds)
                    embed.set_footer(text=f"Monthly VC Time: {self._format_duration(int(new_monthly))}")
                    
                    await notify_channel.send(content=f"<@{user_id}>", embed=embed)
            except Exception as e:
                print(f"❌ Failed to send VC reward notification: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        now = discord.utils.utcnow()

        # ==========================================
        # 1. JOINING A VC
        # ==========================================
        if before.channel is None and after.channel is not None:
            # Check if they joined the AFK channel directly
            if after.channel.id == AFK_CHANNEL_ID:
                await self._log_vc_event(member, "Joined AFK", f"{member.mention} connected directly to {after.channel.mention}", discord.Color.dark_grey())
                return # Do not start a session

            # Normal VC Join
            await self.vc_info_col.update_one(
                {"discordId": member.id},
                {"$setOnInsert": {
                    "start_time": now,
                    "companions": [],
                    "channel_id": after.channel.id
                }},
                upsert=True
            )
            await self.users_col.update_one({"discordId": member.id}, {"$set": {"last_vc_join": now}}, upsert=True)
            await self._update_companions_db(after.channel, member)
            await self._log_vc_event(member, "Joined VC", f"{member.mention} joined {after.channel.mention}", discord.Color.green())

        # ==========================================
        # 2. SWITCHING VCs
        # ==========================================
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            # Case A: Moved TO AFK (Cash out immediately)
            if after.channel.id == AFK_CHANNEL_ID:
                session = await self.vc_info_col.find_one({"discordId": member.id})
                duration_str = ""
                
                if session:
                    start_time = session["start_time"]
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    duration_seconds = (now - start_time).total_seconds()
                    duration_str = f" after **{self._format_duration(int(duration_seconds))}**"

                await self._log_vc_event(member, "Moved to AFK", f"{member.mention} was moved to {after.channel.mention}{duration_str}", discord.Color.dark_grey())
                
                if session:
                    # Pass member in so the level manager operates successfully
                    await self._process_payout(member.id, session, now, member=member)

            # Case B: Moved FROM AFK to Normal VC (Start fresh session)
            elif before.channel.id == AFK_CHANNEL_ID:
                await self.vc_info_col.update_one(
                    {"discordId": member.id},
                    {"$setOnInsert": {
                        "start_time": now,
                        "companions": [],
                        "channel_id": after.channel.id
                    }},
                    upsert=True
                )
                await self.users_col.update_one({"discordId": member.id}, {"$set": {"last_vc_join": now}}, upsert=True)
                await self._update_companions_db(after.channel, member)
                await self._log_vc_event(member, "Returned from AFK", f"{member.mention} joined {after.channel.mention}", discord.Color.green())

            # Case C: Switched between normal VCs
            else:
                await self.vc_info_col.update_one(
                    {"discordId": member.id},
                    {"$set": {"channel_id": after.channel.id}}
                )
                await self._update_companions_db(after.channel, member)
                await self._log_vc_event(member, "Switched VC", f"{member.mention} moved from {before.channel.mention} ➡️ {after.channel.mention}", discord.Color.blue())

        # ==========================================
        # 3. LEAVING A VC
        # ==========================================
        elif before.channel is not None and after.channel is None:
            # If they just left AFK, they already got their payout when they entered it. Just log.
            if before.channel.id == AFK_CHANNEL_ID:
                await self._log_vc_event(member, "Left Server (from AFK)", f"{member.mention} disconnected from {before.channel.mention}", discord.Color.dark_grey())
            else:
                # Normal leave, calculate duration and process payout
                session = await self.vc_info_col.find_one({"discordId": member.id})
                duration_str = ""
                
                if session:
                    start_time = session["start_time"]
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    duration_seconds = (now - start_time).total_seconds()
                    duration_str = f" after **{self._format_duration(int(duration_seconds))}**"

                await self._log_vc_event(member, "Left VC", f"{member.mention} disconnected from {before.channel.mention}{duration_str}", discord.Color.red())
                
                if session:
                    # Pass member in so the level manager operates successfully
                    await self._process_payout(member.id, session, now, member=member)

        # ==========================================
        # 4. STATE CHANGES (Mute, Deafen, Stream, etc.)
        # ==========================================
        elif before.channel == after.channel:
            changes = []
            
            if before.self_mute != after.self_mute:
                state = "Muted" if after.self_mute else "Unmuted"
                changes.append(f"Self-Mute: **{state}**")
                
            if before.self_deaf != after.self_deaf:
                state = "Deafened" if after.self_deaf else "Undeafened"
                changes.append(f"Self-Deafen: **{state}**")
                
            if before.mute != after.mute:
                state = "Server Muted" if after.mute else "Server Unmuted"
                changes.append(f"Server-Mute: **{state}**")
                
            if before.deaf != after.deaf:
                state = "Server Deafened" if after.deaf else "Server Undeafened"
                changes.append(f"Server-Deafen: **{state}**")
                
            if before.self_stream != after.self_stream:
                state = "Started Streaming" if after.self_stream else "Stopped Streaming"
                changes.append(f"Stream Status: **{state}**")
                
            if before.self_video != after.self_video:
                state = "Turned Camera On" if after.self_video else "Turned Camera Off"
                changes.append(f"Video Status: **{state}**")
                
            if changes:
                desc = "\n".join(changes)
                await self._log_vc_event(
                    member, 
                    "State Changed", 
                    f"{member.mention} updated their status in {after.channel.mention}:\n{desc}", 
                    discord.Color.light_grey()
                )

async def setup(bot):
    await bot.add_cog(VCManager(bot))