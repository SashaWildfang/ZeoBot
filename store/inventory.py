import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from typing import Literal
import random
from db.database import get_connection

class UseConfirmView(discord.ui.View):
    def __init__(self, cog, item, user_id_str, active_booster):
        super().__init__(timeout=60)
        self.cog = cog
        self.item = item
        self.user_id_str = user_id_str
        self.active_booster = active_booster
        self.used = False

    @discord.ui.button(label="Confirm Use", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.used: return
        self.used = True
        
        # Re-verify they still own it right now
        owned_item = await self.cog.user_inventory.find_one({"_id": self.item["_id"]})
        if not owned_item:
            return await interaction.response.edit_message(content="❌ You no longer own this item!", embed=None, view=None)

        now = datetime.utcnow()
        duration_seconds = self.item.get("duration", 3600)
        
        if self.active_booster:
            # EXTEND existing booster
            end_time = self.active_booster["end_time"] + timedelta(seconds=duration_seconds)
            await self.cog.temp_boosters.update_one(
                {"_id": self.active_booster["_id"]},
                {"$set": {"end_time": end_time}}
            )
        else:
            # CREATE new booster
            end_time = now + timedelta(seconds=duration_seconds)
            await self.cog.temp_boosters.insert_one({
                "discordId": self.user_id_str,
                "item_id": self.item["item_id"],
                "item_name": self.item["name"],
                "start_time": now,
                "end_time": end_time,
                "duration": duration_seconds
            })

        # Consume 1 from inventory
        await self.cog.user_inventory.delete_one({"_id": self.item["_id"]})
        
        # Log to channel
        channel = self.cog.bot.get_channel(self.cog.LOG_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.cog.bot.fetch_channel(self.cog.LOG_CHANNEL_ID)
            except discord.NotFound:
                pass
                
        total_xp, total_balance, total_pw, xp_breakdown, leaf_breakdown, pw_breakdown = await self.cog.get_multipliers(interaction.user, self.user_id_str)

        if channel:
            if self.item["item_id"] == "booster_xp":
                msg = f"🔥 <@{self.user_id_str}>, you redeemed a personal **{self.item['name']}**!\n📊 **New XP Breakdown:** {xp_breakdown} ➔ **Total: `{total_xp}x`**"
            elif self.item["item_id"] == "booster_balance":
                msg = f"🔥 <@{self.user_id_str}>, you redeemed a personal **{self.item['name']}**!\n📊 **New Leaf Breakdown:** {leaf_breakdown} ➔ **Total: `{total_balance}x`**"
            elif self.item["item_id"] == "booster_profile":
                msg = f"🔥 <@{self.user_id_str}>, you redeemed a personal **{self.item['name']}**!\n💖 **New Profile Breakdown:** {pw_breakdown} ➔ **Total Weight: `{total_pw}x`**"
            else:
                msg = f"🔥 <@{self.user_id_str}>, you redeemed a personal **{self.item['name']}**!"
                
            await channel.send(msg)

        await interaction.response.edit_message(
            content=f"✅ Successfully activated your **{self.item['name']}**! It will remain active until <t:{int(end_time.timestamp())}:t> (<t:{int(end_time.timestamp())}:R>).",
            embed=None, 
            view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.used = True
        await interaction.response.edit_message(content="❌ Canceled item use.", embed=None, view=None)


class Inventory(commands.Cog):
    """Cog for managing user inventory and active boosters."""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        
        self.user_inventory = self.db["user_inventory"]
        self.temp_boosters = self.db["temporary_boosters"]
        self.globals_table = self.db["globals"]
        self.users_table = self.db["users"]
        self.dating_profile = self.db["dating_profile"]

        self.LOG_CHANNEL_ID = 1358485891361804358

        # Role Constants
        self.NITRO_ROLE = 1360260086500561237
        self.NITRO_BOOSTER_ROLE = 1498492008648544277 # Added new Server Booster role
        self.ROYAL_KITTEN = 1362102163693633818
        self.KITTEN_GUARDIAN = 1496892410335330374
        self.LEGENDARY_NEKO = 1362502871639396362

        # Start background task to clean expired boosters
        self.clean_expired_boosters.start()

    def cog_unload(self):
        self.clean_expired_boosters.cancel()

    async def get_multipliers(self, member: discord.Member, discord_id_str: str):
        """Calculates current multipliers dynamically based on roles, weekends, and ALL active boosters."""
        base_xp = 1.0
        base_leaf = 1.0
        base_pw = 1.0 # Profile Weight Base
        
        xp_breakdown = ["Base: `1.0x`"]
        leaf_breakdown = ["Base: `1.0x`"]
        pw_breakdown = ["Base: `1.0x`"]

        if member:
            role_ids = [r.id for r in member.roles]
            
            # Nitro Boost (XP / Leaf)
            if self.NITRO_ROLE in role_ids:
                base_xp += 0.15
                base_leaf += 0.15
                xp_breakdown.append("Nitro: `+0.15x`")
                leaf_breakdown.append("Nitro: `+0.15x`")
                
            # Server Nitro Booster (Dating Profile)
            if self.NITRO_BOOSTER_ROLE in role_ids:
                base_pw += 1.0
                pw_breakdown.append("Nitro Booster: `+1.0x`")
                
            # Patreon Tiers (Highest applies for XP and Profile Weight)
            if self.LEGENDARY_NEKO in role_ids:
                base_xp += 0.40
                base_pw += 2.5
                xp_breakdown.append("Legendary Neko: `+0.40x`")
                pw_breakdown.append("Legendary Neko: `+2.5x`")
            elif self.KITTEN_GUARDIAN in role_ids:
                base_xp += 0.20
                base_pw += 2.0
                xp_breakdown.append("Kitten Guardian: `+0.20x`")
                pw_breakdown.append("Kitten Guardian: `+2.0x`")
            elif self.ROYAL_KITTEN in role_ids:
                base_xp += 0.10
                base_pw += 1.5
                xp_breakdown.append("Royal Kitten: `+0.10x`")
                pw_breakdown.append("Royal Kitten: `+1.5x`")

        # Global Weekend Settings
        global_doc = await self.globals_table.find_one({"isXpWeekend": {"$exists": True}}) 
        if not global_doc:
            global_doc = await self.globals_table.find_one() 

        is_weekend = global_doc.get("isXpWeekend", 0) if global_doc else 0

        # Fetch ALL active boosters for this user
        active_boosters = await self.temp_boosters.find({"discordId": discord_id_str}).to_list(length=None)
        active_ids = [b["item_id"] for b in active_boosters]

        total_xp = base_xp
        total_balance = base_leaf
        total_pw = base_pw

        if is_weekend == 1:
            total_xp *= 2.0
            xp_breakdown.append("Weekend: `x2`")
            
        if "booster_xp" in active_ids:
            total_xp *= 2.0
            xp_breakdown.append("Personal Booster: `x2`")
            
        if "booster_balance" in active_ids:
            total_balance *= 2.0
            leaf_breakdown.append("Personal Booster: `x2`")
            
        if "booster_profile" in active_ids:
            total_pw *= 2.0
            pw_breakdown.append("Profile Booster: `x2`")

        # Clean up formatting for display
        total_xp = int(total_xp) if total_xp.is_integer() else round(total_xp, 2)
        total_balance = int(total_balance) if total_balance.is_integer() else round(total_balance, 2)
        total_pw = int(total_pw) if total_pw.is_integer() else round(total_pw, 2)

        return total_xp, total_balance, total_pw, " • ".join(xp_breakdown), " • ".join(leaf_breakdown), " • ".join(pw_breakdown)

    @tasks.loop(minutes=1)
    async def clean_expired_boosters(self):
        """Passively checks the database and deletes boosters that have run out of time."""
        now = datetime.utcnow()
        expired_boosters = await self.temp_boosters.find({"end_time": {"$lte": now}}).to_list(length=None)

        if not expired_boosters:
            return

        channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.LOG_CHANNEL_ID)
            except discord.NotFound:
                pass

        guild = channel.guild if channel else None

        for booster in expired_boosters:
            discord_id = int(booster["discordId"])
            discord_id_str = booster["discordId"]
            item_name = booster.get("item_name", "Booster")
            item_id = booster.get("item_id", "")

            # Delete it before calculating so it doesn't double count
            await self.temp_boosters.delete_one({"_id": booster["_id"]})

            member = guild.get_member(discord_id) if guild else None
            total_xp, total_balance, total_pw, xp_breakdown, leaf_breakdown, pw_breakdown = await self.get_multipliers(member, discord_id_str)

            if channel:
                if item_id == "booster_xp":
                    msg = f"🛑 <@{discord_id}>, your personal **{item_name}** has expired.\n📊 **New XP Breakdown:** {xp_breakdown} ➔ **Total: `{total_xp}x`**"
                elif item_id == "booster_balance":
                    msg = f"🛑 <@{discord_id}>, your personal **{item_name}** has expired.\n📊 **New Leaf Breakdown:** {leaf_breakdown} ➔ **Total: `{total_balance}x`**"
                elif item_id == "booster_profile":
                    msg = f"🛑 <@{discord_id}>, your personal **{item_name}** has expired.\n💖 **New Profile Breakdown:** {pw_breakdown} ➔ **Total Weight: `{total_pw}x`**"
                else:
                    msg = f"🛑 <@{discord_id}>, your personal **{item_name}** has expired."
                
                await channel.send(msg)

    @app_commands.command(name="inventory", description="Manage your purchased items or use consumables")
    @app_commands.describe(
        action="Choose an action to perform",
        role_id="The ID of the role or 'random' to equip a random owned role",
        item_id="The ID of the item to use (Only needed for consumables)"
    )
    async def inventory(self, interaction: discord.Interaction, action: Literal['view', 'viewroles', 'equiprole', 'removerole', 'use'], role_id: str = None, item_id: str = None):
        if action == 'view':
            await self._view_inventory(interaction)
        elif action == 'viewroles':
            await self._view_roles(interaction)
        elif action == 'equiprole':
            if not role_id:
                return await interaction.response.send_message("You must specify a `role_id` (or 'random') to equip!")
            await self._equip_role(interaction, role_id)
        elif action == 'removerole':
            if not role_id:
                return await interaction.response.send_message("You must specify a `role_id` to remove!")
            await self._remove_role(interaction, role_id)
        elif action == 'use':
            if not item_id:
                return await interaction.response.send_message("You must specify an `item_id` to use a consumable item!")
            await self._use_item(interaction, item_id)

    async def _view_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cursor = self.user_inventory.find({"discordId": str(interaction.user.id), "type": {"$ne": "role"}})
        items = await cursor.to_list(length=None)

        if not items:
            return await interaction.followup.send("You don't have any consumables or boosters in your inventory!")

        item_counts = {}
        for item in items:
            iid = item['item_id']
            if iid not in item_counts:
                item_counts[iid] = {"data": item, "count": 1}
            else:
                item_counts[iid]["count"] += 1

        embed = discord.Embed(title=f"🎒 {interaction.user.display_name}'s Inventory (Consumables)", color=discord.Color.blue())
        
        # Display all currently active boosters
        active_boosters = await self.temp_boosters.find({"discordId": str(interaction.user.id)}).to_list(length=None)
        if active_boosters:
            desc = ""
            for b in active_boosters:
                desc += f"🔥 **Active:** `{b['item_name']}` (Ends <t:{int(b['end_time'].timestamp())}:R>)\n"
            embed.description = desc

        for iid, info in item_counts.items():
            item = info["data"]
            count = info["count"]
            name_display = f"{item['name']} (x{count})"
            desc_text = item.get("description", "No description provided.")
            img_text = f"\n**Image:** [View Here]({item['image_url']})" if item.get("image_url") else ""
                
            embed.add_field(name=name_display, value=f"*{desc_text}*{img_text}\n**ID:** `{item['item_id']}`\n**Quantity:** `{count}`", inline=True)
            
        await interaction.followup.send(embed=embed)

    async def _view_roles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cursor = self.user_inventory.find({"discordId": str(interaction.user.id), "type": "role"})
        items = await cursor.to_list(length=None)

        if not items:
            return await interaction.followup.send("You don't own any roles yet!")

        embed = discord.Embed(title=f"🎭 {interaction.user.display_name}'s Owned Roles", color=discord.Color.purple())

        for item in items:
            desc_text = item.get("description", "No description provided.")
            role_text = f"\n**Role Mention:** <@&{item['role_id']}>" if item.get('role_id') else ""
            img_text = f"\n**Image:** [View Here]({item['image_url']})" if item.get("image_url") else ""
                
            embed.add_field(name=item["name"], value=f"*{desc_text}*{img_text}\n**ID:** `{item['item_id']}`{role_text}", inline=True)
            
        await interaction.followup.send(embed=embed)

    async def _equip_role(self, interaction: discord.Interaction, role_id: str):
        await interaction.response.defer()
        
        # 1. Clean the input (removes <@& ... > if they pinged the role)
        cleaned_input = role_id.replace("<@&", "").replace(">", "").strip()
        
        role_id_int = None
        
        # 2. Check for "random" selection or standard input
        if cleaned_input.lower() == "random":
            cursor = self.user_inventory.find({"discordId": str(interaction.user.id), "type": "role"})
            owned_roles = await cursor.to_list(length=None)
            
            if not owned_roles:
                return await interaction.followup.send("❌ You do not own any roles to equip!")
                
            chosen_role = random.choice(owned_roles)
            if "role_id" in chosen_role:
                role_id_int = int(chosen_role["role_id"])
            else:
                return await interaction.followup.send("❌ A random role was selected, but its ID is missing from the database.")
                
        elif cleaned_input.isdigit():
            role_id_int = int(cleaned_input)
            # Check if they own it by role_id (supports both int and str formats in your DB)
            owned = await self.user_inventory.find_one({
                "discordId": str(interaction.user.id), 
                "role_id": {"$in": [role_id_int, str(role_id_int)]}
            })
            if not owned:
                role_id_int = None
        else:
            # They typed a text name like "watermelon" instead of an ID
            owned = await self.user_inventory.find_one({
                "discordId": str(interaction.user.id), 
                "item_id": cleaned_input.lower()
            })
            if owned and "role_id" in owned:
                role_id_int = int(owned["role_id"])

        if not role_id_int:
            return await interaction.followup.send("❌ You do not own this role, or the ID is invalid.")
            
        # 3. Fetch the actual Role object from the server
        role = interaction.guild.get_role(role_id_int)
        if not role:
            return await interaction.followup.send("❌ Could not find a role with that ID in this server.")

        if role in interaction.user.roles:
            return await interaction.followup.send("You already have this role equipped.")

        # Get a list of all role IDs that exist in your shop
        try:
            from store.items import SHOP_ITEMS
            shop_role_ids = {item["role_id"] for item in SHOP_ITEMS if "role_id" in item}
        except ImportError:
            shop_role_ids = set() # Fallback if import fails

        # Identify which of the user's current roles are from the shop
        roles_to_remove = [r for r in interaction.user.roles if r.id in shop_role_ids]

        try:
            # Remove existing shop roles first
            if roles_to_remove:
                await interaction.user.remove_roles(*roles_to_remove, reason="Equipping new shop role")

            # Add the new role
            await interaction.user.add_roles(role, reason="Equipped from inventory")
            
            await interaction.followup.send(f"✅ Successfully equipped the **{role.name}** role!")
            
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to manage your roles. Make sure my bot's role is positioned higher than the shop roles in the server settings!")
        except discord.HTTPException:
            await interaction.followup.send("An error occurred while updating your roles.")
            
    async def _remove_role(self, interaction: discord.Interaction, role_id: str):
        await interaction.response.defer()
        
        # 1. Clean the input (removes <@& ... > if they pinged the role)
        cleaned_input = role_id.replace("<@&", "").replace(">", "").strip()
        role_id_int = None
        
        # 2. Check if input is numeric (Role ID) or text (Item ID)
        if cleaned_input.isdigit():
            role_id_int = int(cleaned_input)
            owned = await self.user_inventory.find_one({
                "discordId": str(interaction.user.id), 
                "role_id": {"$in": [role_id_int, str(role_id_int)]}
            })
        else:
            owned = await self.user_inventory.find_one({
                "discordId": str(interaction.user.id), 
                "item_id": cleaned_input.lower()
            })
            if owned and "role_id" in owned:
                role_id_int = int(owned["role_id"])

        if not owned or not role_id_int:
            return await interaction.followup.send("❌ You do not own this role in your inventory.")
            
        # 3. Fetch the actual Role object from the server
        role = interaction.guild.get_role(role_id_int)
        if not role:
            return await interaction.followup.send("❌ Could not find a role with that ID in this server.")

        if role not in interaction.user.roles:
            return await interaction.followup.send("❌ You do not currently have this role equipped.")

        try:
            await interaction.user.remove_roles(role, reason="Removed from inventory")
            await interaction.followup.send(f"✅ Successfully removed the **{role.name}** role.")
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to manage this role.")


    async def _use_item(self, interaction: discord.Interaction, item_id: str):
        await interaction.response.defer()
        user_id_str = str(interaction.user.id)

        item = await self.user_inventory.find_one({"discordId": user_id_str, "item_id": item_id})
        if not item:
            return await interaction.followup.send("You do not own this item or you have run out of it!")

        if item.get("type") != "booster":
            return await interaction.followup.send("This item cannot be 'used' like a consumable.")

        # --- Check for Dating Profile if using Profile Booster ---
        if item_id == "booster_profile":
            # Check integer ID or String ID for primary key
            profile = await self.dating_profile.find_one({"_id": interaction.user.id})
            if not profile:
                profile = await self.dating_profile.find_one({"_id": user_id_str}) # fallback
                
            if not profile:
                return await interaction.followup.send("❌ You cannot use this booster because you haven't created a dating profile yet!")

        # Check ONLY for this specific type of booster
        active_booster = await self.temp_boosters.find_one({"discordId": user_id_str, "item_id": item_id})
        
        # Build preview message
        duration_hrs = item.get('duration', 3600) / 3600
        
        if duration_hrs >= 24:
            duration_str = f"{int(duration_hrs // 24)} day(s)"
        else:
            duration_str = f"{int(duration_hrs)} hour(s)"
            
        desc = item.get("description", f"Boosts your stats for {duration_str}.")
        
        embed = discord.Embed(title="Confirm Item Use", color=discord.Color.yellow())
        embed.description = f"Are you sure you want to use **{item['name']}**?\n\n*\"{desc}\"*\n"

        if active_booster:
            new_end = active_booster["end_time"] + timedelta(seconds=item.get("duration", 3600))
            embed.description += f"\n⚠️ **Warning:** You already have this booster active. Using it now will **add** to your timer, extending it to <t:{int(new_end.timestamp())}:R>."

        view = UseConfirmView(self, item, user_id_str, active_booster)
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Inventory(bot))