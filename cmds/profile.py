import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
from datetime import datetime
from db.database import get_connection

# ==========================================
# CONFIRMATION UI
# ==========================================
class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.value = None
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

# ==========================================
# UI CLASSES FOR EDITING
# ==========================================
class ProfileEditModal(discord.ui.Modal):
    def __init__(self, category_name: str, fields: dict, current_data: dict, db_collection):
        super().__init__(title=f"Edit {category_name}")
        self.db_collection = db_collection
        self.db_keys = []

        for label, db_key in fields.items():
            self.db_keys.append(db_key)
            
            paragraph_fields = ["bio", "likes", "dislikes", "fun_fact", "green_flags", "red_flags", "dealbreakers"]
            input_style = discord.TextStyle.paragraph if db_key in paragraph_fields else discord.TextStyle.short
            
            max_len = 1000 if db_key == "bio" else (300 if db_key in paragraph_fields else 150)
            
            text_input = discord.ui.TextInput(
                label=label,
                style=input_style,
                default=current_data.get(db_key, ""), 
                required=False, 
                max_length=max_len
            )
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        updates = {}
        
        for item, db_key in zip(self.children, self.db_keys):
            val = item.value.strip().replace("’", "'").replace("`", "'")
            if val: 
                updates[db_key] = val

        if updates:
            await self.db_collection.update_one(
                {"_id": interaction.user.id},
                {"$set": updates},
                upsert=True
            )
            await interaction.response.send_message(f"✅ Your `{self.title.replace('Edit ', '')}` section has been updated!", ephemeral=True)
        else:
            await interaction.response.send_message("No changes were made.", ephemeral=True)

class ProfileEditSelect(discord.ui.Select):
    def __init__(self, current_data, db_collection):
        self.current_data = current_data
        self.db_collection = db_collection
        
        options = [
            discord.SelectOption(label="Basics & Bio", description="Name, Age, Fun Fact, Bio", emoji="👤"),
            discord.SelectOption(label="Identity", description="Gender, Pronouns, Sexuality, Position", emoji="🏳️‍🌈"),
            discord.SelectOption(label="Physical Traits", description="Body Type, Height, Weight", emoji="🧍"),
            discord.SelectOption(label="Logistics", description="Location, Timezone, Status, Work, Independence", emoji="🌍"),
            discord.SelectOption(label="Lifestyle & Values", description="Sleep, Activity, Kids, Marriage, Religion", emoji="🏡"),
            
            discord.SelectOption(label="Dating Targets", description="Looking?, Genders, Ages, Target Pos.", emoji="❤️"),
            discord.SelectOption(label="Distance & Travel", description="LDR?, Max Dist, Relocating", emoji="✈️"),
            discord.SelectOption(label="Vices Comfort", description="Smoking, Drinking, Substances", emoji="🍷"),
            discord.SelectOption(label="Partner Flags", description="Indep. Level, Green Flags, Red Flags, Deals", emoji="🚩"),
            
            discord.SelectOption(label="Interests", description="Likes, Dislikes, Hobbies, Games", emoji="🎮"),
            discord.SelectOption(label="Media Favorites", description="Movie, Anime, Song, Artist", emoji="🎬"),
            discord.SelectOption(label="More Favorites", description="Food, Drink, Color, Animal", emoji="🍕"),
            discord.SelectOption(label="Social Media", description="Twitter, Telegram, FA, Insta", emoji="🌐"),
            discord.SelectOption(label="Gaming Tags", description="Steam, Switch, Xbox, PlayStation", emoji="👾")
        ]
        super().__init__(placeholder="Choose a section to edit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        field_maps = {
            "Basics & Bio": {"Name": "name", "Age": "age", "Fun Fact": "fun_fact", "Bio": "bio"},
            "Identity": {"Gender": "gender", "Pronouns": "pronouns", "Sexuality": "sexuality", "Position": "sexual_position"},
            "Physical Traits": {"Body Type": "body_type", "Height": "height", "Weight": "weight"},
            "Logistics": {"Location": "location", "Status": "relationship_status", "Work/Ed": "what_do_you_do_for_work_education", "Independence (1-10)": "independence_level"},
            "Lifestyle & Values": {"Sleep": "sleep_schedule", "Activity": "activity_level", "Want Kids?": "want_kids", "Marriage?": "marriage_goals", "Religion?": "religion_important"},
            
            "Dating Targets": {"Open to Dating?": "is_looking", "Target Genders": "looking_for_gender", "Min Age": "looking_for_min_age", "Max Age": "looking_for_max_age", "Target Position": "looking_for_sexual_position"},
            "Distance & Travel": {"Distance Comfort": "distance_comfort", "Max Distance": "max_distance", "I'd Relocate?": "willing_to_relocate", "Partner Relocate?": "partner_relocate"},
            "Vices Comfort": {"Smoking OK?": "smoking_ok", "Drinking OK?": "drinking_ok", "Substances OK?": "substance_ok"},
            "Partner Flags": {"Partner Indep. (1-10)": "partner_independence_level", "Green Flags": "green_flags", "Red Flags": "red_flags", "Dealbreakers": "dealbreakers"},
            
            "Interests": {"Likes": "likes", "Dislikes": "dislikes", "Hobbies": "hobbies_interests", "Games": "favorite_games"},
            "Media Favorites": {"Movie": "favorite_anime", "Song": "favorite_song", "Artist": "favorite_artist_band"},
            "More Favorites": {"Food": "favorite_drink", "Color": "favorite_color", "Animal": "favorite_animal"},
            "Social Media": {"Twitter": "twitter", "Telegram": "telegram", "FurAffinity": "furaffinity", "Instagram": "instagram"},
            "Gaming Tags": {"Steam": "steam", "Nintendo Switch": "nintendo_switch", "Xbox": "xbox", "PlayStation": "playstation"}
        }

        selected = self.values[0]
        fields = field_maps[selected]

        modal = ProfileEditModal(selected, fields, self.current_data, self.db_collection)
        await interaction.response.send_modal(modal)

class ProfileEditView(discord.ui.View):
    def __init__(self, current_data, db_collection):
        super().__init__(timeout=180)
        self.add_item(ProfileEditSelect(current_data, db_collection))

# ==========================================
# UI CLASS FOR TABBED NAVIGATION & LIKES
# ==========================================
class ProfilePaginator(discord.ui.View):
    def __init__(self, target_user: discord.Member, profile_data: dict, author: discord.Member, likes_collection, activity_collection, passes_collection, total_likes: int, user_likes: list, historical_likers: list, user_passes: list):
        super().__init__(timeout=900)
        self.target_user = target_user
        self.profile_data = profile_data
        self.author = author
        self.likes_collection = likes_collection
        self.activity_collection = activity_collection
        self.passes_collection = passes_collection
        self.total_likes = total_likes
        self.user_likes = user_likes
        self.historical_likers = historical_likers
        self.user_passes = user_passes
        self.NITRO_ROLE_ID = 1360260086500561237
        
        self.is_self_view = (self.target_user.id == self.author.id)
        
        # Extract buttons attached via decorators
        self.btn_action_item = self.children[0]
        self.btn_pass_item = self.children[1]
        self.btn_main_item = self.children[2]
        self.btn_looking_item = self.children[3]
        self.btn_interests_item = self.children[4]
        self.btn_socials_item = self.children[5]
        self.btn_fursonas_item = self.children[6]
        
        self.refresh_action_buttons()
        self.update_view("main")

    def refresh_action_buttons(self):
        # Like Button Logic
        if self.is_self_view:
            if self.total_likes > 0:
                self.btn_action_item.label = "👀 View My Likes"
                self.btn_action_item.style = discord.ButtonStyle.success
                self.btn_action_item.disabled = False
            else:
                self.btn_action_item.label = "Your Likes: 0"
                self.btn_action_item.style = discord.ButtonStyle.secondary
                self.btn_action_item.disabled = True
        else:
            has_liked = any(like["liker_id"] == self.author.id for like in self.user_likes)
            if has_liked:
                self.btn_action_item.label = "💔 Unlike"
                self.btn_action_item.style = discord.ButtonStyle.secondary
            else:
                self.btn_action_item.label = "💚 Like"
                self.btn_action_item.style = discord.ButtonStyle.success

        # Pass Button Logic
        if not self.is_self_view:
            has_passed = any((isinstance(p, dict) and p.get("user_id") == self.target_user.id) or p == self.target_user.id for p in self.user_passes)
            if has_passed:
                self.btn_pass_item.label = "Undo Not Interested (Click)"
                self.btn_pass_item.style = discord.ButtonStyle.danger
            else:
                self.btn_pass_item.label = "I'm not Interested (Click)"
                self.btn_pass_item.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You cannot interact with this menu. Run `/profile` yourself!", ephemeral=True)
            return False
        return True

    def update_view(self, active_page: str):
        self.clear_items()
        
        if active_page != "my_likes": 
            self.add_item(self.btn_action_item)
            if not self.is_self_view:
                self.add_item(self.btn_pass_item)
        
        if active_page != "main": self.add_item(self.btn_main_item)
        if active_page != "looking": self.add_item(self.btn_looking_item)
        if active_page != "interests": self.add_item(self.btn_interests_item)
        if active_page != "socials": self.add_item(self.btn_socials_item)
        
        fursonas_list = self.profile_data.get("fursonas", [])
        if fursonas_list and active_page != "fursonas":
            self.btn_fursonas_item.label = "🐾 Fursonas" if len(fursonas_list) > 1 else "🐾 Fursona"
            self.add_item(self.btn_fursonas_item)

    # --- HELPER: CONDITIONAL FIELD ADDER ---
    def _add_field(self, embed: discord.Embed, name: str, value: str, inline: bool = True):
        """Only adds a field if it's not None, empty, or 'N/A'"""
        if value and str(value).strip() != "" and str(value).strip().lower() != "n/a":
            embed.add_field(name=name, value=str(value).strip(), inline=inline)

    # --- EMBED GENERATORS ---
    def get_main_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"👤 {self.target_user.display_name}'s Profile",
            description=f"**Discord:** {self.target_user.mention}",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        self._add_field(embed, "Name", self.profile_data.get("name"), inline=True)
        self._add_field(embed, "Age", self.profile_data.get("age"), inline=True)
        self._add_field(embed, "Gender", self.profile_data.get("gender"), inline=True)
        
        self._add_field(embed, "Pronouns", self.profile_data.get("pronouns"), inline=True)
        self._add_field(embed, "Location", self.profile_data.get("location"), inline=True)
        self._add_field(embed, "Timezone", self.profile_data.get("timezone"), inline=True)
        
        self._add_field(embed, "Status", self.profile_data.get("relationship_status"), inline=True)
        self._add_field(embed, "Sexuality", self.profile_data.get("sexuality"), inline=True)
        self._add_field(embed, "Sexual Position", self.profile_data.get("sexual_position"), inline=True)
        
        self._add_field(embed, "Body Type", self.profile_data.get("body_type"), inline=True)
        self._add_field(embed, "Height", self.profile_data.get("height"), inline=True)
        self._add_field(embed, "Weight", self.profile_data.get("weight"), inline=True) 
        
        self._add_field(embed, "Work / Education", self.profile_data.get("what_do_you_do_for_work_education"), inline=False)
        
        # Build lifestyle string dynamically so we don't display empty categories
        lifestyle_parts = []
        indep = self.profile_data.get('independence_level')
        if indep and str(indep).lower() != "n/a": lifestyle_parts.append(f"**Independence:** {indep}/10")
        
        sleep = self.profile_data.get('sleep_schedule')
        if sleep and str(sleep).lower() != "n/a": lifestyle_parts.append(f"**Sleep:** {sleep}")
        
        act = self.profile_data.get('activity_level')
        if act and str(act).lower() != "n/a": lifestyle_parts.append(f"**Activity:** {act}")
        
        kids = self.profile_data.get('want_kids')
        if kids and str(kids).lower() != "n/a": lifestyle_parts.append(f"**Kids:** {kids}")
        
        mrg = self.profile_data.get('marriage_goals')
        if mrg and str(mrg).lower() != "n/a": lifestyle_parts.append(f"**Marriage:** {mrg}")
        
        rel = self.profile_data.get('religion_important')
        if rel and str(rel).lower() != "n/a": lifestyle_parts.append(f"**Religion Important?:** {rel}")

        if lifestyle_parts:
            self._add_field(embed, "🏡 Lifestyle & Values", " | ".join(lifestyle_parts), inline=False)
        
        fursonas_list = self.profile_data.get("fursonas", [])
        if fursonas_list:
            self._add_field(embed, "🐾 Fursonas", f"Has {len(fursonas_list)} Fursona(s) — Check the button below!", inline=False)
        
        self._add_field(embed, "✨ Fun Fact", self.profile_data.get("fun_fact"), inline=False)
        self._add_field(embed, "📖 Bio", self.profile_data.get("bio"), inline=False)
        
        if self.is_self_view:
            self._add_field(embed, "💚 Your Total Likes", f"**{self.total_likes}**", inline=False)

        if not embed.fields:
            embed.description += "\n\n*No details have been filled out for this section yet.*"

        return embed

    def get_looking_for_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔍 What {self.target_user.display_name} is Looking For",
            color=discord.Color.brand_red()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        is_looking = self.profile_data.get("is_looking", "N/A").strip().lower()
        if is_looking in ["no", "n"]:
            embed.description = "🚫 **This user is not currently looking for a relationship.**\nThey are likely here for friends, gaming, or community!"
            return embed

        min_age = self.profile_data.get("looking_for_min_age", "?")
        max_age = self.profile_data.get("looking_for_max_age", "?")
        if min_age != "?" or max_age != "?":
            self._add_field(embed, "Target Age Range", f"**{min_age} - {max_age}**", inline=True)
            
        self._add_field(embed, "Target Gender(s)", self.profile_data.get("looking_for_gender"), inline=True)
        self._add_field(embed, "Relationship Type", self.profile_data.get("looking_for_relationship_type"), inline=True)
        self._add_field(embed, "Target Position", self.profile_data.get("looking_for_sexual_position"), inline=True)
        
        self._add_field(embed, "Distance Comfort", self.profile_data.get("distance_comfort"), inline=True)
        self._add_field(embed, "Max Distance", self.profile_data.get("max_distance"), inline=True)
        
        p_indep = self.profile_data.get("partner_independence_level")
        if p_indep and str(p_indep).lower() != "n/a":
            self._add_field(embed, "Partner Indep.", f"{p_indep}/10", inline=True)
        
        self._add_field(embed, "Willing to Relocate?", self.profile_data.get("willing_to_relocate"), inline=True)
        self._add_field(embed, "Partner Relocate?", self.profile_data.get("partner_relocate"), inline=True)
        
        # Build vices string
        vices_parts = []
        smoke = self.profile_data.get('smoking_ok')
        if smoke and str(smoke).lower() != "n/a": vices_parts.append(f"**Smoking:** {smoke}")
        
        drink = self.profile_data.get('drinking_ok')
        if drink and str(drink).lower() != "n/a": vices_parts.append(f"**Drinking:** {drink}")
        
        subs = self.profile_data.get('substance_ok')
        if subs and str(subs).lower() != "n/a": vices_parts.append(f"**Substances:** {subs}")

        if vices_parts:
            self._add_field(embed, "🍷 Vices Comfort", " | ".join(vices_parts), inline=False)
        
        self._add_field(embed, "🟩 Green Flags", self.profile_data.get("green_flags"), inline=False)
        self._add_field(embed, "🟥 Red Flags", self.profile_data.get("red_flags"), inline=False)
        self._add_field(embed, "❌ Dealbreakers", self.profile_data.get("dealbreakers"), inline=False)
        
        if not embed.fields:
            embed.description += "\n\n*No details have been filled out for this section yet.*"

        return embed

    def get_interests_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"⭐ {self.target_user.display_name}'s Interests",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        self._add_field(embed, "👍 Likes", self.profile_data.get("likes"), inline=True)
        self._add_field(embed, "👎 Dislikes", self.profile_data.get("dislikes"), inline=True)
        
        self._add_field(embed, "Hobbies / Interests", self.profile_data.get("hobbies_interests"), inline=False)
        self._add_field(embed, "🎮 Favorite Games", self.profile_data.get("favorite_games"), inline=False)
        
        self._add_field(embed, "🎬 Movie", self.profile_data.get("favorite_movie"), inline=True)
        self._add_field(embed, "🎌 Anime", self.profile_data.get("favorite_anime"), inline=True)
        self._add_field(embed, "🎵 Song", self.profile_data.get("favorite_song"), inline=True)
        
        self._add_field(embed, "🎤 Artist/Band", self.profile_data.get("favorite_artist_band"), inline=True)
        self._add_field(embed, "🍔 Food", self.profile_data.get("favorite_food"), inline=True)
        self._add_field(embed, "🍹 Drink", self.profile_data.get("favorite_drink"), inline=True)
        
        self._add_field(embed, "🎨 Color", self.profile_data.get("favorite_color"), inline=True)
        self._add_field(embed, "🐾 Animal", self.profile_data.get("favorite_animal"), inline=True)
        
        if not embed.fields:
            embed.description = "*No details have been filled out for this section yet.*"

        return embed

    def get_socials_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🌐 {self.target_user.display_name}'s Socials",
            color=discord.Color.teal()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        self._add_field(embed, "Twitter / X", self.profile_data.get("twitter"), inline=True)
        self._add_field(embed, "Instagram", self.profile_data.get("instagram"), inline=True)
        self._add_field(embed, "Telegram", self.profile_data.get("telegram"), inline=True)
        self._add_field(embed, "FurAffinity", self.profile_data.get("furaffinity"), inline=True)
        
        self._add_field(embed, "Steam", self.profile_data.get("steam"), inline=True)
        self._add_field(embed, "Nintendo Switch", self.profile_data.get("nintendo_switch"), inline=True)
        self._add_field(embed, "Xbox", self.profile_data.get("xbox"), inline=True)
        self._add_field(embed, "PlayStation", self.profile_data.get("playstation"), inline=True)
        
        if not embed.fields:
            embed.description = "*No details have been filled out for this section yet.*"

        return embed
        
    def get_fursonas_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🐾 {self.target_user.display_name}'s Fursonas",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        fursonas_list = self.profile_data.get("fursonas", [])
        
        for i, sona in enumerate(fursonas_list, 1):
            name = sona.get("name", f"Fursona {i}")
            desc = sona.get("description", "No description provided.")
            
            art_links = sona.get("art_links", [])
            if not art_links and "art_link" in sona and sona["art_link"].lower() != "n/a":
                art_links = [sona["art_link"]]
            
            if not art_links:
                art_val = "N/A"
            else:
                art_val = "\n".join([f"• [View Art {j+1}]({link})" if link.startswith("http") else f"• {link}" for j, link in enumerate(art_links)])
            
            embed.add_field(name=f"Fursona {i}: {name}", value=f"**Description:** {desc}\n**Art:**\n{art_val}", inline=False)
            
        return embed

    def get_my_likes_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"💚 People Who Liked You",
            description=f"You have **{self.total_likes}** total likes!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        has_nitro = any(role.id == self.NITRO_ROLE_ID for role in self.author.roles)
        sorted_likes = sorted(self.user_likes, key=lambda x: x['timestamp'], reverse=True)
        
        likes_str = ""
        for i, like in enumerate(sorted_likes[:15]): 
            dt_timestamp = int(like['timestamp'].timestamp())
            
            if i < 3 or has_nitro:
                likes_str += f"• <@{like['liker_id']}> — <t:{dt_timestamp}:R>\n"
            else:
                likes_str += f"• ||Hidden User|| — <t:{dt_timestamp}:R>\n"
                
        if len(self.user_likes) > 15:
            likes_str += f"\n*...and {len(self.user_likes) - 15} more!*"

        if not has_nitro and len(self.user_likes) > 3:
            likes_str += "\n\n🚀 *(Boost the server to reveal all hidden likes!)*"

        embed.add_field(name="Recent Likes", value=likes_str, inline=False)
        return embed

    # --- BUTTON CALLBACKS ---
    
    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def btn_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_self_view:
            self.update_view("my_likes")
            await interaction.response.edit_message(embed=self.get_my_likes_embed(), view=self)
            return
            
        has_liked = any(like["liker_id"] == interaction.user.id for like in self.user_likes)
        if has_liked:
            await self.likes_collection.update_one(
                {"_id": self.target_user.id},
                {"$pull": {"likes": {"liker_id": interaction.user.id}}}
            )
            self.user_likes = [l for l in self.user_likes if l["liker_id"] != interaction.user.id]
            self.total_likes -= 1
            
            self.refresh_action_buttons()
            await interaction.response.edit_message(view=self)
            return

        has_nitro = any(role.id == self.NITRO_ROLE_ID for role in interaction.user.roles)
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        
        is_re_like = interaction.user.id in self.historical_likers
        
        if not has_nitro and not is_re_like:
            user_activity = await self.activity_collection.find_one({"_id": interaction.user.id})
            if user_activity and user_activity.get("last_like_date") == today_str:
                likes_given = user_activity.get("likes_given_today", 0)
                if likes_given >= 3:
                    await interaction.response.send_message(
                        "⚠️ **You've hit your daily limit of 3 likes!**\n"
                        "Wait until tomorrow, or **boost the server** to bypass this restriction completely!",
                        ephemeral=True
                    )
                    return
                await self.activity_collection.update_one(
                    {"_id": interaction.user.id},
                    {"$inc": {"likes_given_today": 1}}
                )
            else:
                await self.activity_collection.update_one(
                    {"_id": interaction.user.id},
                    {"$set": {"last_like_date": today_str, "likes_given_today": 1}},
                    upsert=True
                )

        now = datetime.utcnow()
        await self.likes_collection.update_one(
            {"_id": self.target_user.id},
            {
                "$push": {"likes": {"liker_id": interaction.user.id, "timestamp": now}},
                "$addToSet": {"historical_likers": interaction.user.id} 
            },
            upsert=True
        )
        
        if not is_re_like:
            try:
                await self.target_user.send(f"💚 **{interaction.user.display_name}** ({interaction.user.mention}) likes your profile!")
            except discord.Forbidden:
                pass 
            self.historical_likers.append(interaction.user.id)
        
        self.user_likes.append({"liker_id": interaction.user.id, "timestamp": now})
        self.total_likes += 1
        
        self.refresh_action_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def btn_pass(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_self_view:
            return 
            
        has_passed = any((isinstance(p, dict) and p.get("user_id") == self.target_user.id) or p == self.target_user.id for p in self.user_passes)
        
        if has_passed:
            await self.passes_collection.update_one(
                {"_id": self.author.id},
                {"$pull": {"passed_users": {"user_id": self.target_user.id}}}
            )
            await self.passes_collection.update_one(
                {"_id": self.author.id},
                {"$pull": {"passed_users": self.target_user.id}}
            )
            self.user_passes = [p for p in self.user_passes if (isinstance(p, dict) and p.get("user_id") != self.target_user.id) and p != self.target_user.id]
        else:
            pass_entry = {"user_id": self.target_user.id, "timestamp": datetime.utcnow()}
            await self.passes_collection.update_one(
                {"_id": self.author.id},
                {"$push": {"passed_users": pass_entry}},
                upsert=True
            )
            self.user_passes.append(pass_entry)
            
        self.refresh_action_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Main Profile", style=discord.ButtonStyle.secondary, emoji="👤")
    async def btn_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_view("main")
        await interaction.response.edit_message(embed=self.get_main_embed(), view=self)

    @discord.ui.button(label="Looking For...", style=discord.ButtonStyle.primary, emoji="🔍")
    async def btn_looking(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_view("looking")
        await interaction.response.edit_message(embed=self.get_looking_for_embed(), view=self)

    @discord.ui.button(label="Likes/Interests", style=discord.ButtonStyle.primary, emoji="⭐")
    async def btn_interests(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_view("interests")
        await interaction.response.edit_message(embed=self.get_interests_embed(), view=self)

    @discord.ui.button(label="Socials", style=discord.ButtonStyle.primary, emoji="🌐")
    async def btn_socials(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_view("socials")
        await interaction.response.edit_message(embed=self.get_socials_embed(), view=self)
        
    @discord.ui.button(label="🐾 Fursonas", style=discord.ButtonStyle.primary)
    async def btn_fursonas(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_view("fursonas")
        await interaction.response.edit_message(embed=self.get_fursonas_embed(), view=self)

# ==========================================
# MAIN COG CLASS
# ==========================================
class DatingProfiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.collection = self.db["dating_profiles"]
        self.likes_collection = self.db["profile_likes"] 
        self.activity_collection = self.db["dating_activity"]
        self.passes_collection = self.db["profile_passes"]
        self.drafts = self.db["profile_drafts"] 
        
        self.profile_questions = [
            # Basics
            {"db_key": "name", "prompt": "**Name:**\nWhat is your Name or preferred nickname?"},
            {"db_key": "age", "prompt": "**Age:**\nHow old are you?"},
            {"db_key": "gender", "prompt": "**Gender:**\nWhat is your gender?"},
            {"db_key": "pronouns", "prompt": "**Pronouns:**\nWhat are your preferred pronouns?"},
            {"db_key": "location", "prompt": "**Location:**\nWhere are you located?"},
            {"db_key": "timezone", "prompt": "**Timezone:**\nWhat is your primary timezone? *(e.g., EST, GMT+1)*"},
            
            # Identity & Physical
            {"db_key": "relationship_status", "prompt": "**Dating Status:**\nWhat is your current relationship status?"},
            {"db_key": "sexuality", "prompt": "**Sexuality:**\nHow do you identify?"},
            {"db_key": "sexual_position", "prompt": "**Sexual Position:**\nWhat is your preferred role in intimacy?"},
            
            # Work & Bio
            {"db_key": "what_do_you_do_for_work_education", "prompt": "**Work / Education:**\nWhat do you do for a living or study?"},
            {"db_key": "fun_fact", "prompt": "**Fun Fact:**\nWhat is a fun or weird fact about yourself?"},
            {"db_key": "bio", "prompt": "**Bio:**\nTell us a bit about yourself! Please write a good few sentences and be descriptive."},
            
            # Dating Targets
            {"db_key": "is_looking", "prompt": "**Open to Dating?:**\nAre you currently looking for a relationship? *(Yes / No)*\n*(Answering 'No' will skip the remaining dating questions!)*"},
            {"db_key": "looking_for_min_age", "prompt": "**Looking For (Min Age):**\nWhat is the youngest age you are comfortable dating?"},
            {"db_key": "looking_for_max_age", "prompt": "**Looking For (Max Age):**\nWhat is the oldest age you are comfortable dating?"},
            {"db_key": "looking_for_gender", "prompt": "**Target Gender(s):**\nWhat gender(s) are you open to dating?"},
            {"db_key": "looking_for_relationship_type", "prompt": "**Relationship Type:**\nWhat kind of dynamic are you looking for?"},
            {"db_key": "looking_for_sexual_position", "prompt": "**Preferred Partner Sexual Position:**\nWhat is your preferred sexual position for a partner?"},
            
            # Distance & Independence Boundaries
            {"db_key": "distance_comfort", "prompt": "**Distance Comfort:**\nLocal only, or open to Long Distance (LDR)?"},
            {"db_key": "max_distance", "prompt": "**Max Distance:**\nWhat is the maximum distance you are willing to travel? *(e.g., 50 miles, 2 hours)*"},
            {"db_key": "partner_independence_level", "prompt": "**Partner Independence:**\nHow independent must your partner be on a scale from 1-10?"},
            {"db_key": "willing_to_relocate", "prompt": "**Willing to Relocate:**\nWould you be willing to relocate for a partner?"},
            {"db_key": "partner_relocate", "prompt": "**Partner Relocating:**\nDo you want a partner who is willing to relocate to you?"}
        ]
        
        self.dating_keys_to_skip = {
            "looking_for_min_age", "looking_for_max_age", "looking_for_gender", 
            "looking_for_relationship_type", "looking_for_sexual_position", "distance_comfort", 
            "max_distance", "partner_independence_level", "willing_to_relocate", "partner_relocate"
        }

    @app_commands.command(name="startprofile", description="Set up your dating profile in DMs.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def startprofile(self, interaction: discord.Interaction):
        if await self.collection.find_one({"_id": interaction.user.id}):
            await interaction.response.send_message(
                "⚠️ **You already have a profile created!**\nPlease use `/editprofile` to make changes or updates instead.", 
                ephemeral=True
            )
            return

        if await self.drafts.find_one({"_id": interaction.user.id}):
            await interaction.response.send_message(
                "⚠️ You already have a profile setup in progress in your DMs! Please go finish or `cancel` it.", 
                ephemeral=True
            )
            return

        draft_data = {
            "_id": interaction.user.id,
            "phase": "questions",
            "step": 0,
            "answers": {},
            "skip_dating_questions": False,
            "fursonas": [],
            "total_sonas": 0,
            "current_sona_index": 0,
            "current_sona_name": "",
            "current_sona_desc": "",
            "current_sona_art": []
        }
        await self.drafts.insert_one(draft_data)

        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(
                "## 💝 Welcome to Profile Setup\n"
                "Let's get your dating profile ready! Answer each question below."
            )
            
            first_q = self.profile_questions[0]
            await dm_channel.send(
                f"**[Question 1/{len(self.profile_questions)}]**\n"
                f"{first_q['prompt']}\n\n"
                f"*Type `skip` to skip to the next question, or `cancel` to stop.*"
            )
            await interaction.response.send_message("I'm sending you a DM to set up your profile! Make sure your DMs are open.", ephemeral=True)
        except discord.Forbidden:
            await self.drafts.delete_one({"_id": interaction.user.id})
            await interaction.response.send_message("I couldn't send you a DM. Please enable DMs from server members.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return

        draft = await self.drafts.find_one({"_id": message.author.id})
        if not draft:
            return 

        content = message.content.strip().replace("’", "'").replace("`", "'")
        if content.lower() == "dont know":
            content = "Don't Know"
        
        content_lower = content.lower()

        if content_lower == 'cancel':
            await self.drafts.delete_one({"_id": message.author.id})
            await message.channel.send("❌ Profile setup cancelled. No data was saved.")
            return

        phase = draft.get("phase")

        if phase == "questions":
            current_step = draft["step"]
            current_q = self.profile_questions[current_step]
            db_key = current_q["db_key"]

            if not content:
                await message.channel.send("⚠️ You cannot submit an empty answer.")
                return
            if db_key == "bio" and len(content) > 1000:
                await message.channel.send("⚠️ Your bio is too long! Please keep it under 1000 characters.")
                return
            if db_key != "bio" and len(content) > 300:
                await message.channel.send("⚠️ Your answer is too long! Please keep it under 300 characters.")
                return
            if re.search(r"([a-zA-Z])\1{9,}", content):
                await message.channel.send("⚠️ Your response looks like keyboard mashing. Please enter a valid answer.")
                return

            if content_lower != 'skip':
                draft["answers"][db_key] = content
            
            if db_key == "is_looking" and content_lower in ["no", "n", "nope"]:
                draft["skip_dating_questions"] = True

            next_step = current_step + 1
            while next_step < len(self.profile_questions):
                next_q = self.profile_questions[next_step]
                if draft.get("skip_dating_questions") and next_q["db_key"] in self.dating_keys_to_skip:
                    next_step += 1
                else:
                    break

            if next_step < len(self.profile_questions):
                draft["step"] = next_step
                await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
                next_q = self.profile_questions[next_step]
                await message.channel.send(
                    f"**[Question {next_step + 1}/{len(self.profile_questions)}]**\n"
                    f"{next_q['prompt']}\n\n*Type `skip` or `cancel`.*"
                )
            else:
                draft["phase"] = "fursona_init"
                await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
                await message.channel.send(
                    "**[Final Section: Fursonas]** 🐾\n"
                    "Do you have a fursona? *(Yes / No)*"
                )

        elif phase == "fursona_init":
            if content_lower in ['yes', 'y', 'yeah']:
                draft["phase"] = "fursona_count"
                await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
                await message.channel.send("Awesome! How many fursonas do you want to add to your profile? *(Enter a number up to 5)*")
            else:
                await self._finalize_profile(message.author, draft)

        elif phase == "fursona_count":
            if not content.isdigit() or int(content) < 1:
                await message.channel.send("⚠️ Please enter a valid number.")
                return
            if int(content) > 5:
                await message.channel.send("⚠️ Please limit it to a maximum of 5 fursonas. How many?")
                return
                
            draft["total_sonas"] = int(content)
            draft["current_sona_index"] = 0
            draft["phase"] = "fursona_name"
            await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
            
            await message.channel.send(f"**Fursona 1 of {draft['total_sonas']}** 🐾\nWhat is their Name?")

        elif phase == "fursona_name":
            draft["current_sona_name"] = content[:100]
            draft["phase"] = "fursona_desc"
            await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
            await message.channel.send(f"Give a brief description of **{draft['current_sona_name']}**:")

        elif phase == "fursona_desc":
            draft["current_sona_desc"] = content[:300]
            draft["current_sona_art"] = []
            draft["phase"] = "fursona_art"
            await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
            await message.channel.send(
                f"Do you have art for **{draft['current_sona_name']}**? Paste the URL (or type 'N/A' if none).\n"
                f"**You can add multiple links!** Type `done` when you are finished adding art."
            )

        elif phase == "fursona_art":
            if content_lower in ['done', 'n/a', 'none', 'skip', 'stop']:
                draft["fursonas"].append({
                    "name": draft["current_sona_name"],
                    "description": draft["current_sona_desc"],
                    "art_links": draft["current_sona_art"]
                })
                draft["current_sona_index"] += 1
                
                if draft["current_sona_index"] < draft["total_sonas"]:
                    draft["current_sona_name"] = ""
                    draft["current_sona_desc"] = ""
                    draft["current_sona_art"] = []
                    draft["phase"] = "fursona_name"
                    await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
                    await message.channel.send(
                        f"Got it! Let's do the next one.\n\n"
                        f"**Fursona {draft['current_sona_index'] + 1} of {draft['total_sonas']}** 🐾\nWhat is their Name?"
                    )
                else:
                    await self._finalize_profile(message.author, draft)
            else:
                if len(draft["current_sona_art"]) >= 10:
                    await message.channel.send("⚠️ You have reached the maximum of 10 art links for this fursona. Type `done` to finish.")
                else:
                    draft["current_sona_art"].append(content[:200])
                    await self.drafts.update_one({"_id": message.author.id}, {"$set": draft})
                    await message.channel.send("✅ Art added! Send another link, or type `done` to move on.")

    async def _finalize_profile(self, user: discord.Member, draft: dict):
        final_data = draft["answers"]
        
        if draft.get("fursonas"):
            final_data["fursonas"] = draft["fursonas"]
            
        final_data["profile_weight"] = 1
        
        await self.collection.update_one(
            {"_id": user.id}, 
            {"$set": final_data}, 
            upsert=True
        )
        
        await self.drafts.delete_one({"_id": user.id}) 
        
        self.bot.dispatch("new_profile", user, final_data)
        
        dm_channel = await user.create_dm()
        
        completion_msg = (
            "✅ **Your profile has been successfully saved!**\n"
            "Users can now use `/profile` in the server to view it.\n\n"
            "💡 **Tip:** There are a ton of other fields to fill out under `/editprofile`, "
            "such as likes/interests, green/red flags, and gaming tags to finish completing your profile!"
        )
        await dm_channel.send(completion_msg)

    @app_commands.command(name="editfursona", description="Manage your fursonas and art via DM.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def editfursona(self, interaction: discord.Interaction):
        current_data = await self.collection.find_one({"_id": interaction.user.id})
        if not current_data:
            await interaction.response.send_message("You don't have a profile yet! Use `/startprofile` first.", ephemeral=True)
            return

        await interaction.response.send_message(
            "I'm sending you a DM to manage your fursonas! Check your messages.", 
            ephemeral=True
        )

        try:
            dm_channel = await interaction.user.create_dm()
            def check(m): return m.author == interaction.user and m.channel == dm_channel

            fursonas = current_data.get("fursonas", [])

            while True:
                menu_text = (
                    "## 🐾 Fursona Manager\n"
                    "What would you like to do? *(Type the number)*\n"
                    "**1.** View current fursonas\n"
                    "**2.** Edit an existing fursona\n"
                    "**3.** Add a new fursona\n"
                    "**4.** Remove a fursona\n"
                    "**5.** ❌ Exit Manager"
                )
                await dm_channel.send(menu_text)
                
                try:
                    msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                    choice = msg.content.strip()
                except asyncio.TimeoutError:
                    await dm_channel.send("⏳ Manager timed out. Run `/editfursona` to open it again.")
                    return

                if choice == '1': 
                    if not fursonas:
                        await dm_channel.send("⚠️ You currently have no fursonas attached to your profile.")
                    else:
                        embed = discord.Embed(title="🐾 Your Current Fursonas", color=discord.Color.orange())
                        for i, sona in enumerate(fursonas, 1):
                            name = sona.get("name", f"Fursona {i}")
                            desc = sona.get("description", "No description provided.")
                            
                            art_links = sona.get("art_links", [])
                            if not art_links and "art_link" in sona and sona["art_link"].lower() != "n/a":
                                art_links = [sona["art_link"]]
                            
                            art_val = "N/A" if not art_links else "\n".join([f"• Link {j+1}: {link}" for j, link in enumerate(art_links)])
                            embed.add_field(name=f"{i}. {name}", value=f"**Description:** {desc}\n**Art:**\n{art_val}", inline=False)
                        
                        await dm_channel.send(embed=embed)

                elif choice == '2': 
                    if not fursonas:
                        await dm_channel.send("⚠️ You have no fursonas to edit. Try adding one first!")
                        continue
                    
                    sona_list = "\n".join([f"**{i+1}.** {s.get('name', f'Fursona {i+1}')}" for i, s in enumerate(fursonas)])
                    await dm_channel.send(f"Which fursona would you like to edit? *(Type the number or `cancel`)*\n{sona_list}")
                    
                    msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                    if msg.content.strip().lower() == 'cancel': continue
                    
                    if not msg.content.strip().isdigit() or not (1 <= int(msg.content.strip()) <= len(fursonas)):
                        await dm_channel.send("⚠️ Invalid selection.")
                        continue
                        
                    idx = int(msg.content.strip()) - 1
                    target_sona = fursonas[idx]
                    
                    if 'art_links' not in target_sona:
                        old_link = target_sona.get('art_link', 'N/A')
                        target_sona['art_links'] = [old_link] if old_link.lower() != 'n/a' else []
                    
                    while True:
                        edit_menu = (
                            f"Editing **{target_sona.get('name', f'Fursona {idx+1}')}**:\n"
                            "What would you like to change? *(Type the number)*\n"
                            "**1.** Update Name\n"
                            "**2.** Update Description\n"
                            "**3.** Add an Art Link\n"
                            "**4.** Remove an Art Link\n"
                            "**5.** ⬅️ Go Back"
                        )
                        await dm_channel.send(edit_menu)
                        msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                        edit_choice = msg.content.strip()
                        
                        if edit_choice == '1':
                            await dm_channel.send("What is the new name? (Or type `cancel`)")
                            new_name = await self.bot.wait_for('message', check=check, timeout=300.0)
                            if new_name.content.strip().lower() != 'cancel':
                                fursonas[idx]['name'] = new_name.content.strip()[:100]
                                await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                                await dm_channel.send("✅ Name updated!")
                                
                        elif edit_choice == '2':
                            await dm_channel.send("What is the new description? (Or type `cancel`)")
                            new_desc = await self.bot.wait_for('message', check=check, timeout=300.0)
                            if new_desc.content.strip().lower() != 'cancel':
                                fursonas[idx]['description'] = new_desc.content.strip()[:300]
                                await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                                await dm_channel.send("✅ Description updated!")
                                
                        elif edit_choice == '3':
                            if len(fursonas[idx]['art_links']) >= 10:
                                await dm_channel.send("⚠️ This fursona already has 10 art links. Please remove one first.")
                                continue
                            await dm_channel.send("Paste the new art URL: (Or type `cancel`)")
                            new_art = await self.bot.wait_for('message', check=check, timeout=300.0)
                            if new_art.content.strip().lower() != 'cancel':
                                fursonas[idx]['art_links'].append(new_art.content.strip()[:200])
                                await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                                await dm_channel.send("✅ Art link added!")
                                
                        elif edit_choice == '4':
                            art_links = fursonas[idx].get('art_links', [])
                            if not art_links:
                                await dm_channel.send("⚠️ There are no art links to remove.")
                                continue
                            link_list = "\n".join([f"**{i+1}.** {link}" for i, link in enumerate(art_links)])
                            await dm_channel.send(f"Which link would you like to remove? *(Type the number or `cancel`)*\n{link_list}")
                            rm_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                            if rm_msg.content.strip().lower() == 'cancel': continue
                            if not rm_msg.content.strip().isdigit() or not (1 <= int(rm_msg.content.strip()) <= len(art_links)):
                                await dm_channel.send("⚠️ Invalid selection.")
                                continue
                            del fursonas[idx]['art_links'][int(rm_msg.content.strip()) - 1]
                            await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                            await dm_channel.send("✅ Art link removed!")
                            
                        elif edit_choice == '5':
                            break
                        else:
                            await dm_channel.send("⚠️ Invalid choice. Please select 1-5.")

                elif choice == '3': 
                    if len(fursonas) >= 8:
                        await dm_channel.send("⚠️ You already have the maximum of 8 fursonas. Please remove one first.")
                        continue
                        
                    await dm_channel.send("What is their Name? (Or type `cancel`)")
                    name_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                    if name_msg.content.strip().lower() == 'cancel': continue
                    
                    await dm_channel.send(f"Give a brief description of {name_msg.content}:")
                    desc_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                    
                    await dm_channel.send(f"Do you have art for {name_msg.content}? Paste the URL (or type 'N/A' if none). **You can add multiple links!** Type `done` when you are finished adding art.")
                    art_links = []
                    while True:
                        art_msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                        art_content = art_msg.content.strip()
                        if art_content.lower() in ['done', 'n/a', 'none', 'skip', 'stop']:
                            break
                        art_links.append(art_content[:200])
                        await dm_channel.send(f"✅ Art added! Send another link, or type `done` to finish.")
                        
                    fursonas.append({
                        "name": name_msg.content.strip()[:100],
                        "description": desc_msg.content.strip()[:300],
                        "art_links": art_links[:10]
                    })
                    
                    await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                    await dm_channel.send("✅ **New fursona successfully added to your profile!**")

                elif choice == '4': 
                    if not fursonas:
                        await dm_channel.send("⚠️ You have no fursonas to remove.")
                        continue
                        
                    sona_list = "\n".join([f"**{i+1}.** {s.get('name', f'Fursona {i+1}')}" for i, s in enumerate(fursonas)])
                    await dm_channel.send(f"Which fursona would you like to completely remove? *(Type the number or `cancel`)*\n{sona_list}")
                    
                    msg = await self.bot.wait_for('message', check=check, timeout=300.0)
                    if msg.content.strip().lower() == 'cancel': continue
                    
                    if not msg.content.strip().isdigit() or not (1 <= int(msg.content.strip()) <= len(fursonas)):
                        await dm_channel.send("⚠️ Invalid selection.")
                        continue
                        
                    idx = int(msg.content.strip()) - 1
                    removed_name = fursonas[idx].get("name", "Fursona")
                    del fursonas[idx]
                    
                    await self.collection.update_one({"_id": interaction.user.id}, {"$set": {"fursonas": fursonas}})
                    await dm_channel.send(f"🗑️ **{removed_name}** has been removed from your profile.")

                elif choice == '5': 
                    await dm_channel.send("Exited Fursona Manager. Changes are saved and your profile is up to date!")
                    break
                else:
                    await dm_channel.send("⚠️ Invalid choice. Please type 1, 2, 3, 4, or 5.")

        except discord.Forbidden:
            pass 

    @app_commands.command(name="profile", description="View a user's dating profile.")
    @app_commands.describe(user="The user whose profile you want to view")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def profile(self, interaction: discord.Interaction, user: discord.Member):
        profile_data = await self.collection.find_one({"_id": user.id})
        
        if not profile_data:
            await interaction.response.send_message(
                f"{user.mention} hasn't set up a profile yet! They can use `/startprofile` to make one, "
                f"or check out their intro in <#1496743217390157935>.", 
                ephemeral=True
            )
            return

        likes_data = await self.likes_collection.find_one({"_id": user.id})
        user_likes = likes_data.get("likes", []) if likes_data else []
        historical_likers = likes_data.get("historical_likers", []) if likes_data else []
        total_likes = len(user_likes)

        passes_data = await self.passes_collection.find_one({"_id": interaction.user.id})
        user_passes = passes_data.get("passed_users", []) if passes_data else []

        view = ProfilePaginator(
            target_user=user, 
            profile_data=profile_data, 
            author=interaction.user,
            likes_collection=self.likes_collection,
            activity_collection=self.activity_collection,
            passes_collection=self.passes_collection,
            total_likes=total_likes,
            user_likes=user_likes,
            historical_likers=historical_likers,
            user_passes=user_passes
        )
        
        await interaction.response.send_message(embed=view.get_main_embed(), view=view)

    @app_commands.command(name="editprofile", description="Edit specific sections of your dating profile.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def editprofile(self, interaction: discord.Interaction):
        current_data = await self.collection.find_one({"_id": interaction.user.id})
        
        if not current_data:
            await interaction.response.send_message(
                "You don't have a profile to edit yet! Use `/startprofile` to create one first.", 
                ephemeral=True
            )
            return

        view = ProfileEditView(current_data, self.collection)
        await interaction.response.send_message(
            "Select which part of your profile you'd like to update:", 
            view=view, 
            ephemeral=True
        )

    @app_commands.command(name="deleteprofile", description="Completely remove your dating profile and data.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def deleteprofile(self, interaction: discord.Interaction):
        current_data = await self.collection.find_one({"_id": interaction.user.id})
        
        if not current_data:
            await interaction.response.send_message("You don't have a profile to delete.", ephemeral=True)
            return

        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message("⚠️ Are you sure you want to completely delete your profile? This cannot be undone.", view=view, ephemeral=True)
        
        await view.wait()
        
        if view.value is None:
            await interaction.edit_original_response(content="⏳ Deletion timed out.", view=None)
            return
        elif view.value:
            await self.collection.delete_one({"_id": interaction.user.id})
            await self.likes_collection.delete_one({"_id": interaction.user.id})
            await self.drafts.delete_one({"_id": interaction.user.id})
            await interaction.edit_original_response(content="✅ Your profile and associated data have been permanently deleted.", view=None)
        else:
            await interaction.edit_original_response(content="❌ Profile deletion cancelled.", view=None)

    @app_commands.command(name="resetprofile", description="Delete your profile and start the creation process over.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def resetprofile(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message("⚠️ Are you sure you want to reset your profile? All existing data and likes will be wiped, and you will be sent a DM to start over.", view=view, ephemeral=True)
        
        await view.wait()
        
        if view.value is None:
            await interaction.edit_original_response(content="⏳ Reset timed out.", view=None)
            return
        elif view.value:
            await self.collection.delete_one({"_id": interaction.user.id})
            await self.likes_collection.delete_one({"_id": interaction.user.id})
            await self.drafts.delete_one({"_id": interaction.user.id})
            
            await interaction.edit_original_response(content="✅ Profile reset! Check your DMs to start the setup process again.", view=None)
            
            # Re-trigger startprofile
            await self.startprofile.callback(self, interaction)
        else:
            await interaction.edit_original_response(content="❌ Profile reset cancelled.", view=None)

async def setup(bot):
    await bot.add_cog(DatingProfiles(bot))
    
    db = get_connection()
    collection = db["dating_profiles"]
    
    await collection.update_many(
        {"profile_weight": {"$exists": False}}, 
        {"$set": {"profile_weight": 1}}
    )