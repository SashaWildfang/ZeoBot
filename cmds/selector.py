import discord
from discord.ext import commands
from discord import app_commands

# --- COMPREHENSIVE ROLE CONFIGURATION ---
ROLE_DATA = {
    "Gender": {
        "desc": "Select your gender identity to help others know who you are.",
        "color": discord.Color.from_str("#5dade2"),
        "roles": {
            "🚹 Male": [1358469893451682104, "Select this if you identify as male."],
            "🚺 Female": [1358469917850206368, "Select this if you identify as female."],
            "⚧️ Nonbinary": [1358470568340623432, "Select this if you identify outside the gender binary."],
            "🏳️‍⚧️ Trans (MtF)": [1358470591237062846, "Male to Female transgender identity."],
            "🏳️‍⚧️ Trans (FtM)": [1358470617476894862, "Female to Male transgender identity."],
            "🟡 Intersex": [1495855560527052881, "Select this if you are intersex."],
            "❓ Other Gender": [1358470654755864647, "Any identity not listed above."]
        }
    },
    "Pronouns": {
        "desc": "Let us know which pronouns you prefer we use for you.",
        "color": discord.Color.from_str("#48c9b0"),
        "roles": {
            "💬 He/Him": [1358470364866547994, "Standard masculine pronouns."],
            "💬 She/Her": [1358470384025866311, "Standard feminine pronouns."],
            "💬 They/Them": [1358470488984391921, "Gender-neutral pronouns."],
            "🌈 Any Pronouns": [1358470508940890182, "You are comfortable with any pronouns."],
            "❓ Ask Pronouns": [1498070570900783256, "Please ask for my preferred pronouns."]
        }
    },
    "Sexuality": {
        "desc": "Identify your orientation within the community.",
        "color": discord.Color.from_str("#af7ac5"),
        "roles": {
            "🏳️‍🌈 Gay": [1358471129915723949, "Attraction to the same gender."],
            "💖 Bisexual": [1358471298837250118, "Attraction to two or more genders."],
            "💛 Pansexual": [1358471351182033089, "Attraction regardless of gender."],
            "🖤 Asexual": [1358471374515081597, "Little to no sexual attraction."],
            "💚 Aromantic": [1495855107580100708, "Little to no romantic attraction."],
            "👫 Straight": [1358471406626537663, "Attraction to the opposite gender."],
            "🔍 Questioning": [1358471428902490272, "Currently exploring your orientation."],
            "💜 Demisexual": [1358819082790637768, "Attraction only after a strong bond."]
        }
    },
    "Location": {
        "desc": "General region you reside in.",
        "color": discord.Color.from_str("#f4d03f"),
        "roles": {
            "🇺🇸 United States": [1358474003831849091, "Located in the USA."],
            "🇨🇦 Canada": [1358819870392717446, "Located in Canada."],
            "🇪🇺 Europe": [1358474080080232739, "Located in Europe."],
            "🌏 Asia": [1358474114658209942, "Located in Asia."],
            "🇦🇺 Oceania": [1358474136292294667, "Located in Australia/Oceania."],
            "🇧🇷 South America": [1358474162691375284, "Located in South America."],
            "🌍 Africa": [1358474188242948318, "Located in Africa."]
        }
    },
    "Timezone": {
        "desc": "Helps others know when you are awake and active.",
        "color": discord.Color.from_str("#2e4053"),
        "roles": {
            "⏰ EST": [1358474214113411234, "Eastern Standard Time."],
            "⏰ CST": [1358474240004853991, "Central Standard Time."],
            "⏰ MST": [1358474264260645067, "Mountain Standard Time."],
            "⏰ PST": [1358474285248938024, "Pacific Standard Time."],
            "🌐 GMT": [1358474323018649677, "Greenwich Mean Time."],
            "🌐 CET": [1358474345810231529, "Central European Time."],
            "🇦🇺 AEST": [1358474403997946037, "Australian Eastern Standard Time."],
            "🌐 AKST": [1488179988497956904, "Alaska Standard Time."]
        }
    },
    "Preferences": {
        "desc": "Your personal boundaries for DMs and Pings.",
        "color": discord.Color.from_str("#ccd1d1"),
        "roles": {
            "🔓 DMs Open": [1358476316437123108, "Anyone can message you."],
            "🔒 DMs Closed": [1358476342924021790, "Please do not DM me."],
            "✉️ Ask to DM": [1358476363329310930, "Please ask in public before DMing."],
            "🔔 Ping Me": [1358476383650840848, "You are okay with being mentioned."],
            "🔕 Dont Ping Me": [1358476416148307988, "Please avoid pinging me directly."]
        }
    },
    "Hobbies": {
        "desc": "What are your interests and hobbies?",
        "color": discord.Color.from_str("#1e8449"),
        "roles": {
            "✍️ Writer": [1358476638957994085, "You enjoy creative writing or poetry."],
            "🎵 Musician": [1358476684159877291, "You play instruments or produce music."],
            "🐾 Pet Owner": [1358476726287601818, "You have animal companions."],
            "🦊 Fursuiter": [1358476748525797396, "You own or enjoy fursuiting."],
            "🌿 Stoner Furry": [1358476780616548555, "420-friendly lifestyle."],
            "💪 Fitness Furry": [1358476825650794667, "Interested in gym or athletics."],
            "💻 PC Gamer": [1358476461765431356, "You play games on PC."],
            "🎮 Console Gamer": [1504466095082573917, "You play games on a console."],
            "📱 Mobile Gamer": [1358476558754517143, "You play on phone or tablet."]
        }
    },
    "Pings": {
        "desc": "Manage your notification pings for server activity.",
        "color": discord.Color.from_str("#e74c3c"),
        "roles": {
            "👋 Welcome Ping": [1363972389188276264, "Pings when new members join."],
            "📢 Announcements": [1363972415822237747, "General server news and updates."],
            "🔥 Chat Revive": [1488184349286338892, "Pings to bring life back to the chat."],
            "🛒 Store Ping": [1503069470908878969, "Pings related to store updates and offers."]
        }
    }
}

class SummaryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="View My Roles", style=discord.ButtonStyle.primary, custom_id="btn_view_summary")
    async def view_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        found_roles = []
        for cat_name, data in ROLE_DATA.items():
            cat_roles = []
            for name, info in data['roles'].items():
                role = interaction.guild.get_role(info[0])
                if role and role in interaction.user.roles:
                    cat_roles.append(name)
            if cat_roles:
                found_roles.append(f"**{cat_name.replace('_', ' ')}:** {', '.join(cat_roles)}")
        
        if found_roles:
            msg = "🔍 **Your Current Gallery Roles:**\n\n" + "\n".join(found_roles)
        else:
            msg = "❌ You haven't selected any roles from the gallery yet!"
        
        await interaction.followup.send(msg, ephemeral=True)

class ConfirmResetView(discord.ui.View):
    def __init__(self, category_key, category_ids, user_has_names):
        super().__init__(timeout=60)
        self.category_key = category_key
        self.category_ids = category_ids
        self.user_has_names = user_has_names

    @discord.ui.button(label="Yes, Clear Roles", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        removed_names = []
        for rid in self.category_ids:
            role = interaction.guild.get_role(rid)
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role)
                    removed_names.append(role.name)
                except: continue
        
        if removed_names:
            await interaction.followup.send(f"🧹 **Section Cleared!**\nRemoved: {', '.join(removed_names)}", ephemeral=True)
        else:
            await interaction.followup.send("✨ No roles from this section were found on your profile.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()

class ArtistApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Artist Roles", style=discord.ButtonStyle.primary, custom_id="btn_goto_artist_verify")
    async def goto_artist(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket_channel_id = 1495841072423899276
        await interaction.response.send_message(
            f"Please head over to <#{ticket_channel_id}> to open a ticket and apply for an Artist Role", 
            ephemeral=True
        )

class IDVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Take me to ID Verification", style=discord.ButtonStyle.success, custom_id="btn_goto_id_verify")
    async def goto_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        verify_channel_id = 1358485673991999721 
        await interaction.response.send_message(
            f"Please head over to <#{verify_channel_id}> to begin your ID verification process! 🛡️", 
            ephemeral=True
        )

class PersistentRoleSelect(discord.ui.Select):
    def __init__(self, category_name, roles_info):
        self.category_name = category_name
        self.roles_info = roles_info
        options = [
            discord.SelectOption(label=name, value=str(info[0]), description=info[1])
            for name, info in roles_info.items()
        ]
        super().__init__(
            placeholder=f"Pick your {category_name.replace('_', ' ')} roles...",
            min_values=0, max_values=len(options),
            options=options, custom_id=f"sel_role:{category_name}"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        selected_ids = [int(val) for val in self.values]
        category_ids = [info[0] for info in self.roles_info.values()]
        added, removed = [], []

        for role_id in category_ids:
            role = interaction.guild.get_role(role_id)
            if not role: continue
            if role_id in selected_ids:
                if role not in member.roles:
                    await member.add_roles(role)
                    added.append(role.name)
            else:
                if role in member.roles:
                    await member.remove_roles(role)
                    removed.append(role.name)

        msg = []
        if added: msg.append(f"✅ Added: {', '.join(added)}")
        if removed: msg.append(f"❌ Removed: {', '.join(removed)}")
        await interaction.followup.send("\n".join(msg) if msg else "No changes made.", ephemeral=True)

class RoleView(discord.ui.View):
    def __init__(self, category_name=None):
        super().__init__(timeout=None)
        if category_name:
            self.add_item(PersistentRoleSelect(category_name, ROLE_DATA[category_name]["roles"]))
            
    @discord.ui.button(label="Clear Roles in this section", style=discord.ButtonStyle.danger, custom_id="btn_reset_cat")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        title = interaction.message.embeds[0].title
        category_key = None
        for key in ROLE_DATA.keys():
            if key.replace('_', ' ') in title:
                category_key = key
                break
        if not category_key:
            return await interaction.response.send_message("❌ Error identifying category.", ephemeral=True)

        category_ids = [info[0] for info in ROLE_DATA[category_key]["roles"].values()]
        user_has_these = []
        for rid in category_ids:
            role = interaction.guild.get_role(rid)
            if role and role in interaction.user.roles:
                user_has_these.append(f"**{role.name}**")

        if not user_has_these:
            return await interaction.response.send_message(f"✨ You don't have any roles from the **{category_key.replace('_', ' ')}** section!", ephemeral=True)

        role_list_str = "\n".join([f"• {name}" for name in user_has_these])
        confirm_content = (f"⚠️ **Confirm Reset: {category_key.replace('_', ' ')}**\n\n"
                          f"Are you sure you want to clear this section? You currently have:\n"
                          f"{role_list_str}\n\n*Clicking 'Yes' will remove all of the above.*")
        view = ConfirmResetView(category_key, category_ids, user_has_these)
        await interaction.response.send_message(content=confirm_content, view=view, ephemeral=True)

class RoleSelector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="deploy_roles", description="Admin: Post the role selection gallery.")
    @app_commands.default_permissions(administrator=True)
    async def deploy_roles(self, interaction: discord.Interaction):
        await interaction.response.send_message("Creating role gallery...", ephemeral=True)
        
        summary_embed = discord.Embed(
            title="📋 Role Selection Overview",
            description="Lost track of what you've picked? Click the button below to see a private summary of your current gallery roles.",
            color=discord.Color.blue()
        )
        await interaction.channel.send(embed=summary_embed, view=SummaryView())

        for category, data in ROLE_DATA.items():
            embed = discord.Embed(
                title=f"🎭 {category.replace('_', ' ')} Roles",
                description=f"### {data['desc']}\n\n", color=data['color']
            )
            role_details = "".join([f"**{name}**\n*{info[1]}*\n\n" for name, info in data['roles'].items()])
            embed.description += role_details
            embed.set_footer(text="Use the dropdown below to select or unselect roles.")
            await interaction.channel.send(embed=embed, view=RoleView(category))

        # --- NEW ARTIST EMBED ---
        artist_embed = discord.Embed(
            title="🎨 Artist Applications & Commissions",
            description=(
                "Want to post your commission info in our server? You can apply for our Artist roles by opening a ticket in <#1495841072423899276>.\n\n"
                "### 🖌️ Available Roles\n"
                "• <@&1499426309972033746> - Grants access to post your info in <#1369654830058176602>.\n"
                "• <@&1499426344025723103> - Grants access to post your info in <#1369656851670765748>. *(Requires the <@&1358469974552870913> role)*\n\n"
                "### ⚠️ Rules & Disclaimer\n"
                "Failure to follow these rules will result in disciplinary actions, which normally fall within our warning/strike/ban format and can include revoking your Artist role if applicable. Cases of verifiable tracing, plagiarized material, theft, fraud/scamming and ToS-breaking material will be an immediate ban. Kitty Kingdom is not responsible for the transactions between artist and commissioner."
            ),
            color=discord.Color.from_str("#9b59b6") 
        )
        await interaction.channel.send(embed=artist_embed, view=ArtistApplicationView())

        # --- ID VERIFICATION EMBED ---
        id_embed = discord.Embed(
            title="🛡️ Restricted Access & ID Verification",
            description=(
                "### 🛡️ Why Verify Your ID?\n"
                "Certain sections are locked behind age verification for safety.\n\n"
                "❤️ **Dating & Introductions:** Access to relationship roles and dating channels.\n"
                "🔥 **NSFW Media:** Full access to adult-only galleries.\n"
                "💬 **Restricted Channels:** Access to mature discussion areas.\n\n"
                "### 🔒 Your Privacy Matters\n"
                "Once confirmed, all provided ID images are permanently deleted."
            ), color=discord.Color.from_str("#f23a3a") 
        )
        await interaction.channel.send(embed=id_embed, view=IDVerificationView())

async def setup(bot):
    await bot.add_cog(RoleSelector(bot))