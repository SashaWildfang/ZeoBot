import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.database import get_connection

# ==========================================
# UI CLASS FOR TABBED NAVIGATION & LIKES
# (Copied here so this file works standalone)
# ==========================================

class ProfilePaginator(discord.ui.View):
    def __init__(self, target_user: discord.Member, profile_data: dict, author: discord.Member, likes_collection, activity_collection, total_likes: int, user_likes: list, historical_likers: list):
        super().__init__(timeout=900)
        self.target_user = target_user
        self.profile_data = profile_data
        self.author = author
        self.likes_collection = likes_collection
        self.activity_collection = activity_collection
        self.total_likes = total_likes
        self.user_likes = user_likes
        self.historical_likers = historical_likers
        self.NITRO_ROLE_ID = 1360260086500561237
        
        self.is_self_view = (self.target_user.id == self.author.id)
        
        self.btn_action_item = self.children[0]
        self.btn_main_item = self.children[1]
        self.btn_looking_item = self.children[2]
        self.btn_interests_item = self.children[3]
        self.btn_socials_item = self.children[4]
        self.btn_fursonas_item = self.children[5]
        
        self.refresh_action_button()
        self.update_view("main")

    def refresh_action_button(self):
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("You cannot interact with this menu. Run the command yourself!", ephemeral=True)
            return False
        return True

    def update_view(self, active_page: str):
        self.clear_items()
        
        if active_page != "my_likes": self.add_item(self.btn_action_item)
        if active_page != "main": self.add_item(self.btn_main_item)
        if active_page != "looking": self.add_item(self.btn_looking_item)
        if active_page != "interests": self.add_item(self.btn_interests_item)
        if active_page != "socials": self.add_item(self.btn_socials_item)
        
        fursonas_list = self.profile_data.get("fursonas", [])
        if fursonas_list and active_page != "fursonas":
            self.btn_fursonas_item.label = "🐾 Fursonas" if len(fursonas_list) > 1 else "🐾 Fursona"
            self.add_item(self.btn_fursonas_item)

    def get_main_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"👤 {self.target_user.display_name}'s Profile", color=discord.Color.blurple())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        embed.add_field(name="Name", value=self.profile_data.get("name", "N/A"), inline=True)
        embed.add_field(name="Age", value=self.profile_data.get("age", "N/A"), inline=True)
        embed.add_field(name="Gender", value=self.profile_data.get("gender", "N/A"), inline=True)
        embed.add_field(name="Pronouns", value=self.profile_data.get("pronouns", "N/A"), inline=True)
        embed.add_field(name="Location", value=self.profile_data.get("location", "N/A"), inline=True)
        embed.add_field(name="Timezone", value=self.profile_data.get("timezone", "N/A"), inline=True)
        embed.add_field(name="Status", value=self.profile_data.get("relationship_status", "N/A"), inline=True)
        embed.add_field(name="Sexuality", value=self.profile_data.get("sexuality", "N/A"), inline=True)
        embed.add_field(name="Sexual Position", value=self.profile_data.get("sexual_position", "N/A"), inline=True)
        embed.add_field(name="Body Type", value=self.profile_data.get("body_type", "N/A"), inline=True)
        embed.add_field(name="Height", value=self.profile_data.get("height", "N/A"), inline=True)
        embed.add_field(name="Weight", value=self.profile_data.get("weight", "N/A"), inline=True)
        embed.add_field(name="Work / Education", value=self.profile_data.get("what_do_you_do_for_work_education", "N/A"), inline=True)
        
        lifestyle_str = (
            f"**Sleep:** {self.profile_data.get('sleep_schedule', 'N/A')} | "
            f"**Activity:** {self.profile_data.get('activity_level', 'N/A')}\n"
            f"**Kids:** {self.profile_data.get('want_kids', 'N/A')} | "
            f"**Marriage:** {self.profile_data.get('marriage_goals', 'N/A')}\n"
            f"**Religion Important?:** {self.profile_data.get('religion_important', 'N/A')}"
        )
        embed.add_field(name="🏡 Lifestyle & Values", value=lifestyle_str, inline=False)
        
        fursonas_list = self.profile_data.get("fursonas", [])
        if not fursonas_list:
            embed.add_field(name="🐾 Fursonas", value="No Fursona", inline=False)
        else:
            embed.add_field(name="🐾 Fursonas", value=f"Has {len(fursonas_list)} Fursona(s) — Check the button below!", inline=False)
        
        embed.add_field(name="✨ Fun Fact", value=self.profile_data.get("fun_fact", "N/A"), inline=False)
        embed.add_field(name="📖 Bio", value=self.profile_data.get("bio", "N/A"), inline=False)
        
        if self.is_self_view:
            embed.add_field(name="💚 Your Total Likes", value=f"**{self.total_likes}**", inline=False)
        return embed

    def get_looking_for_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🔍 What {self.target_user.display_name} is Looking For", color=discord.Color.brand_red())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        is_looking = self.profile_data.get("is_looking", "N/A").strip().lower()
        if is_looking in ["no", "n", "nope"]:
            embed.description = "🚫 **This user is not currently looking for a relationship.**\nThey are likely here for friends, gaming, or community!"
            return embed
        embed.add_field(name="Target Age Range", value=f"**{self.profile_data.get('looking_for_min_age', '?')} - {self.profile_data.get('looking_for_max_age', '?')}**", inline=True)
        embed.add_field(name="Target Gender(s)", value=self.profile_data.get("looking_for_gender", "N/A"), inline=True)
        embed.add_field(name="Relationship Type", value=self.profile_data.get("looking_for_relationship_type", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Distance Comfort", value=self.profile_data.get("distance_comfort", "N/A"), inline=True)
        embed.add_field(name="Max Distance", value=self.profile_data.get("max_distance", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Willing to Relocate?", value=self.profile_data.get("willing_to_relocate", "N/A"), inline=True)
        embed.add_field(name="Partner Relocate?", value=self.profile_data.get("partner_relocate", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        vices_str = (
            f"**Smoking:** {self.profile_data.get('smoking_ok', 'N/A')} | "
            f"**Drinking:** {self.profile_data.get('drinking_ok', 'N/A')}\n"
            f"**Substances:** {self.profile_data.get('substance_ok', 'N/A')}"
        )
        embed.add_field(name="🍷 Vices Comfort", value=vices_str, inline=False)
        embed.add_field(name="🟩 Green Flags", value=self.profile_data.get("green_flags", "N/A"), inline=False)
        embed.add_field(name="🟥 Red Flags", value=self.profile_data.get("red_flags", "N/A"), inline=False)
        embed.add_field(name="❌ Dealbreakers", value=self.profile_data.get("dealbreakers", "N/A"), inline=False)
        return embed

    def get_interests_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"⭐ {self.target_user.display_name}'s Interests", color=discord.Color.gold())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        embed.add_field(name="👍 Likes", value=self.profile_data.get("likes", "N/A"), inline=True)
        embed.add_field(name="👎 Dislikes", value=self.profile_data.get("dislikes", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False) 
        embed.add_field(name="Hobbies / Interests", value=self.profile_data.get("hobbies_interests", "N/A"), inline=False)
        embed.add_field(name="🎮 Favorite Games", value=self.profile_data.get("favorite_games", "N/A"), inline=False)
        embed.add_field(name="🎬 Movie", value=self.profile_data.get("favorite_movie", "N/A"), inline=True)
        embed.add_field(name="🎌 Anime", value=self.profile_data.get("favorite_anime", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="🎵 Song", value=self.profile_data.get("favorite_song", "N/A"), inline=True)
        embed.add_field(name="🎤 Artist/Band", value=self.profile_data.get("favorite_artist_band", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="🍔 Food", value=self.profile_data.get("favorite_food", "N/A"), inline=True)
        embed.add_field(name="🍹 Drink", value=self.profile_data.get("favorite_drink", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="🎨 Color", value=self.profile_data.get("favorite_color", "N/A"), inline=True)
        embed.add_field(name="🐾 Animal", value=self.profile_data.get("favorite_animal", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        return embed

    def get_socials_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🌐 {self.target_user.display_name}'s Socials", color=discord.Color.teal())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        embed.add_field(name="Twitter / X", value=self.profile_data.get("twitter", "N/A"), inline=True)
        embed.add_field(name="Instagram", value=self.profile_data.get("instagram", "N/A"), inline=True)
        embed.add_field(name="Telegram", value=self.profile_data.get("telegram", "N/A"), inline=True)
        embed.add_field(name="FurAffinity", value=self.profile_data.get("furaffinity", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="🎮 Gaming Tags", value="\u200b", inline=False)
        embed.add_field(name="Steam", value=self.profile_data.get("steam", "N/A"), inline=True)
        embed.add_field(name="Nintendo Switch", value=self.profile_data.get("nintendo_switch", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        return embed
        
    def get_fursonas_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🐾 {self.target_user.display_name}'s Fursonas", color=discord.Color.orange())
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
        embed = discord.Embed(title=f"💚 People Who Liked You", description=f"You have **{self.total_likes}** total likes!", color=discord.Color.green())
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
            self.refresh_action_button()
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
                await self.activity_collection.update_one({"_id": interaction.user.id}, {"$inc": {"likes_given_today": 1}})
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
        self.refresh_action_button()
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
# RANDOM PROFILE COG
# ==========================================

class RandomProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.collection = self.db["dating_profiles"]
        self.likes_collection = self.db["profile_likes"] 
        self.activity_collection = self.db["dating_activity"]

    def check_gender_clash(self, user_gender: str, user_looking_for: str, target_gender: str, target_looking_for: str) -> bool:
        """Returns True if the genders are INCOMPATIBLE (clash). Returns False if they MATCH."""
        u_gen = user_gender.lower().strip()
        t_gen = target_gender.lower().strip()
        
        # Parse comma-separated looking for lists
        u_looking = [g.strip() for g in user_looking_for.split(',') if g.strip()]
        t_looking = [g.strip() for g in target_looking_for.split(',') if g.strip()]
        
        # If any required field is missing, fail the strict check
        if not u_gen or not t_gen or not u_looking or not t_looking:
            return True
            
        # Does the user's gender exist in the target's preferences?
        if u_gen not in t_looking:
            return True
            
        # Does the target's gender exist in the user's preferences?
        if t_gen not in u_looking:
            return True
            
        return False

    @app_commands.command(name="randomprofile", description="Discover a random user's dating profile.")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def randomprofile(self, interaction: discord.Interaction):
        await interaction.response.defer() # Defer in case finding an active member takes a second

        # Fetch the user's profile to validate their gender preferences
        user_profile = await self.collection.find_one({"_id": interaction.user.id})
        
        if not user_profile:
            await interaction.followup.send("⚠️ You don't have a profile yet! Run `/startprofile` first.", ephemeral=True)
            return

        # Fetch missing gender inputs to prevent failure
        raw_user_gender = str(user_profile.get("gender", "")).strip()
        raw_user_looking_for = str(user_profile.get("looking_for_gender", "")).strip()

        # Check if the required gender fields exist
        if not raw_user_gender or raw_user_gender.lower() == "n/a" or not raw_user_looking_for or raw_user_looking_for.lower() == "n/a":
            await interaction.followup.send(
                "⚠️ Your profile is missing your **Gender** or **Target Gender(s)**!\n"
                "Please run `/editprofile`, select **'Identity'** to update your Gender, and **'Dating Targets'** to update your Target Genders so we can find you compatible random profiles.", 
                ephemeral=True
            )
            return

        user_gender = raw_user_gender.lower()
        user_looking_for_gender = raw_user_looking_for.lower()

        # Pull 100 random profiles to ensure we find at least one user who matches gender AND hasn't left the server
        pipeline = [{"$sample": {"size": 100}}]
        cursor = self.collection.aggregate(pipeline)
        docs = await cursor.to_list(length=100)

        if not docs:
            await interaction.followup.send("There are no profiles in the database yet!", ephemeral=True)
            return

        target_user = None
        profile_data = None

        # Loop through the random selection until we find a match
        for doc in docs:
            # Don't show the user their own profile in random matching
            if doc["_id"] == interaction.user.id:
                continue
                
            member = interaction.guild.get_member(doc["_id"])
            if not member:
                continue

            target_gender = str(doc.get("gender", "")).lower().strip()
            target_looking_for_gender = str(doc.get("looking_for_gender", "")).lower()

            # Ensure both profiles pass the mutual gender compatibility check
            if self.check_gender_clash(user_gender, user_looking_for_gender, target_gender, target_looking_for_gender):
                continue

            target_user = member
            profile_data = doc
            break

        if not target_user:
            await interaction.followup.send("Could not find any active random profiles that match your exact Gender requirements at this time. Try again later!", ephemeral=True)
            return

        # Fetch their likes data for the Paginator
        likes_data = await self.likes_collection.find_one({"_id": target_user.id})
        user_likes = likes_data.get("likes", []) if likes_data else []
        historical_likers = likes_data.get("historical_likers", []) if likes_data else []
        total_likes = len(user_likes)

        # Generate the View
        view = ProfilePaginator(
            target_user=target_user, 
            profile_data=profile_data, 
            author=interaction.user,
            likes_collection=self.likes_collection,
            activity_collection=self.activity_collection,
            total_likes=total_likes,
            user_likes=user_likes,
            historical_likers=historical_likers
        )
        
        await interaction.followup.send(content="🎲 **You found a random profile!**", embed=view.get_main_embed(), view=view)


async def setup(bot):
    await bot.add_cog(RandomProfile(bot))