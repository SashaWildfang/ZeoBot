import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta
from db.database import get_connection

class ServerIntros(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.collection = self.db["dating_profiles"]
        self.CHANNEL_ID = 1496875154314231828
        self.NITRO_ROLE_ID = 1360260086500561237
        
        # Start the background loop
        self.intro_loop.start()

    def cog_unload(self):
        self.intro_loop.cancel()

    def is_valid(self, val: str) -> bool:
        """Helper to check if a field is empty or N/A."""
        if not val: 
            return False
        v = str(val).strip().lower()
        return v not in ["", "n/a", "none", "skip", "[]", "['n/a']"]

    async def execute_intro_draw(self):
        """The core logic for picking and posting profiles. Can be called by the loop, an event, or a command."""
        channel = self.bot.get_channel(self.CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.CHANNEL_ID)
            except discord.NotFound:
                return

        guild = channel.guild

        # 1. Fetch only profiles actively looking for a relationship
        all_profiles = await self.collection.find({"is_looking": {"$regex": "^yes|y", "$options": "i"}}).to_list(None)
        if not all_profiles:
            return

        # 2. Filter out members who have left the server to avoid posting dead profiles
        valid_profiles = []
        for p in all_profiles:
            member = guild.get_member(p["_id"])
            if member:
                valid_profiles.append((p, member))

        if not valid_profiles:
            return

        # Calculate server-wide metrics for the fun text above the embed
        total_candidates = len(valid_profiles)
        initial_total_weight = sum(p[0].get("profile_weight", 1.0) for p in valid_profiles)

        # 3. Weighted Random Selection (Pick 1)
        selected_profiles = []
        pool = valid_profiles.copy()
        
        num_to_pick = min(1, len(pool))
        for _ in range(num_to_pick):
            weights = [p[0].get("profile_weight", 1.0) for p in pool]
            choice = random.choices(pool, weights=weights, k=1)[0]
            selected_profiles.append(choice)
            pool.remove(choice)

        # 4. Build and send the embeds
        for i, (profile_data, member) in enumerate(selected_profiles, start=1):
            embed = self.build_featured_embed(profile_data, member)
            
            profile_weight = profile_data.get("profile_weight", 1.0)
            base_chance = (profile_weight / initial_total_weight) * 100
            
            header_text = (
                f"### 💖 Featured Match 💖\n"
                f"*Selected from a pool of **{total_candidates}** active profiles! (Base draw chance: **{base_chance:.1f}%**)*"
            )
            
            await channel.send(content=header_text, embed=embed)

    # ==========================================
    # TRIGGERS (Loop, Event, Command)
    # ==========================================

    @tasks.loop(hours=3)
    async def intro_loop(self):
        """Runs automatically every 3 hours."""
        await self.execute_intro_draw()

    @intro_loop.before_loop
    async def before_intro_loop(self):
        """Prevents the bot from spamming on restart. Sleeps until the next 3-hour interval mark."""
        await self.bot.wait_until_ready()
        
        now = datetime.utcnow()
        # Calculate hours to add to reach the next interval of 3 (e.g., 00:00, 03:00, 06:00)
        hours_to_add = 3 - (now.hour % 3)
        next_run = (now + timedelta(hours=hours_to_add)).replace(minute=0, second=0, microsecond=0)
        seconds_to_wait = (next_run - now).total_seconds()
        
        print(f"⏳ ServerIntros loop sleeping for {int(seconds_to_wait)} seconds to align with the next 3-hour interval.")
        await asyncio.sleep(seconds_to_wait)

    @commands.Cog.listener("on_trigger_intros")
    async def on_trigger_intros(self):
        """Custom event listener to manually trigger from elsewhere in code."""
        await self.execute_intro_draw()

    @app_commands.command(name="force_intros", description="[ADMIN] Manually trigger the featured match.")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_intros(self, interaction: discord.Interaction):
        """Allows admins to test the draw without waiting for the loop or dispatching the event."""
        await interaction.response.send_message("🎲 Drawing featured profile now...", ephemeral=True)
        await self.execute_intro_draw()

    # ==========================================
    # EMBED BUILDER
    # ==========================================

    def build_featured_embed(self, data: dict, member: discord.Member) -> discord.Embed:
        name_val = data.get('name', member.display_name)
        embed = discord.Embed(
            title=f"✨ Featured Match: {name_val}",
            description=f"**Connect with them:** {member.mention}",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # --- Basic Info Section ---
        basic_info = []
        
        # Safely extract mandatory gender fields
        raw_gender = data.get("gender", "N/A")
        gender_str = ", ".join(raw_gender) if isinstance(raw_gender, list) else str(raw_gender)
        if not gender_str.strip() or gender_str.lower() in ["[]", "['n/a']"]: gender_str = "N/A"

        raw_target = data.get("looking_for_gender", "N/A")
        target_str = ", ".join(raw_target) if isinstance(raw_target, list) else str(raw_target)
        if not target_str.strip() or target_str.lower() in ["[]", "['n/a']"]: target_str = "N/A"

        # Ordered cleanly as requested
        basic_info.append(f"**Name:** {name_val}")
        if self.is_valid(data.get("age")): basic_info.append(f"**Age:** {data.get('age')}")
        basic_info.append(f"**Gender:** {gender_str}")
        if self.is_valid(data.get("pronouns")): basic_info.append(f"**Pronouns:** {data.get('pronouns')}")
        if self.is_valid(data.get("location")): basic_info.append(f"**Location:** {data.get('location')}")
        if self.is_valid(data.get("relationship_status")): basic_info.append(f"**Status:** {data.get('relationship_status')}")
        basic_info.append(f"**Target Gender(s):** {target_str}")
        
        embed.add_field(name="👤 Basic Info", value="\n".join(basic_info), inline=False)

        # --- Identity & Physical Section ---
        physical = []
        if self.is_valid(data.get("sexuality")): physical.append(f"**Sexuality:** {data.get('sexuality')}")
        if self.is_valid(data.get("sexual_position")): physical.append(f"**Position:** {data.get('sexual_position')}")
        if self.is_valid(data.get("body_type")): physical.append(f"**Body Type:** {data.get('body_type')}")
        if self.is_valid(data.get("height")): physical.append(f"**Height:** {data.get('height')}")
        if self.is_valid(data.get("weight")): physical.append(f"**Weight:** {data.get('weight')}")
        
        if physical:
            embed.add_field(name="🏳️‍🌈 Identity & Physical", value="\n".join(physical), inline=False)

        # --- Fun Fact & Bio Section ---
        if self.is_valid(data.get("fun_fact")):
            embed.add_field(name="✨ Fun Fact", value=data.get("fun_fact"), inline=False)

        if self.is_valid(data.get("bio")):
            embed.add_field(name="📖 Bio", value=data.get("bio"), inline=False)

        # --- Socials Section ---
        socials = []
        social_keys = {
            "Twitter": "twitter", 
            "Telegram": "telegram", 
            "FurAffinity": "furaffinity", 
            "Instagram": "instagram", 
            "Steam": "steam", 
            "Switch": "nintendo_switch"
        }
        for display_name, db_key in social_keys.items():
            if self.is_valid(data.get(db_key)):
                socials.append(f"**{display_name}:** {data.get(db_key)}")
                
        if socials:
            embed.add_field(name="🌐 Socials & Gaming", value="\n".join(socials), inline=False)

        # --- Weight / Nitro Notice ---
        embed.add_field(
            name="\u200b", 
            value=f"💎 <@&{self.NITRO_ROLE_ID}> Server Boosters receive additional profile weighting, increasing their chances of being featured here!",
            inline=False
        )

        # --- Footer ---
        weight = data.get("profile_weight", 1.0)
        embed.set_footer(text=f"Profile Weight: {weight} | Run /profile @{member.name} to see their full profile!")
        
        return embed

async def setup(bot):
    await bot.add_cog(ServerIntros(bot))