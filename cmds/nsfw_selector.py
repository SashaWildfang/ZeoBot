import discord
from discord.ext import commands
from discord import app_commands

# --- COMPREHENSIVE NSFW/RELATIONSHIP ROLE CONFIGURATION ---
NSFW_ROLE_DATA = {
    "Relationship_Type": {
        "desc": "How do you prefer to structure your relationships?",
        "color": discord.Color.from_str("#e91e63"), # Pink
        "roles": {
            "💍 Monogamous": [1358471476679934074, "Dedicated to one partner."],
            "🌈 Polyamorous": [1358471502575571214, "Open to multiple romantic partners."],
            "🔓 Open Relationship": [1358471533642776758, "Committed but sexually open."],
            "🔒 Closed Relationship": [1358471579033670004, "Not looking for outside additions."]
        }
    },
    "Relationship_Status": {
        "desc": "What is your current availability?",
        "color": discord.Color.from_str("#9b59b6"), # Purple
        "roles": {
            "❤️ Taken": [1358471717764468997, "Currently in a relationship."],
            "🔍 Looking": [1359165195536171048, "Seeking new connections."],
            "🚫 Not Looking": [1358471668695171072, "Not currently seeking anyone."]
        }
    },
    "Looking_For": {
        "desc": "Specify what or who you are looking for.",
        "color": discord.Color.from_str("#f1c40f"), # Gold
        "roles": {
            "🔥 Partner": [1358471789595988224, "Seeking a romantic partner."],
            "🫂 Friends": [1358471820575248688, "Seeking platonic friendships."],
            "🧬 Poly Connections": [1358484800507216039, "Seeking polyamorous dynamics."],
            "💍 Mono Connections": [1358484767565152447, "Seeking monogamous dynamics."]
        }
    },
    "Positions": {
        "desc": "Your preferred role in the bedroom.",
        "color": discord.Color.from_str("#2ecc71"), # Green
        "roles": {
            "⬆️ Top": [1358477166253310102, "Preferring the giving role."],
            "⬇️ Bottom": [1358477245307424798, "Preferring the receiving role."],
            "🔄 Switch": [1358477262869102744, "Comfortable with both roles."],
            "🔼 Vers Top": [1359174049292620008, "Versatile, but prefers topping."],
            "🔽 Vers Bottom": [1359174111007342813, "Versatile, but prefers bottoming."]
        }
    },
    "Notifications": {
        "desc": "Opt-in to server pings and alerts.",
        "color": discord.Color.from_str("#5865F2"), # Discord Blurple
        "roles": {
            "🔔 Introduction Ping": [1497237607044747375, "Get pinged when a new dating profile is posted!"]
        }
    }
}

# --- REUSABLE COMPONENTS ---

class NSFWConfirmResetView(discord.ui.View):
    def __init__(self, category_key, category_ids, user_has_names):
        super().__init__(timeout=60)
        self.category_key = category_key
        self.category_ids = category_ids
        self.user_has_names = user_has_names

    @discord.ui.button(label="Yes, Clear Roles", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        removed = []
        for rid in self.category_ids:
            role = interaction.guild.get_role(rid)
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role)
                    removed.append(role.name)
                except: continue
        
        if removed:
            await interaction.followup.send(f"🧹 **Section Cleared!**\nRemoved: {', '.join(removed)}", ephemeral=True)
        else:
            await interaction.followup.send("✨ No roles from this section were found.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()

class NSFWSummaryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="View My NSFW/Relationship Roles", style=discord.ButtonStyle.primary, custom_id="btn_view_nsfw_summary")
    async def view_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        found = []
        for cat_name, data in NSFW_ROLE_DATA.items():
            cat_roles = []
            for name, info in data['roles'].items():
                role = interaction.guild.get_role(info[0])
                if role and role in interaction.user.roles:
                    cat_roles.append(name)
            if cat_roles:
                found.append(f"**{cat_name.replace('_', ' ')}:** {', '.join(cat_roles)}")
        
        msg = "🔍 **Your Current Roles:**\n\n" + "\n".join(found) if found else "❌ No roles selected yet."
        await interaction.followup.send(msg, ephemeral=True)

class NSFWRoleSelect(discord.ui.Select):
    def __init__(self, category_name, roles_info):
        self.roles_info = roles_info # FIXED: Store roles_info for use in callback
        options = [discord.SelectOption(label=name, value=str(info[0]), description=info[1]) for name, info in roles_info.items()]
        super().__init__(
            placeholder=f"Pick your {category_name.replace('_', ' ')} roles...",
            min_values=0, max_values=len(options),
            options=options, custom_id=f"nsfw_sel:{category_name}"
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
                    try:
                        await member.add_roles(role)
                        added.append(role.name)
                    except discord.Forbidden:
                        return await interaction.followup.send("❌ I cannot manage this role. Ensure my bot role is higher than the roles I am giving!", ephemeral=True)
            else:
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                        removed.append(role.name)
                    except discord.Forbidden:
                        continue

        msg = []
        if added: msg.append(f"✅ Added: {', '.join(added)}")
        if removed: msg.append(f"❌ Removed: {', '.join(removed)}")
        await interaction.followup.send("\n".join(msg) if msg else "No changes made.", ephemeral=True)

class NSFWView(discord.ui.View):
    def __init__(self, category_name=None):
        super().__init__(timeout=None)
        if category_name:
            self.add_item(NSFWRoleSelect(category_name, NSFW_ROLE_DATA[category_name]["roles"]))
            
    @discord.ui.button(label="Clear Roles in this section", style=discord.ButtonStyle.danger, custom_id="btn_reset_nsfw")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        title = interaction.message.embeds[0].title
        category_key = None
        for key in NSFW_ROLE_DATA.keys():
            if key.replace('_', ' ') in title:
                category_key = key
                break
        
        if not category_key: return await interaction.response.send_message("❌ Error.", ephemeral=True)

        category_ids = [info[0] for info in NSFW_ROLE_DATA[category_key]["roles"].values()]
        user_has = []
        for rid in category_ids:
            role = interaction.guild.get_role(rid)
            if role and role in interaction.user.roles:
                user_has.append(f"**{role.name}**")

        if not user_has:
            return await interaction.response.send_message("✨ No roles to clear here.", ephemeral=True)

        view = NSFWConfirmResetView(category_key, category_ids, user_has)
        await interaction.response.send_message(
            content=f"⚠️ **Clear {category_key.replace('_', ' ')}?**\nRoles: {', '.join(user_has)}",
            view=view, ephemeral=True
        )

# --- COG SETUP ---
class NSFWRoleSelector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="deploy_nsfw_roles", description="Admin: Post the NSFW role gallery.")
    @app_commands.default_permissions(administrator=True)
    async def deploy_nsfw_roles(self, interaction: discord.Interaction):
        await interaction.response.send_message("Deploying NSFW role gallery...", ephemeral=True)
        
        # Summary Button
        summary_embed = discord.Embed(
            title="🔞 Role Overview",
            description="Click below to see your currently selected Relationship, Ping, and NSFW roles.",
            color=discord.Color.dark_red()
        )
        await interaction.channel.send(embed=summary_embed, view=NSFWSummaryView())

        # Main Sections
        for category, data in NSFW_ROLE_DATA.items():
            # Check if we should use a different emoji for the notifications section
            emoji = "🔔" if category == "Notifications" else "🔞"
            
            embed = discord.Embed(
                title=f"{emoji} {category.replace('_', ' ')} Roles",
                description=f"### {data['desc']}\n\n", color=data['color']
            )
            role_details = "".join([f"**{name}**\n*{info[1]}*\n\n" for name, info in data['roles'].items()])
            embed.description += role_details
            await interaction.channel.send(embed=embed, view=NSFWView(category))

async def setup(bot):
    await bot.add_cog(NSFWRoleSelector(bot))