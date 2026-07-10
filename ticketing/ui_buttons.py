import discord
from discord.ui import View, button
from discord import ButtonStyle
from db.database import get_connection
from ticketing.ticket_manager import TicketManager

# ==========================================
# CONSTANTS & CATEGORIES
# ==========================================
NSFW_OPEN_CATEGORY = 1362459990245245151
NSFW_ROLE_ID = 1358469974552870913
STAFF_APP_CATEGORY = 1362459990245245151 
SUPPORT_TICKET_CATEGORY = 1362459990245245151

# Roles for NSFW tickets
MOD_ROLES = [
    1358472557862457537,  # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1416866395366359193,  # Bad Dragon
    1358473248534167663   # Owner
]

# Admin+ Roles for Private Staff Application Access
ADMIN_ACCESS_ROLES = [
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1416866395366359193,  # Bad Dragon
    1358473248534167663   # Owner
]

# All Staff roles for General Support (Helper and up)
STAFF_LADDER_ROLES = [
    1358470318087340342,  # Helper
    1358472557862457537,  # Jr Mod
    1358472532222808126,  # Mod
    1358472588430676018,  # Sr Mod
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1416866395366359193,  # Bad Dragon
    1358473248534167663   # Owner
]

# ==========================================
# NSFW VERIFY BUTTON
# ==========================================
class NSFWVerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(
        label="Request NSFW Access 🔞",
        style=ButtonStyle.danger,
        custom_id="nsfw_ticket_open"
    )
    async def nsfw_open(self, interaction: discord.Interaction, btn):
        db = get_connection()
        user = interaction.user
        
        # --- LEVEL CHECK ---
        user_data = await db["users"].find_one({"discordId": user.id})
        if not user_data or user_data.get("level", 0) < 5:
            return await interaction.response.send_message(
                "❌ You must be at least **Level 5** to request NSFW access.", ephemeral=True
            )

        tm = TicketManager(db)
        guild = interaction.guild

        if guild.get_role(NSFW_ROLE_ID) in user.roles:
            return await interaction.response.send_message(
                "🔞 You are **already verified** and have access to NSFW channels.",
                ephemeral=True
            )

        existing = await tm.find_open_ticket(user.id, ticket_type="nsfw")
        if existing:
            try:
                chan_id = int(existing["channel_id"])
                existing_chan = guild.get_channel(chan_id)
            except:
                existing_chan = None

            if existing_chan:
                return await interaction.response.send_message(
                    f"❗ You already have an open NSFW verification ticket:\n➡️ {existing_chan.mention}",
                    ephemeral=True
                )
            else:
                try:
                    await tm.close(existing["ticket_id"], staff_id=guild.me.id)
                except:
                    pass

        await interaction.response.send_message("Creating your **NSFW verification** ticket...", ephemeral=True)

        category = guild.get_channel(NSFW_OPEN_CATEGORY)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        for role_id in MOD_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, attach_files=True, embed_links=True
                )

        channel = await guild.create_text_channel(
            name=f"nsfw-{user.name}".replace(" ", "-").lower(),
            category=category,
            overwrites=overwrites,
            topic=f"NSFW verification for {user.id}"
        )

        interaction.client.dispatch("ticket_opened", interaction, channel)

# ==========================================
# STAFF APPLY BUTTON
# ==========================================
class StaffApplyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Apply for Staff 📝",
        style=discord.ButtonStyle.success,
        custom_id="staff_apply_button"
    )
    async def apply_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = get_connection()
        user = interaction.user
        guild = interaction.guild
        
        # --- LEVEL CHECK ---
        user_data = await db["users"].find_one({"discordId": user.id})
        if not user_data or user_data.get("level", 0) < 5:
            return await interaction.response.send_message(
                "❌ You must be at least **Level 5** to apply for staff.", ephemeral=True
            )

        STAFF_TEAM_ROLE_ID = 1358470109965979859
        if any(role.id == STAFF_TEAM_ROLE_ID for role in user.roles):
            return await interaction.response.send_message(
                "❌ You are already a member of the staff team!", ephemeral=True
            )

        tm = TicketManager(db)
        existing = await tm.tickets.find_one({
            "user_id": str(user.id),
            "status": "open",
            "ticket_type": "staff-application"
        })

        if existing:
            return await interaction.response.send_message(
                "❌ You already have an open staff application!", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(STAFF_APP_CATEGORY)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        for role_id in ADMIN_ACCESS_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_messages=True, manage_channels=True
                )

        channel = await guild.create_text_channel(
            name=f"staff-{user.name}".replace(" ", "-").lower(),
            category=category,
            overwrites=overwrites,
            topic=f"Private Staff Application for {user.id}"
        )

        interaction.client.dispatch("ticket_opened", interaction, channel)
        await interaction.followup.send(f"✅ Application created: {channel.mention}", ephemeral=True)

# ==========================================
# SUPPORT TICKET BUTTON
# ==========================================
class SupportTicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Support Ticket 🎫",
        style=discord.ButtonStyle.primary,
        custom_id="support_ticket_button"
    )
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = get_connection()
        user = interaction.user
        guild = interaction.guild
        
        # --- LEVEL CHECK ---
        user_data = await db["users"].find_one({"discordId": user.id})
        if not user_data or user_data.get("level", 0) < 5:
            return await interaction.response.send_message(
                "❌ You must be at least **Level 5** to open a support ticket.", ephemeral=True
            )

        tm = TicketManager(db)
        existing = await tm.tickets.find_one({
            "user_id": str(user.id),
            "status": "open",
            "ticket_type": "support"
        })

        if existing:
            return await interaction.response.send_message(
                "❌ You already have an open support ticket!", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(SUPPORT_TICKET_CATEGORY)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        # Grant access to all staff roles for general support
        for role_id in STAFF_LADDER_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"sup-{user.name}".replace(" ", "-").lower(),
            category=category,
            overwrites=overwrites,
            topic=f"General Support for {user.id}"
        )

        interaction.client.dispatch("ticket_opened", interaction, channel)
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)