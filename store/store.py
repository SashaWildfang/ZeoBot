import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import random
from typing import Literal
from db.database import get_connection

# 📦 Import your shop items from the separate file
from store.items import SHOP_ITEMS

# ===============================
# Interactive UI Views
# ===============================
class BuyConfirmView(discord.ui.View):
    def __init__(self, cog, item, user_id, user_id_str, query_id, price):
        super().__init__(timeout=60)
        self.cog = cog
        self.item = item
        self.user_id = user_id
        self.user_id_str = user_id_str
        self.query_id = query_id
        self.price = price
        self.used = False

    @discord.ui.button(label="Confirm Purchase", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            # We keep this one ephemeral so it doesn't spam chat if someone else clicks it!
            return await interaction.response.send_message("This is not your menu!", ephemeral=True)
        if self.used: 
            return
        self.used = True

        # Re-check balance just in case they spent Leaves while the menu was open
        balance, _ = await self.cog.get_user_balance(self.user_id)
        if balance < self.price:
            return await interaction.response.edit_message(content="❌ You no longer have enough Leaves to complete this purchase!", embed=None, view=None)

        # Deduct balance
        await self.cog.economy.update_one({"discordId": self.query_id}, {"$inc": {"balance": -self.price}}, upsert=True)
        
        # Deduct stock
        if self.item["quantity"] > 0:
            await self.cog.store_inventory.update_one({"item_id": self.item["item_id"]}, {"$inc": {"quantity": -1}})

        # Add item to inventory
        await self.cog.user_inventory.insert_one({
            "discordId": self.user_id_str,
            "item_id": self.item["item_id"],
            "name": self.item["name"],
            "description": self.item.get("description", "No description provided."),
            "image_url": self.item.get("image_url", ""),
            "role_id": self.item.get("role_id"),
            "type": self.item.get("type", "role"),
            "duration": self.item.get("duration"),
            "purchasedAt": datetime.utcnow()
        })

        # Log the sale
        await self.cog.store_sales.insert_one({
            "buyerId": self.user_id_str,
            "item_id": self.item["item_id"],
            "price_paid": self.price,
            "timestamp": datetime.utcnow()
        })

        await interaction.response.edit_message(content=f"✅ Successfully purchased **{self.item['name']}**!", embed=None, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This is not your menu!", ephemeral=True)
        self.used = True
        await interaction.response.edit_message(content="❌ Purchase canceled.", embed=None, view=None)


class StoreMainView(discord.ui.View):
    def __init__(self, cog, categories):
        super().__init__(timeout=300) 
        self.cog = cog
        self.categories = categories
        
        for category in categories:
            btn = discord.ui.Button(
                label=category, 
                style=discord.ButtonStyle.primary, 
                custom_id=f"store_cat_{category}"
            )
            btn.callback = self.create_callback(category)
            self.add_item(btn)

    def create_callback(self, category_name):
        async def button_callback(interaction: discord.Interaction):
            # Fetch balance & timers
            balance, _ = await self.cog.get_user_balance(interaction.user.id)
            settings = await self.cog.shop_settings.find_one({"_id": "rotation_timers"})
            daily_end = int(settings['next_daily'].timestamp()) if settings else 0
            weekly_end = int(settings['next_weekly'].timestamp()) if settings else 0

            # Fetch user's inventory to check for owned items
            user_inv_cursor = self.cog.user_inventory.find({"discordId": str(interaction.user.id)})
            user_owned_docs = await user_inv_cursor.to_list(length=None)
            owned_item_ids = {doc["item_id"] for doc in user_owned_docs}

            # Fetch active items for this specific category
            cursor = self.cog.store_inventory.find({
                "category": category_name, 
                "is_active": True, 
                "quantity": {"$ne": 0}
            })
            items = await cursor.to_list(length=100)

            # 🗂️ Custom Sorting: Daily -> Weekly -> Perm, then Owned -> Unowned, then Alphabetical
            def sort_key(item):
                rot_order = {"daily": 0, "weekly": 1, "permanent": 2}.get(item.get("rotation_type", "permanent"), 3)
                is_owned = item['item_id'] in owned_item_ids
                return (rot_order, 0 if is_owned else 1, item['name'].lower())
            
            items.sort(key=sort_key)

            embed = discord.Embed(
                title=f"Store Category: {category_name} ({len(items)})",
                description=(
                    f"**Your Balance:** **{balance:,}** <:leaf:1524758896659660831>\n"
                    "*Use `/store buy <id>` to purchase an item.*\n"
                ),
                color=discord.Color.blue()
            )

            if not items:
                embed.description += "\n\n*No items currently available in this category.*"
            else:
                current_section = None
                for item in items:
                    rot_type = item.get("rotation_type", "permanent")
                    
                    # 📌 Add Section Headers when the rotation type changes
                    if rot_type != current_section:
                        current_section = rot_type
                        if current_section == "daily":
                            embed.add_field(name=f"━━━━━━━━━━━━━━━━━━━━\n⏳ Daily Deal(s) — Ends <t:{daily_end}:R>", value="\u200b", inline=False)
                        elif current_section == "weekly":
                            embed.add_field(name=f"━━━━━━━━━━━━━━━━━━━━\n📆 Weekly Deal(s) — Ends <t:{weekly_end}:R>", value="\u200b", inline=False)
                        elif current_section == "permanent":
                            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━\n🏪 Permanent Store", value="\u200b", inline=False)

                    is_owned = item['item_id'] in owned_item_ids
                    
                    # Icons: Boosters show package, Roles/Others show check/X
                    if category_name == "Boosters" or item.get("category") == "Consumables":
                        ownership_emoji = "📦"
                    else:
                        ownership_emoji = "✅" if is_owned else "❌"

                    qty_text = f"\n**Stock:** {item['quantity']}" if item["quantity"] != -1 else ""
                    title_name = f"{ownership_emoji} {item['name']}"
                    desc_text = item.get("description", "No description provided.")
                        
                    mention_text = ""
                    if category_name == "Roles" and item.get("role_id"):
                        mention_text = f"<@&{item['role_id']}>\n"
                        
                    img_text = ""
                    if item.get("image_url"):
                        img_text = f"\n**Image:** [View Here]({item['image_url']})"

                    embed.add_field(
                        name=title_name, 
                        value=f"{mention_text}*{desc_text}*{img_text}\n**ID:** `{item['item_id']}`\n**Price:** {item['price']:,} <:leaf:1524758896659660831>{qty_text}", 
                        inline=True 
                    )

            view = StoreBackView(self.cog, self.categories)
            await interaction.response.edit_message(embed=embed, view=view)
        return button_callback

class StoreBackView(discord.ui.View):
    def __init__(self, cog, categories):
        super().__init__(timeout=300)
        self.cog = cog
        self.categories = categories

    @discord.ui.button(label="Back to Menu", style=discord.ButtonStyle.secondary, custom_id="store_back_btn")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        balance, query_id = await self.cog.get_user_balance(interaction.user.id)
        settings = await self.cog.shop_settings.find_one({"_id": "rotation_timers"})
        daily_end = int(settings['next_daily'].timestamp()) if settings else 0
        weekly_end = int(settings['next_weekly'].timestamp()) if settings else 0
        
        last_item = await self.cog.user_inventory.find_one(
            {"discordId": str(interaction.user.id)},
            sort=[("purchasedAt", -1)]
        )
        last_purchase_text = f"\n**Last Purchase:** {last_item['name']} (<t:{int(last_item['purchasedAt'].timestamp())}:R>)" if last_item else "\n**Last Purchase:** None yet!"

        embed = discord.Embed(
            title="Welcome to the Server Store!", 
            description=(
                "Browse our rotating selection of items to customize your profile.\n\n"
                f"**Your Balance:** **{balance:,}** <:leaf:1524758896659660831>{last_purchase_text}\n\n"
                "**Commands:**\n"
                "**Buy:** `/store buy <id>`\n"
                "**Inventory:** `/inventory view`\n"
                "**Equip/Remove:** `/inventory equiprole <@role>`\n"
                "**Use Item:** `/inventory use <id>`\n\n"
                "*Select a category below to see what's in stock!*"
            ),
            color=discord.Color.gold()
        )

        daily_items = await self.cog.store_inventory.find({"is_active": True, "rotation_type": "daily", "quantity": {"$ne": 0}}).to_list(length=10)
        if daily_items:
            daily_text = "\n".join([f"• **({item.get('category', 'Misc')}) {item['name']}** - {item['price']:,} <:leaf:1524758896659660831> (Ends <t:{daily_end}:R>)" for item in daily_items])
            embed.add_field(name="⏳ Today's Daily Deals", value=daily_text, inline=False)
        else:
            embed.add_field(name="⏳ Today's Daily Deals", value="*No daily deals currently active.*", inline=False)

        weekly_items = await self.cog.store_inventory.find({"is_active": True, "rotation_type": "weekly", "quantity": {"$ne": 0}}).to_list(length=10)
        if weekly_items:
            weekly_text = "\n".join([f"• **({item.get('category', 'Misc')}) {item['name']}** - {item['price']:,} <:leaf:1524758896659660831> (Ends <t:{weekly_end}:R>)" for item in weekly_items])
            embed.add_field(name="📆 This Week's Deals", value=weekly_text, inline=False)
        else:
            embed.add_field(name="📆 This Week's Deals", value="*No weekly deals currently active.*", inline=False)

        view = StoreMainView(self.cog, self.categories)
        await interaction.response.edit_message(embed=embed, view=view)


# ===============================
# Store Cog
# ===============================
class Store(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        
        self.store_inventory = self.db["store_inventory"]
        self.store_sales = self.db["store_sales"]
        self.user_inventory = self.db["user_inventory"]
        self.economy = self.db["users"] 
        self.shop_settings = self.db["shop_settings"]

        self.bot.loop.create_task(self.seed_inventory())
        self.rotate_shop.start()

    def cog_unload(self):
        self.rotate_shop.cancel()

    async def get_user_balance(self, user_id: int):
        query_id = user_id
        user_doc = await self.economy.find_one({"discordId": query_id})
        
        if not user_doc:
            query_id = str(user_id)
            user_doc = await self.economy.find_one({"discordId": query_id})
            
        balance = user_doc.get("balance", 0) if user_doc else 0
        return balance, query_id

    async def seed_inventory(self):
        for raw_item in SHOP_ITEMS:
            item = raw_item.copy()
            default_active = item.pop("is_active", False)
            
            await self.store_inventory.update_one(
                {"item_id": item["item_id"]},
                {
                    "$set": item, 
                    "$setOnInsert": {"is_active": default_active} 
                },
                upsert=True
            )

    async def _announce_rotation(self, rotation_type: str, new_items: list, ends_at: datetime):
        channel = self.bot.get_channel(1358485891361804358)
        if not channel:
            return
            
        ping_role = "<@&1503069470908878969>"
        
        embed = discord.Embed(
            title=f"🛒 Store Rotation: New {rotation_type.capitalize()} Items!",
            description=f"The store has just updated with new **{rotation_type}** items!\nThese will be available until <t:{int(ends_at.timestamp())}:R>.\n\n**New Items:**\n",
            color=discord.Color.gold()
        )
        
        if new_items:
            for item in new_items:
                embed.description += f"• **({item.get('category', 'Misc')}) {item['name']}** - {item['price']:,} <:leaf:1524758896659660831>\n"
        else:
            embed.description += "*No new items available.*"
            
        embed.set_footer(text="Use /store view to check them out!")
        await channel.send(content=ping_role, embed=embed)

    @tasks.loop(minutes=30)
    async def rotate_shop(self):
        await self.bot.wait_until_ready()
        now = datetime.utcnow()

        settings = await self.shop_settings.find_one({"_id": "rotation_timers"})
        if not settings:
            settings = {"_id": "rotation_timers", "next_daily": now, "next_weekly": now}
            await self.shop_settings.insert_one(settings)

        if now >= settings["next_daily"]:
            chosen_daily = await self._rotate_pool("daily", max_active=3) # Changed to 3
            new_daily_time = now + timedelta(days=1)
            await self.shop_settings.update_one({"_id": "rotation_timers"}, {"$set": {"next_daily": new_daily_time}})
            await self._announce_rotation("daily", chosen_daily, new_daily_time)

        if now >= settings["next_weekly"]:
            chosen_weekly = await self._rotate_pool("weekly", max_active=1)
            new_weekly_time = now + timedelta(days=7)
            await self.shop_settings.update_one({"_id": "rotation_timers"}, {"$set": {"next_weekly": new_weekly_time}})
            await self._announce_rotation("weekly", chosen_weekly, new_weekly_time)

    async def _rotate_pool(self, rotation_type: str, max_active: int):
        await self.store_inventory.update_many({"rotation_type": rotation_type}, {"$set": {"is_active": False}})
        cursor = self.store_inventory.find({"rotation_type": rotation_type})
        pool = await cursor.to_list(length=100)
        
        chosen = []
        if pool:
            num_to_activate = min(max_active, len(pool)) if isinstance(max_active, int) else 1
            chosen = random.sample(pool, k=num_to_activate)
            for item in chosen:
                update_data = {"is_active": True}
                if "max_quantity" in item:
                    update_data["quantity"] = item["max_quantity"]
                await self.store_inventory.update_one({"item_id": item["item_id"]}, {"$set": update_data})
                
        return chosen

    @app_commands.command(name="storeadmin", description="Admin command to force rotate shop pools")
    @app_commands.describe(action="Choose which rotation to reset")
    @app_commands.default_permissions(administrator=True) 
    async def storeadmin(self, interaction: discord.Interaction, action: Literal['resetdaily', 'resetweekly']):
        await interaction.response.defer(ephemeral=True) # Kept ephemeral so admin commands remain hidden
        
        if action == 'resetdaily':
            chosen_daily = await self._rotate_pool("daily", max_active=3)
            now = datetime.utcnow()
            new_daily_time = now + timedelta(days=1)
            await self.shop_settings.update_one(
                {"_id": "rotation_timers"}, 
                {"$set": {"next_daily": new_daily_time}},
                upsert=True
            )
            await self._announce_rotation("daily", chosen_daily, new_daily_time)
            await interaction.followup.send("✅ Successfully forced a **Daily** shop rotation!")
            
        elif action == 'resetweekly':
            chosen_weekly = await self._rotate_pool("weekly", max_active=1)
            now = datetime.utcnow()
            new_weekly_time = now + timedelta(days=7)
            await self.shop_settings.update_one(
                {"_id": "rotation_timers"}, 
                {"$set": {"next_weekly": new_weekly_time}},
                upsert=True
            )
            await self._announce_rotation("weekly", chosen_weekly, new_weekly_time)
            await interaction.followup.send("✅ Successfully forced a **Weekly** shop rotation!")

    @app_commands.command(name="store", description="View the store or buy an item")
    @app_commands.describe(
        action="Choose whether to view the store menu or buy an item",
        item_id="The ID of the item (Only required if you are buying)"
    )
    async def store(self, interaction: discord.Interaction, action: Literal['view', 'buy'], item_id: str = None):
        if action == 'view':
            await self._view_store(interaction)
        elif action == 'buy':
            if not item_id:
                return await interaction.response.send_message("You must provide an `item_id` if you want to buy something!")
            await self._buy_item(interaction, item_id)

    async def _view_store(self, interaction: discord.Interaction):
        balance, _ = await self.get_user_balance(interaction.user.id)
        settings = await self.shop_settings.find_one({"_id": "rotation_timers"})
        daily_end = int(settings['next_daily'].timestamp()) if settings else 0
        weekly_end = int(settings['next_weekly'].timestamp()) if settings else 0
        
        last_item = await self.user_inventory.find_one(
            {"discordId": str(interaction.user.id)},
            sort=[("purchasedAt", -1)]
        )
        last_purchase_text = f"\n**Last Purchase:** {last_item['name']} (<t:{int(last_item['purchasedAt'].timestamp())}:R>)" if last_item else "\n**Last Purchase:** None yet!"

        active_items = await self.store_inventory.find({"is_active": True, "quantity": {"$ne": 0}}).to_list(length=100)
        categories = list(set(item.get("category", "Misc") for item in active_items))
        categories.sort()

        if not categories:
            return await interaction.response.send_message("The store is currently empty! Check back later.")

        embed = discord.Embed(
            title="Welcome to the Server Store!", 
            description=(
                "Browse our rotating selection of items to customize your profile.\n\n"
                f"**Your Balance:** **{balance:,}** <:leaf:1524758896659660831>{last_purchase_text}\n\n"
                "**Commands:**\n"
                "**Buy:** `/store buy <id>`\n"
                "**Inventory:** `/inventory view`\n"
                "**Equip/Remove:** `/inventory equiprole <@role>`\n"
                "**Use Item:** `/inventory use <id>`\n\n"
                "*Select a category below to see what's in stock!*"
            ),
            color=discord.Color.gold()
        )

        daily_items = await self.store_inventory.find({"is_active": True, "rotation_type": "daily", "quantity": {"$ne": 0}}).to_list(length=10)
        if daily_items:
            daily_text = "\n".join([f"• **({item.get('category', 'Misc')}) {item['name']}** - {item['price']:,} <:leaf:1524758896659660831> (Ends <t:{daily_end}:R>)" for item in daily_items])
            embed.add_field(name="⏳ Today's Daily Deals", value=daily_text, inline=False)
        else:
            embed.add_field(name="⏳ Today's Daily Deals", value="*No daily deals currently active.*", inline=False)

        weekly_items = await self.store_inventory.find({"is_active": True, "rotation_type": "weekly", "quantity": {"$ne": 0}}).to_list(length=10)
        if weekly_items:
            weekly_text = "\n".join([f"• **({item.get('category', 'Misc')}) {item['name']}** - {item['price']:,} <:leaf:1524758896659660831> (Ends <t:{weekly_end}:R>)" for item in weekly_items])
            embed.add_field(name="📆 This Week's Deals", value=weekly_text, inline=False)
        else:
            embed.add_field(name="📆 This Week's Deals", value="*No weekly deals currently active.*", inline=False)

        view = StoreMainView(self, categories)
        await interaction.response.send_message(embed=embed, view=view)

    async def _buy_item(self, interaction: discord.Interaction, item_id: str):
        # Changed this defer to no longer be ephemeral!
        await interaction.response.defer()
        user_id_str = str(interaction.user.id)

        item = await self.store_inventory.find_one({"item_id": item_id})
        if not item or not item.get("is_active", False):
            return await interaction.followup.send("Item not found or is not currently in rotation.")
        
        if item["quantity"] == 0:
            return await interaction.followup.send("This item is currently out of stock.")

        if item.get("category") not in ["Consumables", "Boosters"]:
            already_owns = await self.user_inventory.find_one({"discordId": user_id_str, "item_id": item_id})
            if already_owns:
                return await interaction.followup.send("You already own this item!")

        daily_limit = item.get("daily_limit")
        if daily_limit:
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
            bought_count = await self.store_sales.count_documents({
                "buyerId": user_id_str,
                "item_id": item_id,
                "timestamp": {"$gte": twenty_four_hours_ago}
            })
            if bought_count >= daily_limit:
                return await interaction.followup.send(f"You have reached the daily limit of **{daily_limit}** for this item!")

        balance, query_id = await self.get_user_balance(interaction.user.id)
        if balance < item["price"]:
            return await interaction.followup.send(f"You don't have enough Leaves! You need **{item['price']:,}** <:leaf:1524758896659660831>")

        # Calculate new balance for the preview
        new_balance = balance - item["price"]

        # Build preview embed
        embed = discord.Embed(
            title="🛒 Confirm Purchase",
            description=(
                f"Are you sure you want to buy **{item['name']}**?\n\n"
                f"**Price:** {item['price']:,} <:leaf:1524758896659660831>\n"
                f"**Current Balance:** {balance:,} <:leaf:1524758896659660831>\n"
                f"**Balance After Purchase:** {new_balance:,} <:leaf:1524758896659660831>"
            ),
            color=discord.Color.yellow()
        )

        view = BuyConfirmView(self, item, interaction.user.id, user_id_str, query_id, item["price"])
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Store(bot))