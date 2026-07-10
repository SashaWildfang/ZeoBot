import discord
from discord.ext import commands
from discord import app_commands
import re
from datetime import datetime
from db.database import get_connection
import json
import asyncio

# ==========================================
# CONFIGURE GEMINI AI (NEW SDK)
# ==========================================
# Make sure you have run: pip install google-genai
from google import genai
from google.genai import types

# Initialize the new client with your API key
client = genai.Client(api_key="AIzaSyAYbj3fBG52Fp8TKGVfhU0d4vopsxSWdko")

# ==========================================
# AI VIBE CHECKER
# ==========================================
async def get_ai_vibe_scores(main_user: dict, candidates: list) -> dict:
    """
    Sends the top candidates to the LLM to get a contextual Vibe Score and Reasoning.
    Returns a dictionary mapping candidate Discord IDs to their structured AI score and breakdown.
    """
    if not candidates:
        return {}

    # Strip down the data so we don't waste AI tokens on useless info
    # Notice we removed kids, marriage, sleep, and religion, and added independence.
    def clean_profile(p):
        return {
            "id": str(p["_id"]),
            "name": p.get("name", "This person"),
            "bio": p.get("bio", "N/A"),
            "fun_fact": p.get("fun_fact", "N/A"),
            "likes": p.get("likes", "N/A"),
            "dislikes": p.get("dislikes", "N/A"),
            "hobbies": p.get("hobbies_interests", "N/A"),
            "games": p.get("favorite_games", "N/A"),
            "green_flags": p.get("green_flags", "N/A"),
            "red_flags": p.get("red_flags", "N/A"),
            "independence_level": p.get("independence_level", "N/A"),
            "partner_independence_level": p.get("partner_independence_level", "N/A")
        }

    user_data = clean_profile(main_user)
    candidates_data = [clean_profile(c) for c in candidates]

    prompt = f"""
    You are an expert, friendly matchmaker for a Discord community. 
    I will provide the profile of a Main User, and a list of Candidate Profiles.
    
    Your job is to read their bios, favorites, red flags, and independence levels to assess their compatibility.
    
    CRITICAL TONE & FORMATTING RULES:
    1. BE PERSONAL: Talk directly to the Main User using "You" and "Your". 
    2. USE NAMES: Refer to the match by their actual `name`. NEVER use clinical words like "Candidate".
    3. BULLET POINTS: Format the `shared_interests` field as a neat bulleted list using newlines and dashes (e.g., "- Coding\\n- Gaming").
    4. HUMANIZED & SIMPLE: Make the `about` section sound conversational, warm, and natural. Do not overcomplicate it. Focus heavily on shared interests and whether their independence levels match.
    
    MAIN USER:
    {json.dumps(user_data, indent=2)}
    
    CANDIDATES:
    {json.dumps(candidates_data, indent=2)}
    
    Score each candidate from 1 to 100.
    1-30: Clashing vibes or totally opposite personalities.
    31-60: Neutral.
    61-85: Solid shared vibes, perfectly matched independence, and interests.
    86-100: Soulmate level. Niche shared interests, perfectly aligned boundaries.
    
    Respond ONLY with a valid JSON array of objects. Do NOT use markdown formatting like ```json. 
    Format exactly like this example:
    [
      {{
        "id": "123456789", 
        "score": 85, 
        "shared_interests": "- Stardew Valley\\n- Anime",
        "about": "Church matches your vibe perfectly! They are just as independent as you are, and you both share a love for cozy nights in playing video games. They seem like a really genuine and fun person to be around.",
        "differences": "They are a bit more outdoorsy than you."
      }}
    ]
    """

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=1.0,
                response_mime_type="application/json",
                safety_settings=[
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                ]
            )
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        ai_results = json.loads(raw_text)
        
        final_scores = {}
        for item in ai_results:
            final_scores[int(item["id"])] = {
                "score": item.get("score", 50),
                "shared_interests": item.get("shared_interests", "None clearly identified."),
                "about": item.get("about", "Neutral vibe."),
                "differences": item.get("differences", "None clearly identified.")
            }
            
        return final_scores
        
    except Exception as e:
        # Check for 503 specifically to log it clearly
        if "503" in str(e):
            print("⚠️ AI Matchmaker Failed: Model currently unavailable (503).")
        else:
            print(f"❌ AI Matchmaker Failed: {e}")
        return {}


# ==========================================
# FULL PROFILE PAGINATOR
# ==========================================
# ==========================================
# FULL PROFILE PAGINATOR
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
            await interaction.response.send_message("You cannot interact with this menu.", ephemeral=True)
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
        embed = discord.Embed(title=f"👤 {self.target_user.display_name}'s Profile", description=f"**Discord:** {self.target_user.mention}", color=discord.Color.blurple())
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
            f"**Sleep:** {self.profile_data.get('sleep_schedule', 'N/A')} | **Activity:** {self.profile_data.get('activity_level', 'N/A')}\n"
            f"**Kids:** {self.profile_data.get('want_kids', 'N/A')} | **Marriage:** {self.profile_data.get('marriage_goals', 'N/A')}\n"
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
        return embed

    def get_looking_for_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🔍 What {self.target_user.display_name} is Looking For", color=discord.Color.brand_red())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        is_looking = self.profile_data.get("is_looking", "N/A").strip().lower()
        if is_looking in ["no", "n", "nope"]:
            embed.description = "🚫 **This user is not currently looking for a relationship.**"
            return embed
        embed.add_field(name="Target Age Range", value=f"**{self.profile_data.get('looking_for_min_age', '?')} - {self.profile_data.get('looking_for_max_age', '?')}**", inline=True)
        embed.add_field(name="Target Gender(s)", value=self.profile_data.get("looking_for_gender", "N/A"), inline=True)
        embed.add_field(name="Relationship Type", value=self.profile_data.get("looking_for_relationship_type", "N/A"), inline=True)
        embed.add_field(name="Distance Comfort", value=self.profile_data.get("distance_comfort", "N/A"), inline=True)
        embed.add_field(name="Max Distance", value=self.profile_data.get("max_distance", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Willing to Relocate?", value=self.profile_data.get("willing_to_relocate", "N/A"), inline=True)
        embed.add_field(name="Partner Relocate?", value=self.profile_data.get("partner_relocate", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        vices_str = f"**Smoking:** {self.profile_data.get('smoking_ok', 'N/A')} | **Drinking:** {self.profile_data.get('drinking_ok', 'N/A')}\n**Substances:** {self.profile_data.get('substance_ok', 'N/A')}"
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
            art_val = "N/A" if not art_links else "\n".join([f"• [View Art {j+1}]({link})" if link.startswith("http") else f"• {link}" for j, link in enumerate(art_links)])
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
            await self.likes_collection.update_one({"_id": self.target_user.id}, {"$pull": {"likes": {"liker_id": interaction.user.id}}})
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
                        "⚠️ **You've hit your daily limit of 3 likes!**\nWait until tomorrow, or **boost the server** to bypass this restriction completely!",
                        ephemeral=True
                    )
                    return
                await self.activity_collection.update_one({"_id": interaction.user.id}, {"$inc": {"likes_given_today": 1}})
            else:
                await self.activity_collection.update_one({"_id": interaction.user.id}, {"$set": {"last_like_date": today_str, "likes_given_today": 1}}, upsert=True)

        now = datetime.utcnow()
        await self.likes_collection.update_one({"_id": self.target_user.id}, {"$push": {"likes": {"liker_id": interaction.user.id, "timestamp": now}}, "$addToSet": {"historical_likers": interaction.user.id}}, upsert=True)
        
        if not is_re_like:
            try: await self.target_user.send(f"💚 **{interaction.user.display_name}** ({interaction.user.mention}) likes your profile!")
            except discord.Forbidden: pass 
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
# AI MATCH RESULTS UI
# ==========================================
class MatchPaginator(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, matches: list, db, user_passes: list):
        super().__init__(timeout=600)
        self.interaction = interaction
        self.matches = matches
        self.index = 0
        self.db = db
        self.likes_collection = db["profile_likes"]
        self.activity_collection = db["dating_activity"]
        self.passes_collection = db["profile_passes"]
        self.user_passes = user_passes
        
        self.update_buttons()

    def get_match_embed(self) -> discord.Embed:
        match_info = self.matches[self.index]
        member = match_info["member"]
        doc = match_info["doc"]
        score = match_info["score"]
        
        if score >= 85: color = discord.Color.brand_green()
        elif score >= 70: color = discord.Color.gold()
        else: color = discord.Color.orange()

        embed = discord.Embed(
            title=f"💘 {score}% Vibe Match!",
            description=f"You matched with {member.mention}!",
            color=color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name="🎮 Shared Interests", value=match_info['shared_interests'], inline=True)
        
        # Spacer for visual cleanlyness 
        embed.add_field(name="\u200b", value="\u200b", inline=True) 
        
        name = doc.get('name', member.display_name)
        embed.add_field(name=f"✨ About {name}", value=match_info['about'], inline=False)
        
        if match_info['differences'] and str(match_info['differences']).lower() not in ["none", "n/a", "none clearly identified.", "none clearly identified"]:
            embed.add_field(name="⚠️ Potential Clashes", value=match_info['differences'], inline=False)

        # Basic Stats
        embed.add_field(name="Name", value=doc.get("name", member.display_name), inline=True)
        embed.add_field(name="Age", value=doc.get("age", "N/A"), inline=True)
        embed.add_field(name="Gender", value=doc.get("gender", "N/A"), inline=True)
        
        embed.add_field(name="Location", value=doc.get("location", "N/A"), inline=True)
        embed.add_field(name="Sexuality", value=doc.get("sexuality", "N/A"), inline=True)
        embed.add_field(name="Rel. Type", value=doc.get("looking_for_relationship_type", "N/A"), inline=True)
        
        embed.set_footer(text="Click 'View Full Profile' below to read their bio and see everything!")
        return embed

    def update_buttons(self):
        # Index 0: Prev, 1: Status, 2: Next, 3: Pass, 4: View Full
        self.children[0].disabled = (self.index == 0)
        self.children[2].disabled = (self.index == len(self.matches) - 1)
        self.children[1].label = f"Match {self.index + 1} of {len(self.matches)}"
        
        target_id = self.matches[self.index]["member"].id
        has_passed = any((isinstance(p, dict) and p.get("user_id") == target_id) or p == target_id for p in self.user_passes)
        
        if has_passed:
            self.children[3].label = "Undo Not Interested"
            self.children[3].style = discord.ButtonStyle.danger
        else:
            self.children[3].label = "Not Interested"
            self.children[3].style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("This isn't your match list! Run `/findmatch` to find your own.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_match_embed(), view=self)

    @discord.ui.button(label="1 of X", style=discord.ButtonStyle.secondary, disabled=True)
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_match_embed(), view=self)

    @discord.ui.button(label="Not Interested", style=discord.ButtonStyle.secondary)
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        target_id = self.matches[self.index]["member"].id
        has_passed = any((isinstance(p, dict) and p.get("user_id") == target_id) or p == target_id for p in self.user_passes)
        
        if has_passed:
            await self.passes_collection.update_one(
                {"_id": self.interaction.user.id},
                {"$pull": {"passed_users": {"user_id": target_id}}}
            )
            # Cleanup legacy plain-ID formatting if they exist
            await self.passes_collection.update_one(
                {"_id": self.interaction.user.id},
                {"$pull": {"passed_users": target_id}} 
            )
            self.user_passes = [p for p in self.user_passes if (isinstance(p, dict) and p.get("user_id") != target_id) and p != target_id]
        else:
            pass_entry = {"user_id": target_id, "timestamp": datetime.utcnow()}
            await self.passes_collection.update_one(
                {"_id": self.interaction.user.id},
                {"$push": {"passed_users": pass_entry}},
                upsert=True
            )
            self.user_passes.append(pass_entry)
            
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="👀 View Full Profile", style=discord.ButtonStyle.primary)
    async def view_full_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        match_info = self.matches[self.index]
        member = match_info["member"]
        doc = match_info["doc"]
        
        likes_data = await self.likes_collection.find_one({"_id": member.id})
        user_likes = likes_data.get("likes", []) if likes_data else []
        historical_likers = likes_data.get("historical_likers", []) if likes_data else []
        total_likes = len(user_likes)

        # Pull passes so the full profile paginator knows if they are passed too
        passes_data = await self.passes_collection.find_one({"_id": interaction.user.id})
        full_user_passes = passes_data.get("passed_users", []) if passes_data else []

        # (Assumes your updated ProfilePaginator exists in this file!)
        full_view = ProfilePaginator(
            target_user=member, 
            profile_data=doc, 
            author=interaction.user,
            likes_collection=self.likes_collection,
            activity_collection=self.activity_collection,
            passes_collection=self.passes_collection,
            total_likes=total_likes,
            user_likes=user_likes,
            historical_likers=historical_likers,
            user_passes=full_user_passes
        )
        
        await interaction.response.send_message(
            content=f"Here is the full profile for **{member.display_name}**:", 
            embed=full_view.get_main_embed(), 
            view=full_view,
            ephemeral=True 
        )


# ==========================================
# FIND MATCH COG
# ==========================================
class FindMatch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.collection = self.db["dating_profiles"]
        self.active_searches = set()

    def extract_age(self, age_string: str) -> int:
        if not age_string: return 0
        match = re.search(r'\d+', str(age_string))
        return int(match.group()) if match else 0

    def check_gender_clash(self, user_gender: str, user_looking_for: str, target_gender: str, target_looking_for: str) -> bool:
        u_gen = user_gender.lower().strip()
        t_gen = target_gender.lower().strip()
        
        u_looking = [g.strip() for g in user_looking_for.split(',') if g.strip()]
        t_looking = [g.strip() for g in target_looking_for.split(',') if g.strip()]
        
        if not u_gen or not t_gen or not u_looking or not t_looking:
            return False # Avoid hard crashes if missing data
            
        if u_gen not in t_looking and "any" not in t_looking:
            return True
            
        if t_gen not in u_looking and "any" not in u_looking:
            return True
            
        return False

    def check_sexuality_clash(self, user_sex: str, target_sex: str) -> bool:
        u_sex = user_sex.lower()
        t_sex = target_sex.lower()
        
        u_straight = "straight" in u_sex or "hetero" in u_sex
        u_gay = "gay" in u_sex or "lesbian" in u_sex or "homo" in u_sex
        
        t_straight = "straight" in t_sex or "hetero" in t_sex
        t_gay = "gay" in t_sex or "lesbian" in t_sex or "homo" in t_sex
        
        if u_straight and t_gay: return True
        if u_gay and t_straight: return True
        return False

    def check_relationship_clash(self, user_rel: str, target_rel: str) -> bool:
        u_rel = user_rel.lower()
        t_rel = target_rel.lower()
        
        if "any" in u_rel or "any" in t_rel:
            return False
        
        u_mono = "mono" in u_rel
        u_poly = "poly" in u_rel or "open" in u_rel
        t_mono = "mono" in t_rel
        t_poly = "poly" in t_rel or "open" in t_rel
        
        if (u_mono and not u_poly) and t_poly: return True
        if (t_mono and not t_poly) and u_poly: return True
        return False

    @app_commands.command(name="findmatch", description="Find your best matches amongst the server members")
    @app_commands.checks.has_role(1358469974552870913) # 18+ Role ID
    async def findmatch(self, interaction: discord.Interaction):
        if interaction.user.id in self.active_searches:
            await interaction.response.send_message("⚠️ You already have a match search in progress! Please wait for it to finish. I will ping you when it's done.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=False)
        self.active_searches.add(interaction.user.id)

        try:
            user_profile = await self.collection.find_one({"_id": interaction.user.id})
            
            if not user_profile:
                await interaction.followup.send("⚠️ You don't have a profile yet! Run `/startprofile` first.", ephemeral=True)
                return
                
            if str(user_profile.get("is_looking", "yes")).strip().lower() not in ["yes", "y", "yeah"]:
                await interaction.followup.send("⚠️ Your profile is set to 'Not Looking'. Update it with `/editprofile` to find matches!", ephemeral=True)
                return

            # Get the users they've passed on
            passes_data = await self.db["profile_passes"].find_one({"_id": interaction.user.id})
            user_passes = passes_data.get("passed_users", []) if passes_data else []
            passed_ids = [p.get("user_id") if isinstance(p, dict) else p for p in user_passes]

            # Extract User Data for Filtering
            user_gender = str(user_profile.get("gender", "any")).lower().strip()
            user_looking_for_gender = str(user_profile.get("looking_for_gender", "any")).lower().strip()

            user_age = self.extract_age(user_profile.get("age", "18"))
            user_min_target = self.extract_age(user_profile.get("looking_for_min_age", "18"))
            user_max_target = self.extract_age(user_profile.get("looking_for_max_age", "99"))
            if user_max_target == 0: user_max_target = 99
            
            user_sexuality = str(user_profile.get("sexuality", "N/A"))
            user_relationship = str(user_profile.get("looking_for_relationship_type", "N/A"))
            
            all_profiles = await self.collection.find({"is_looking": {"$regex": "^yes|y", "$options": "i"}}).to_list(None)
            
            # 1. HARD FILTERING
            valid_candidates = []
            for target_profile in all_profiles:
                if target_profile["_id"] == interaction.user.id: continue
                
                # Cross-Reference Not Interested list!
                if target_profile["_id"] in passed_ids: continue 
                
                target_member = interaction.guild.get_member(target_profile["_id"])
                if not target_member: continue

                target_gender = str(target_profile.get("gender", "")).lower().strip()
                target_looking_for = str(target_profile.get("looking_for_gender", "")).lower()
                
                if self.check_gender_clash(user_gender, user_looking_for_gender, target_gender, target_looking_for): continue
                
                target_age = self.extract_age(target_profile.get("age", "0"))
                if target_age != 0 and not (user_min_target <= target_age <= user_max_target): continue
                
                target_min_target = self.extract_age(target_profile.get("looking_for_min_age", "18"))
                target_max_target = self.extract_age(target_profile.get("looking_for_max_age", "99"))
                if target_max_target == 0: target_max_target = 99
                
                if user_age != 0 and not (target_min_target <= user_age <= target_max_target): continue
                
                if self.check_sexuality_clash(user_sexuality, str(target_profile.get("sexuality", ""))): continue
                if self.check_relationship_clash(user_relationship, str(target_profile.get("looking_for_relationship_type", ""))): continue
                
                valid_candidates.append(target_profile)

            if not valid_candidates:
                await interaction.followup.send("Wow, you have strict filters! No users currently match your exact requirements. Check back later!", ephemeral=True)
                return

            # 2. THE AI VIBE CHECK (Only send the top 15 candidates to save processing time)
            top_15_candidates = valid_candidates[:15]
            
            # --- LOADING BAR BACKGROUND TASK ---
            stop_event = asyncio.Event()

            async def update_loading_bar():
                progress = 10
                while not stop_event.is_set() and progress <= 95:
                    bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))
                    try:
                        await interaction.edit_original_response(
                            content=(
                                f"**Matchmaker is analyzing profiles!**\n"
                                f"Reading bios, comparing hobbies, and checking vibe compatibility...\n"
                                f"`[{bar}] {progress}%`\n\n"
                                f"*(This takes a little bit! Feel free to leave or chat elsewhere. I will ping you when your results are ready.)*"
                            )
                        )
                    except discord.HTTPException:
                        pass 
                    progress += 10
                    await asyncio.sleep(2)

            loader_task = asyncio.create_task(update_loading_bar())

            try:
                ai_scores = await get_ai_vibe_scores(user_profile, top_15_candidates)
            finally:
                stop_event.set()
                await loader_task

            # 3. BUILD FINAL RESULTS
            scored_matches = []
            for target_profile in top_15_candidates:
                target_member = interaction.guild.get_member(target_profile["_id"])
                if not target_member:
                    continue
                
                ai_data = ai_scores.get(target_profile["_id"], {
                    "score": 50, 
                    "shared_interests": "Unclear",
                    "about": "Passed basic demographic checks.",
                    "differences": "None immediately visible."
                })
                
                scored_matches.append({
                    "member": target_member,
                    "doc": target_profile,
                    "score": ai_data["score"],
                    "shared_interests": ai_data["shared_interests"],
                    "about": ai_data["about"],
                    "differences": ai_data["differences"]
                })

            scored_matches.sort(key=lambda x: x["score"], reverse=True)

            if not scored_matches:
                await interaction.edit_original_response(content="⚠️ Something went wrong compiling your matches. Please try again later.")
                return

            view = MatchPaginator(interaction, scored_matches, self.db, user_passes)
            
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass

            await interaction.followup.send(
                content=f"🎯 {interaction.user.mention}, **I found your top {len(scored_matches)} potential matches!**", 
                embed=view.get_match_embed(), 
                view=view
            )

        finally:
            self.active_searches.discard(interaction.user.id)

async def setup(bot):
    await bot.add_cog(FindMatch(bot))