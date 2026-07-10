import discord
import random
import string
from discord import app_commands
from discord.ext import commands
import traceback
from typing import Literal
from datetime import datetime

# ==========================================================
# IMPORTS
# ==========================================================
from db.database import get_connection
from ticketing.ticket_manager import TicketManager
from ticketing.ticket_controls import ConfirmDeleteView, STAFF_ROLES, CAT_OPEN, CAT_CLAIMED, CAT_CLOSED

# Put your log channel ID here
BOT_LOGS_CHANNEL_ID = 1360344042705256660

# ==========================================================
# HIERARCHY SETUP FOR SPECIAL TICKETS
# ==========================================================
STAFF_TEAM_ROLE = 1358470109965979859

# Ranks are assigned a level (Higher number = Higher rank)
STAFF_HIERARCHY = {
    1358470318087340342: 1,  # Helper
    1358472557862457537: 2,  # Jr Mod
    1358472532222808126: 3,  # Mod
    1358472588430676018: 4,  # Sr Mod
    1358472511133585564: 5,  # Admin
    1358472635234779207: 6   # Sr Admin
}

# Roles that ALWAYS get access to these special tickets
SPECIAL_ROLES = [
    1416866395366359193, # Dustin's Sr Admin
    1358473248534167663  # Your Role
]

# ==========================================================
# CONFIRMATION VIEW FOR ADD/REMOVE USER
# ==========================================================
class ConfirmUserView(discord.ui.View):
    def __init__(self, action: str, target: discord.Member):
        super().__init__(timeout=60)
        self.action = action
        self.target = target
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()

# ==========================================================
# TICKET CONTROLS VIEW (BUTTONS FOR THE EMBED)
# ==========================================================
class TicketControlsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="btn_ticket_claim", emoji="🎟️")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        if not is_staff:
            return await interaction.response.send_message("⛔ Staff only. You cannot claim this.", ephemeral=True)

        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)
        
        if not ticket:
            return await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
        if ticket.get("status") in ["closed", "deleted"]:
            return await interaction.response.send_message("⚠️ This ticket is closed!", ephemeral=True)
        if ticket.get("claimed_by"):
            return await interaction.response.send_message("⚠️ Already claimed.", ephemeral=True)

        await interaction.response.defer()
        await tm.claim(ticket["ticket_id"], interaction.user.id)
        claimed_category = interaction.guild.get_channel(CAT_CLAIMED)
        if claimed_category:
            await interaction.channel.edit(category=claimed_category)

        await interaction.followup.send(f"🎟️ Ticket claimed by {interaction.user.mention}.")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="btn_ticket_close", emoji="🔒")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)
        
        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        is_creator = str(interaction.user.id) == str(ticket.get("user_id")) if ticket else False
        
        if not (is_staff or is_creator):
            return await interaction.response.send_message("⛔ You do not have permission to close this.", ephemeral=True)

        if not ticket:
            return await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
        if ticket.get("status") in ["closed", "deleted"]:
            return await interaction.response.send_message("⚠️ Already closed.", ephemeral=True)

        await interaction.response.defer()
        
        await tm.close(ticket["ticket_id"], interaction.user.id)
        await tm.tickets.update_one({"ticket_id": ticket["ticket_id"]}, {"$set": {"claimed_by": None}})

        overwrites = interaction.channel.overwrites
        for target in overwrites:
            overwrites[target].update(send_messages=False)

        target = interaction.guild.get_channel(CAT_CLOSED)
        await interaction.channel.edit(
            category=target if target else interaction.channel.category,
            overwrites=overwrites
        )
        await interaction.followup.send("🔒 **Ticket closed and channel locked.**")

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.primary, custom_id="btn_ticket_reopen", emoji="🔓")
    async def reopen_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)
        
        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        if not is_staff:
            return await interaction.response.send_message("⛔ Staff only. You cannot reopen this.", ephemeral=True)

        if not ticket:
            return await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
        if ticket.get("status") != "closed":
            return await interaction.response.send_message("⚠️ This ticket is not closed.", ephemeral=True)

        await interaction.response.defer()
        await tm.tickets.update_one(
            {"ticket_id": ticket["ticket_id"]}, 
            {"$set": {"status": "open", "closed_at": None, "closed_by": None, "claimed_by": None}}
        )

        overwrites = interaction.channel.overwrites
        for target in overwrites:
            if target != interaction.guild.default_role:
                overwrites[target].update(send_messages=True)

        target = interaction.guild.get_channel(CAT_OPEN)
        await interaction.channel.edit(
            category=target if target else interaction.channel.category,
            overwrites=overwrites
        )
        await interaction.followup.send("🔓 **Ticket reopened and unlocked.**")

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.secondary, custom_id="btn_ticket_delete", emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)
        
        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        is_creator = str(interaction.user.id) == str(ticket.get("user_id")) if ticket else False
        
        if not (is_staff or is_creator):
            return await interaction.response.send_message("⛔ You do not have permission to delete this.", ephemeral=True)

        if not ticket:
            return await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)

        # Triggers your existing ConfirmDeleteView which handles the transcript!
        await interaction.response.send_message(
            f"⚠️ Confirm deletion of ticket `{ticket['ticket_id']}`?",
            view=ConfirmDeleteView(ticket["ticket_id"]),
            ephemeral=True
        )

# ==========================================================
# MAIN COG
# ==========================================================
class TicketCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket", description="Manage the current ticket")
    @app_commands.describe(
        action="Choose the action to perform on this ticket",
        user="The user to add, remove, or create a special ticket for"
    )
    async def ticket_action(
        self, 
        interaction: discord.Interaction, 
        action: Literal["claim", "close", "reopen", "delete", "status", "adduser", "removeuser", "create"],
        user: discord.Member = None
    ):
        
        # ==========================================
        # ACTION: CREATE (Special Support Ticket)
        # ==========================================
        if action == "create":
            await interaction.response.defer(ephemeral=True)
            
            is_staff_team = any(r.id == STAFF_TEAM_ROLE for r in interaction.user.roles)
            if not is_staff_team:
                return await interaction.followup.send("⛔ You need the Staff Team role to create special tickets.")
            
            if not user:
                return await interaction.followup.send("❌ You must specify a user to create a ticket for.")
            
            # --- PREVENT CREATING TICKET WITH SELF ---
            if user.id == interaction.user.id:
                return await interaction.followup.send("❌ You cannot create a special ticket with yourself.")
                
            creator_level = 0
            is_special = any(r.id in SPECIAL_ROLES for r in interaction.user.roles)

            if is_special:
                creator_level = 999 
            else:
                for role in interaction.user.roles:
                    if role.id in STAFF_HIERARCHY:
                        creator_level = max(creator_level, STAFF_HIERARCHY[role.id])
                
                if creator_level == 0:
                    creator_level = 1

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
            }
            
            for role_id, level in STAFF_HIERARCHY.items():
                if level >= creator_level:
                    role_obj = interaction.guild.get_role(role_id)
                    if role_obj:
                        overwrites[role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
            
            for role_id in SPECIAL_ROLES:
                role_obj = interaction.guild.get_role(role_id)
                if role_obj:
                    overwrites[role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
                    
            try:
                category = interaction.guild.get_channel(CAT_OPEN)
                ticket_channel = await interaction.guild.create_text_channel(
                    name=f"pm-{user.name}",
                    category=category,
                    overwrites=overwrites
                )
                
                tm = TicketManager(get_connection())
                ticket_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                
                await tm.tickets.insert_one({
                    "ticket_id": ticket_id,
                    "channel_id": str(ticket_channel.id),
                    "user_id": str(interaction.user.id),  # <--- FIX: Now logs the command runner as the creator
                    "status": "open",
                    "created_at": datetime.utcnow(),
                    "claimed_by": None,
                    "special_ticket": True
                })
                
                embed = discord.Embed(
                    title="🔒 Special Support Ticket",
                    description=f"This ticket was created for {user.mention} by {interaction.user.mention}.\nOnly authorized staff tiers and the target user can view this channel.",
                    color=discord.Color.gold()
                )
                
                await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketControlsView())
                
                return await interaction.followup.send(f"✅ Special ticket created: {ticket_channel.mention}")
                
            except Exception as e:
                return await interaction.followup.send(f"❌ Failed to create special ticket: {e}")

        # ==========================================
        # STANDARD TICKET ACTIONS (Require existing ticket channel)
        # ==========================================
        
        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)

        if not ticket:
            return await interaction.response.send_message("❌ Ticket not found in DB or this is not a ticket channel.", ephemeral=True)

        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        is_creator = str(interaction.user.id) == str(ticket.get("user_id"))
        is_staff_team = any(r.id == STAFF_TEAM_ROLE for r in interaction.user.roles)

        if action in ["claim", "reopen"] and not is_staff:
            return await interaction.response.send_message("⛔ Staff only. You do not have permission to use this action.", ephemeral=True)
            
        if action in ["close", "delete", "status"] and not (is_staff or is_creator):
            return await interaction.response.send_message("⛔ You do not have permission to manage or view this ticket.", ephemeral=True)

        # ==========================================
        # ACTIONS: ADDUSER / REMOVEUSER
        # ==========================================
        if action in ["adduser", "removeuser"]:
            if not is_staff_team:
                return await interaction.response.send_message("⛔ You need the Staff Team role to use this action.", ephemeral=True)
            if not user:
                return await interaction.response.send_message("❌ You must specify a user for this action.", ephemeral=True)

            action_text = "add" if action == "adduser" else "remove"
            view = ConfirmUserView(action_text, user)
            
            await interaction.response.send_message(
                f"⚠️ Are you sure you want to **{action_text}** {user.mention} {'to' if action == 'adduser' else 'from'} this ticket?",
                view=view,
                ephemeral=True
            )
            
            await view.wait()

            if view.value is None:
                return await interaction.edit_original_response(content="⏳ Command timed out.", view=None)
            elif view.value is False:
                return await interaction.edit_original_response(content="❌ Action cancelled.", view=None)

            try:
                log_channel = interaction.guild.get_channel(BOT_LOGS_CHANNEL_ID)

                if action == "adduser":
                    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True, view_channel=True)
                    await interaction.edit_original_response(content=f"✅ {user.mention} has been successfully added to the ticket.", view=None)
                    await interaction.channel.send(f"👤 {user.mention} was added to the ticket by {interaction.user.mention}.")
                    
                    if log_channel:
                        embed = discord.Embed(title="👤 User Added to Ticket", color=discord.Color.green())
                        embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
                        embed.add_field(name="Added User", value=user.mention, inline=True)
                        embed.add_field(name="Added By", value=interaction.user.mention, inline=True)
                        await log_channel.send(embed=embed)

                elif action == "removeuser":
                    await interaction.channel.set_permissions(user, overwrite=None)
                    await interaction.edit_original_response(content=f"✅ {user.mention} has been successfully removed from the ticket.", view=None)
                    await interaction.channel.send(f"👤 {user.mention} was removed from the ticket by {interaction.user.mention}.")
                    
                    if log_channel:
                        embed = discord.Embed(title="👤 User Removed from Ticket", color=discord.Color.red())
                        embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
                        embed.add_field(name="Removed User", value=user.mention, inline=True)
                        embed.add_field(name="Removed By", value=interaction.user.mention, inline=True)
                        await log_channel.send(embed=embed)

            except Exception as e:
                await interaction.edit_original_response(content=f"❌ Failed to {action_text} user: `{e}`", view=None)
            
            return

        # ==========================================
        # ACTION: DELETE
        # ==========================================
        if action == "delete":
            await interaction.response.send_message(
                f"⚠️ Confirm deletion of ticket `{ticket['ticket_id']}`?",
                view=ConfirmDeleteView(ticket["ticket_id"]),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            # ==========================================
            # ACTION: STATUS
            # ==========================================
            if action == "status":
                embed = discord.Embed(
                    title=f"🎫 Ticket Information: {ticket.get('ticket_id')}",
                    color=discord.Color.blurple()
                )
                
                embed.add_field(name="Opened By", value=f"<@{ticket.get('user_id')}>", inline=True)
                
                status_text = str(ticket.get("status")).capitalize()
                embed.add_field(name="Status", value=f"`{status_text}`", inline=True)

                claimed_by = ticket.get("claimed_by")
                if claimed_by:
                    embed.add_field(name="Claimed By", value=f"<@{claimed_by}>", inline=True)
                else:
                    embed.add_field(name="Claimed By", value="`Unclaimed`", inline=True)

                created_at = ticket.get("created_at")
                if created_at:
                    if isinstance(created_at, datetime):
                        embed.add_field(name="Created At", value=f"<t:{int(created_at.timestamp())}:F>", inline=False)
                    else:
                        embed.add_field(name="Created At", value=str(created_at), inline=False)

                await interaction.followup.send(embed=embed)

            # ==========================================
            # ACTION: CLAIM
            # ==========================================
            elif action == "claim":
                if ticket.get("status") in ["closed", "deleted"]:
                    return await interaction.followup.send("⚠️ This ticket is closed! You must reopen it before claiming.", ephemeral=True)
                if ticket.get("claimed_by"):
                    return await interaction.followup.send("⚠️ Already claimed.", ephemeral=True)

                await tm.claim(ticket["ticket_id"], interaction.user.id)
                claimed_category = interaction.guild.get_channel(CAT_CLAIMED)
                if claimed_category:
                    await interaction.channel.edit(category=claimed_category)

                await interaction.followup.send(f"🎟️ Ticket claimed by {interaction.user.mention}.")

            # ==========================================
            # ACTION: CLOSE
            # ==========================================
            elif action == "close":
                if ticket.get("status") in ["closed", "deleted"]:
                    return await interaction.followup.send("⚠️ Already closed.", ephemeral=True)

                await tm.close(ticket["ticket_id"], interaction.user.id)
                await tm.tickets.update_one({"ticket_id": ticket["ticket_id"]}, {"$set": {"claimed_by": None}})

                overwrites = interaction.channel.overwrites
                for target in overwrites:
                    overwrites[target].update(send_messages=False)

                target = interaction.guild.get_channel(CAT_CLOSED)
                await interaction.channel.edit(
                    category=target if target else interaction.channel.category,
                    overwrites=overwrites
                )

                if is_staff:
                    await interaction.followup.send("🔒 Ticket closed and channel locked.")
                else:
                    await interaction.followup.send(
                        "🔒 **Ticket closed and channel locked.**\n\n"
                        "⚠️ *Note: You cannot reopen this ticket. However, you are free to delete the ticket if you wish by using the Delete button or `/ticket delete`*"
                    )

            # ==========================================
            # ACTION: REOPEN
            # ==========================================
            elif action == "reopen":
                await tm.tickets.update_one(
                    {"ticket_id": ticket["ticket_id"]}, 
                    {"$set": {"status": "open", "closed_at": None, "closed_by": None, "claimed_by": None}}
                )

                overwrites = interaction.channel.overwrites
                for target in overwrites:
                    if target != interaction.guild.default_role:
                        overwrites[target].update(send_messages=True)

                target = interaction.guild.get_channel(CAT_OPEN)
                await interaction.channel.edit(
                    category=target if target else interaction.channel.category,
                    overwrites=overwrites
                )

                await interaction.followup.send(f"🔓 Ticket reopened and unlocked.")

        except Exception as e:
            tb = traceback.format_exc()
            print(f"Ticket Cmd Error:\n{tb}")
            await interaction.followup.send(f"❌ **Error executing '{action}':**\n```py\n{e}\n```", ephemeral=True) 

async def setup(bot):
    await bot.add_cog(TicketCommands(bot))