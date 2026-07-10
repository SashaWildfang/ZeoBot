import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, Modal, TextInput, View
from db.database import get_connection  
from db.punishments import log_punishment

import logging

# Configure logging to show in your terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("MemberJoin")


# Level role mapping: each range maps to a single Discord role ID
LEVEL_ROLE_MAP = {
    range(0, 5): 1361677978421035180,
    range(5, 11): 1361678583713759363,
    range(11, 21): 1361678717197221968,
    range(21, 31): 1361678760327512185,
    range(31, 41): 1361679050632073398,
    range(41, 51): 1361679477700038828,
    range(51, 61): 1361680109953876049,
    range(61, 71): 1361680599672422540,
    range(71, 81): 1361680699563966605,
    range(81, 91): 1361680852064407683,
    range(91, 200): 1361681482946576504
}

PATREON_TIER_1 = 1362102163693633818
PATREON_TIER_2 = 1362502662721114245
PATREON_TIER_3 = 1362502871639396362
BOOSTER_ROLE_ID = 1360260086500561237

STAFF_ROLE_IDS = {
    1358470318087340342, 1358472557862457537, 1358472532222808126,
    1358472588430676018, 1358472511133585564, 1358472635234779207,
    1358473248534167663
}

YOUR_GUILD_ID = 1358469974552870913 # Replace if you have a specific test server ID variable 
DISCORD_MEMBER_ROLE_ID = 1358469854725931038
BOT_LOG_CHANNEL_ID = 1360344042705256660
VERIFICATION_CHANNEL_ID = 1358486077916057691
ACTIVITY_CHANNEL_ID = 1358485536511234164
WELCOME_CHANNEL_ID = 1358486077916057691
REMINDER_CHANNEL_ID = 1487886250114547762
RULES_CHANNEL_ID = 1383559103913267282
UNVERIFIED_ROLE_ID = 1358469817191104716
ADMIN_CHANNEL_ID = 1381975737808191599
NOTIFY_ID = 1485825407654559846
SFW_GENERAL = 1358452494660796448
NSFW_ROLE_ID = 1358469974552870913  
PUNISHMENT_LOG_ID = 1358486649360748665
PATREON_INFO_CHANNEL_ID = 1362502211220930581

# Pre-computed set of all level role IDs for cleanup logic
LEVEL_ROLE_IDS = set(LEVEL_ROLE_MAP[r] for r in LEVEL_ROLE_MAP)

# JSON data files for lightweight persistence (deny/pending/reminder tracking)
REMINDER_DATA_FILE = "unverified_reminder.json"
DENIED_USERS_FILE = "denied_users.json"
PENDING_VERIFICATIONS_FILE = "pending_verifications.json"

# Timezones
UTC_TZ = ZoneInfo("UTC")

def load_json_file(filename: str) -> Dict[str, Any]:
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump({}, f)
    with open(filename, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json_file(data: Dict[str, Any], filename: str) -> None:
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def get_level_role_id_for_level(level: int) -> Optional[int]:
    for level_range, role_id in LEVEL_ROLE_MAP.items():
        if level in level_range:
            return role_id
    return None

def is_staff(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def update_embed_status(embed: discord.Embed, new_status: str):
    """Helper function to neatly replace the pending status or append it if not found."""
    if "**Status:** ⏳ Pending" in embed.description:
        embed.description = embed.description.replace("**Status:** ⏳ Pending", new_status)
    else:
        embed.description += f"\n\n{new_status}"

# Accept Verification (Admin "Accept" Button Handler)
async def accept_verification(bot: commands.Bot, interaction: discord.Interaction, member_id: int):
    if not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

    guild: discord.Guild = interaction.guild
    member: Optional[discord.Member] = guild.get_member(member_id) if guild else None
    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID) if guild else None
    discord_member_role = guild.get_role(DISCORD_MEMBER_ROLE_ID) if guild else None
    welcome_channel = guild.get_channel(SFW_GENERAL) if guild else None
    bot_log_channel = bot.get_channel(BOT_LOG_CHANNEL_ID)
    
    # We use Discord's native Unix timestamp formatting so it adapts to the user's timezone!
    now_ts = int(datetime.now().timestamp())
    dynamic_time_str = f"<t:{now_ts}:d> @ <t:{now_ts}:t>"

    if not (guild and member):
        if interaction.message:
            try:
                original_embed = interaction.message.embeds[0]
                original_embed.color = discord.Color.red()
                new_status = (
                    f"**Status:** ❌ Failed (Member not found) by {interaction.user.mention} "
                    f"at {dynamic_time_str}"
                )
                update_embed_status(original_embed, new_status)
                await interaction.message.edit(embed=original_embed, view=None)
            except Exception:
                pass
        try:
            await interaction.followup.send("❌ Error: Member not found. They might have left the server.", ephemeral=True)
        except Exception:
            pass
        return

    if not unverified_role:
        if interaction.message:
            try:
                original_embed = interaction.message.embeds[0]
                original_embed.color = discord.Color.red()
                new_status = (
                    f"**Status:** ❌ Failed (Unverified role not found) by {interaction.user.mention} "
                    f"at {dynamic_time_str}"
                )
                update_embed_status(original_embed, new_status)
                await interaction.message.edit(embed=original_embed, view=None)
            except Exception:
                pass
        try:
            await interaction.followup.send("❌ Error: Unverified role not found. Please check bot configuration.", ephemeral=True)
        except Exception:
            pass
        return

    if not discord_member_role:
        if interaction.message:
            try:
                original_embed = interaction.message.embeds[0]
                original_embed.color = discord.Color.red()
                new_status = (
                    f"**Status:** ❌ Failed (Discord Member role not found) by {interaction.user.mention} "
                    f"at {dynamic_time_str}"
                )
                update_embed_status(original_embed, new_status)
                await interaction.message.edit(embed=original_embed, view=None)
            except Exception:
                pass
        try:
            await interaction.followup.send("❌ Error: Discord Member role not found. Please check bot configuration.", ephemeral=True)
        except Exception:
            pass
        return

    # Database: ensure user doc exists and mark verifiedBy (camelCase)
    try:
        db = get_connection()

        applications_col = db["join_applications"]
        await applications_col.update_one({"discordId": str(member_id)}, {"$set": {"status": "approved"}})

        users = db["users"]
        now = datetime.utcnow()
        result = await users.update_one(
            {"discordId": member.id},
            {
                "$setOnInsert": {
                    "discordId": member.id,
                    "balance": 0,
                    "level": 1,
                    "xp": 0,
                    "xpNeeded": 100,
                    "streak": 0,
                    "lastDaily": None,
                    "lastMessage": None,
                    "xpMultiplier": 1.0,
                    "multiplier": 1.0,
                    "createdAt": now,
                    "msgCount": 0,
                    "nsfwVerifiedBy": None
                },
                "$set": {
                    "updatedAt": now,
                    "verifiedBy": interaction.user.id
                }
            },
            upsert=True
        )

    except Exception as e:
        if interaction.message:
            try:
                original_embed = interaction.message.embeds[0]
                original_embed.color = discord.Color.red()
                new_status = (
                    f"**Status:** ❌ Failed (DB Error) by {interaction.user.mention} "
                    f"at {dynamic_time_str} — {e}"
                )
                update_embed_status(original_embed, new_status)
                await interaction.message.edit(embed=original_embed, view=None)
            except Exception:
                pass
        try:
            await interaction.followup.send(f"❌ An error occurred during database update: {e}", ephemeral=True)
        except Exception:
            pass
        return

    if unverified_role in member.roles:
        try:
            await member.remove_roles(unverified_role, reason=f"Verified by {interaction.user.name}")
        except discord.Forbidden:
            try:
                await interaction.followup.send("❌ I don't have permissions to remove the unverified role.", ephemeral=True)
            except Exception:
                pass
            return
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ An error occurred while removing the unverified role: {e}", ephemeral=True)
            except Exception:
                pass
            return
        
    # Update original admin embed as verified & remove buttons
    if interaction.message:
        try:
            original_embed = interaction.message.embeds[0]
            original_embed.color = discord.Color.green()
            new_status = f"**Status:** ✅ Verified by {interaction.user.mention} at {dynamic_time_str}"
            update_embed_status(original_embed, new_status)
            await interaction.message.edit(embed=original_embed, view=None)
        except Exception:
            pass

    # Confirm to clicker
    try:
        await interaction.followup.send(f"Successfully verified {member.mention}!", ephemeral=True)
    except Exception:
        pass

    # Remove from pending verifications JSON
    pending_data = load_json_file(PENDING_VERIFICATIONS_FILE)

    if str(member.id) in pending_data:
        del pending_data[str(member.id)]
        save_json_file(pending_data, PENDING_VERIFICATIONS_FILE)

    # Fetch level and map to role
    level = 1
    try:
        db = get_connection()
        users = db["users"]
        doc = await users.find_one({"discordId": member.id}, {"level": 1})
        if doc and "level" in doc:
            level = int(doc["level"])
    except Exception as e:
        print(f"❌ Failed to fetch level during verify: {e}")

    level_role_id = get_level_role_id_for_level(level)
    level_role = guild.get_role(level_role_id) if level_role_id else None
    actions = []

    # Add Discord Member role
    if discord_member_role and discord_member_role not in member.roles:
        try:
            await member.add_roles(discord_member_role, reason="Assigned Discord Member role on verify")
            actions.append(f"added role ({discord_member_role.name})")
        except discord.Forbidden:
            print(f"Missing permissions to add Discord Member role {discord_member_role.name}")
            actions.append(f"failed to add role ({discord_member_role.name}) due to missing permissions")
        except Exception as e:
            print(f"Failed to assign Discord Member role: {e}")
            actions.append(f"failed to add role ({discord_member_role.name}) due to error: {e}")

    # Clean any old level roles
    current_level_roles = [r for r in member.roles if r.id in LEVEL_ROLE_IDS]
    if current_level_roles:
        try:
            await member.remove_roles(*current_level_roles, reason="Cleaning up old level role(s)")
            actions.append(f"removed old level role(s): {', '.join([r.name for r in current_level_roles])}")
        except Exception as e:
            print(f"Failed to remove old level roles: {e}")
            actions.append(f"failed to remove old level role(s) due to error: {e}")

    # Add correct level role
    if level_role and level_role not in member.roles:
        try:
            await member.add_roles(level_role, reason="Assigned level role on verify")
            actions.append(f"added level role ({level_role.name})")
        except discord.Forbidden:
            print(f"Missing permissions to add level role {level_role.name}")
            actions.append(f"failed to add level role ({level_role.name}) due to missing permissions")
        except Exception as e:
            print(f"Failed to assign level role: {e}")
            actions.append(f"failed to add level role ({level_role.name}) due to error: {e}")

    # Summarize role changes to the staff clicker
    try:
        if actions:
            await interaction.followup.send(f"Role updates for {member.mention}:\n- " + "\n- ".join(actions), ephemeral=True)
        else:
            await interaction.followup.send(f"No specific role changes for {member.mention}.", ephemeral=True)
    except Exception:
        pass

    # Log to bot-log channel
    if bot_log_channel:
        embed = discord.Embed(
            title="Verification Logged",
            description=f"{interaction.user.mention} verified {member.mention} ({member.name}#{member.discriminator})",
            color=discord.Color.green(),
            timestamp=datetime.now(UTC_TZ)
        )
        embed.set_footer(text=f"User ID: {member.id}")
        try:
            await bot_log_channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to send verification log: {e}")

    # Public welcome ping to SFW general
    if welcome_channel:
        gid = guild.id
        embed = discord.Embed(
            title="🌸 A new bud has sprouted in Kitty Kingdom!",
            description=(
                f"Say hi to {member.mention}, our newest member!\n\n"
                f"🌿 **[Server Announcements](https://discord.com/channels/{gid}/1358485236073238528)**\n"
                f"📜 **[Rules](https://discord.com/channels/{gid}/1358485180146384906)**\n"
                f"🎨 **[Role Selection](https://discord.com/channels/{gid}/1358485281904267622)**\n"
                f"📘 **[Server Guide](https://discord.com/channels/{gid}/1358485363412176906)**\n"
                f"💎 **[Booster Perks](https://discord.com/channels/{gid}/1358485493020496004)**\n"
                f"🥀 **[NSFW Verification](https://discord.com/channels/{gid}/1358485673991999721)**\n"
                f"🦋 **[Level Info](https://discord.com/channels/{gid}/1358485327030784071)**\n"
                f"💖 **[Become a Patron](https://discord.com/channels/{gid}/{PATREON_INFO_CHANNEL_ID})**\n\n"
                f"We hope you enjoy your time in **Kitty Kingdom**! ✨"
            ),
            color=discord.Color.from_rgb(183, 228, 199), # Soft Spring Green
            timestamp=datetime.now(UTC_TZ)
        )
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass
        embed.set_footer(text="Chat with any staff member if you have any questions or concerns")
        try:
            await welcome_channel.send(content=f"<@&1363972389188276264>", embed=embed)
        except Exception as e:
            print(f"Failed to send public welcome: {e}")

# Deny Modal
class ConfirmDenyModal(Modal, title="Confirm Denial"):
    def __init__(self, bot, member_id: int):
        super().__init__()
        self.bot = bot
        self.member_id = member_id

        # "confirm" input
        self.add_item(TextInput(label="Type 'confirm' to deny:", required=True, max_length=10, custom_id="deny_confirm_input"))

        # reason input
        self.deny_reason_input = TextInput(
            label="Reason for denial:",
            placeholder="Provide a reason for the application being denied",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500,
            custom_id="deny_reason_input"
        )

        self.add_item(self.deny_reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.children[0].value.lower() != 'confirm':
            await interaction.response.send_message("Confirmation failed. Please type 'confirm' exactly", ephemeral=True)
            return

        deny_reason = self.deny_reason_input.value
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
        welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
        
        if member and unverified_role and welcome_channel:
            try:
                # Add user to denied list (lockout for 1 day)
                denied_data = load_json_file(DENIED_USERS_FILE)
                denied_until = datetime.now(UTC_TZ) + timedelta(days=1)
                denied_data[str(member.id)] = denied_until.isoformat()
                save_json_file(denied_data, DENIED_USERS_FILE)

                # Remove user from pending verifications
                pending_data = load_json_file(PENDING_VERIFICATIONS_FILE)
                if str(member.id) in pending_data:
                    del pending_data[str(member.id)]
                    save_json_file(pending_data, PENDING_VERIFICATIONS_FILE)

                # --- NEW CODE: UPDATE MONGODB APP STATUS ---
                try:
                    db = get_connection()
                    applications_col = db["join_applications"]
                    await applications_col.update_one(
                        {"discordId": str(self.member_id)},
                        {"$set": {"status": "denied"}}
                    )
                except Exception as e:
                    print(f"Failed to update application status to denied: {e}") 
                # -------------------------------------------

                await interaction.response.send_message(
                    f"Successfully denied {member.mention}. They have been notified to re-verify in 1d",
                    ephemeral=True
                )

                # Edit original admin embed
                if interaction.message:
                    original_embed = interaction.message.embeds[0]
                    original_embed.color = discord.Color.red()
                    unix_re_submit_timestamp = int(denied_until.timestamp())
                    
                    now_ts = int(datetime.now().timestamp())
                    dynamic_time_str = f"<t:{now_ts}:d> @ <t:{now_ts}:t>"
                    
                    new_status = (
                        f"**Status:** 🚫 Denied by {interaction.user.mention} at {dynamic_time_str}\n"
                        f"**Reason:** {deny_reason}\n"
                        f"**Re-submit allowed:** <t:{unix_re_submit_timestamp}:F> (<t:{unix_re_submit_timestamp}:R>)"
                    )
                    update_embed_status(original_embed, new_status)
                    
                    try:
                        await interaction.message.edit(embed=original_embed, view=None)
                    except Exception:
                        pass

                # Public ping with reason
                deny_ping_embed = discord.Embed(
                    title="🚫 Verification Denied",
                    description=(
                        f"Your verification form was denied.\n\n"
                        f"**Reason:** {deny_reason}\n\n"
                        f"Please review the <#{RULES_CHANNEL_ID}> and submit a new form on "
                        f"<t:{int(denied_until.timestamp())}:F> (<t:{int(denied_until.timestamp())}:R>). "
                        "Thank you for your patience"
                    ),
                    color=discord.Color.red(),
                    timestamp=datetime.now(UTC_TZ)
                )
                await welcome_channel.send(content=f"{member.mention}, please see below:", embed=deny_ping_embed)

            except discord.Forbidden:
                await interaction.followup.send("I don't have permissions to ping in the welcome channel.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"An error occurred during denial: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("User, role, or welcome channel not found.", ephemeral=True)

class BanReasonSelect(discord.ui.Select):
    def __init__(self, bot, member_id: int):
        self.bot = bot
        self.member_id = member_id
        options = [
            discord.SelectOption(label="Raider / Troller", emoji="⚔️", description="Intent to disrupt the server."),
            discord.SelectOption(label="Other / Custom", emoji="📝", description="Provide a manual reason.")
        ]
        super().__init__(placeholder="Choose a ban reason...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        reason = self.values[0]
        if reason == "Other / Custom":
            await interaction.response.send_modal(BanConfirmModal(self.bot, self.member_id))
        else:
            await interaction.response.send_modal(BanConfirmModal(self.bot, self.member_id, preset_reason=reason))

class BanDropdownView(discord.ui.View):
    def __init__(self, bot, member_id: int):
        super().__init__(timeout=60)
        self.add_item(BanReasonSelect(bot, member_id))

class BanConfirmModal(Modal, title="Confirm Permanent Ban"):
    def __init__(self, bot, member_id: int, preset_reason: str = None):
        super().__init__()
        self.bot = bot
        self.member_id = member_id

        self.confirm_input = TextInput(
            label="Type 'BAN' to confirm:",
            placeholder="BAN",
            required=True,
            max_length=3
        )
        self.add_item(self.confirm_input)

        self.reason_input = TextInput(
            label="Reason for Ban:",
            default=preset_reason if preset_reason else "",
            placeholder="e.g., Underage, Raider, etc.",
            required=True,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm_input.value.upper() != "BAN":
            return await interaction.response.send_message("❌ Action cancelled. You must type 'BAN' to proceed.", ephemeral=True)

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        user = member or await self.bot.fetch_user(self.member_id)
        reason = self.reason_input.value

        if member and any(role.id in STAFF_ROLE_IDS for role in member.roles):
            if interaction.user.id != guild.owner_id:
                return await interaction.response.send_message("⚠️ You cannot ban other staff members.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        try:
            punishment_id = await asyncio.wait_for(
                log_punishment(
                    user_id=user.id,
                    issuer_id=interaction.user.id,
                    action="ban",
                    reason=f"[Join Form] {reason}",
                    duration=None,
                    extra_info="Banned via Verification System"
                ),
                timeout=5.0
            )
        except Exception as e:
            punishment_id = "DB_ERROR"
            print(f"⚠️ Verification Ban Log Error: {e}")

        dm_sent = False
        try:
            ban_appeal_link = "https://forms.gle/AgbY3XDFFVmVTjab9"
            await user.send(
                f"⚠️ You have been **permanently banned** from **{guild.name}**.\n\n"
                f"**Reason:** {reason}\n"
                f"**Punishment ID:** `{punishment_id}`\n\n"
                f"If you wish to appeal, use this link: {ban_appeal_link}"
            )
            dm_sent = True
        except: pass

        try:
            await guild.ban(user, reason=f"Banned by {interaction.user}: {reason}", delete_message_days=1)
            
            if interaction.message and len(interaction.message.embeds) > 0:
                embed_orig = interaction.message.embeds[0]
                if "🔨 **BANNED**" not in embed_orig.description:
                    embed_orig.color = discord.Color.dark_red()
                    new_status = (
                        f"**Status:** 🔨 **BANNED** by {interaction.user.mention}\n"
                        f"**Reason:** {reason}\n"
                        f"**ID:** `{punishment_id}`"
                    )
                    update_embed_status(embed_orig, new_status)
                    await interaction.message.edit(embed=embed_orig, view=None)

            log_embed = discord.Embed(
                title="⚠️ User Banned",
                color=discord.Color.dark_red(),
                timestamp=datetime.now(UTC_TZ)
            )
            log_embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
            log_embed.add_field(name="Staff", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
            log_embed.add_field(name="Reason", value=reason, inline=False)
            log_embed.add_field(name="Punishment ID", value=f"`{punishment_id}`", inline=False)
            log_embed.add_field(name="DM Sent", value="Yes" if dm_sent else "No", inline=True)
            log_embed.set_footer(text="Permanent Ban Issued via Verification")
            
            try:
                log_embed.set_thumbnail(url=user.display_avatar.url)
            except:
                pass

            punish_log = self.bot.get_channel(PUNISHMENT_LOG_ID) 
            if punish_log:
                await punish_log.send(embed=log_embed)

            await interaction.followup.send(f"Successfully banned {user.name} (DM Sent: {dm_sent}).", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to execute ban: {e}", ephemeral=True)

class VerificationAdminView(View):
    def __init__(self, bot, member_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.member_id = member_id
        
        # Manually set unique custom IDs using the member's ID
        self.accept_button.custom_id = f"v_acc_{member_id}"
        self.deny_button.custom_id = f"v_deny_{member_id}"
        self.ban_button.custom_id = f"v_ban_{member_id}"

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)
        await accept_verification(self.bot, interaction, self.member_id)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji="❌")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("You don't have permission.", ephemeral=True)
        await interaction.response.send_modal(ConfirmDenyModal(self.bot, self.member_id))

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user): 
            return await interaction.response.send_message("⚠️ You lack permission.", ephemeral=True)
        
        await interaction.response.send_message(
            content=f"### 🔨 Ban Process: {self.member_id}\nSelect a reason:",
            view=BanDropdownView(self.bot, self.member_id),
            ephemeral=True
        )

# User Verification Modal
class VerificationModal(Modal, title="Kitty Kingdom Verification Form"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    age_dob = TextInput(
        label="1. Full DOB (MM/DD/YYYY)",
        placeholder="e.g. 01/01/2005",
        required=True,
        max_length=50
    )
    how_found = TextInput(
        label="2. How did you find the server?",
        placeholder="e.g., Disboard, friend invite",
        required=True,
        max_length=50
    )
    fursona_and_looking_for = TextInput(
        label="3. Fursona & Reason for Joining",
        placeholder="What is your fursona and why do you want to join?",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    rules_and_password = TextInput(
        label="4. Password",
        placeholder="Provide password found in Rules",
        required=True,
        max_length=100
    )
    bio = TextInput(
        label="5. Tell us a little about yourself",
        placeholder="e.g., I'm a student who loves cats and sci-fi.",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
            # 1. DEFER IMMEDIATELY
            await interaction.response.defer(ephemeral=True)

            member_id_str = str(interaction.user.id)

            # 1.5 CHECK IF ALREADY PENDING
            pending_data = load_json_file(PENDING_VERIFICATIONS_FILE)
            if member_id_str in pending_data:
                return await interaction.followup.send(
                    "You already have a pending verification form! Please wait for staff to review your current submission.",
                    ephemeral=True
                )

            # 2. CHECK DENIED LOCKOUT
            denied_data = load_json_file(DENIED_USERS_FILE)
            if member_id_str in denied_data:
                denied_until_str = denied_data[member_id_str]
                try:
                    denied_until = datetime.fromisoformat(denied_until_str)
                    if denied_until.tzinfo is None:
                        denied_until = denied_until.replace(tzinfo=UTC_TZ)
                    
                    if datetime.now(UTC_TZ) < denied_until:
                        remaining_time = denied_until - datetime.now(UTC_TZ)
                        hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                        minutes, _ = divmod(remainder, 60)
                        
                        return await interaction.followup.send(
                            f"You were recently denied. Please wait {int(hours)}h {int(minutes)}m before submitting again.",
                            ephemeral=True
                        )
                    else:
                        del denied_data[member_id_str]
                        save_json_file(denied_data, DENIED_USERS_FILE)
                except ValueError:
                    del denied_data[member_id_str]
                    save_json_file(denied_data, DENIED_USERS_FILE)

            # =======================================================
            # 2.0 FORCE MM/DD/YYYY FORMAT AND CALCULATE AGE
            # =======================================================
            age_input = self.age_dob.value.strip()
            date_match = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', age_input)
            
            if not date_match:
                return await interaction.followup.send(
                    "⚠️ **Verification Failed:** You must provide your Date of Birth in the exact **MM/DD/YYYY** format.\n\n"
                    "Example: `01/01/2005`\n"
                    "Please click 'Start Verification' again and fix your answer.",
                    ephemeral=True
                )
            
            try:
                month = int(date_match.group(1))
                day = int(date_match.group(2))
                year = int(date_match.group(3))
                dob = datetime(year, month, day)
            except ValueError:
                return await interaction.followup.send(
                    "⚠️ **Verification Failed:** The date you entered is not a valid calendar date.\n"
                    "Please click 'Start Verification' again and provide a valid date.",
                    ephemeral=True
                )
                
            now = datetime.now(UTC_TZ)
            age = now.year - dob.year - ((now.month, now.day) < (dob.month, dob.day))
            formatted_age_dob = f"{age} years old, {dob.strftime('%m/%d/%Y')}"

            # =======================================================
            # 2.1 AUTO-KICK UNDERAGE
            # =======================================================
            if age < 18:
                deny_msg = (
                    f"Your verification was denied and you have been kicked from **{interaction.guild.name}**.\n\n"
                    f"**Reason:** Based on the Date of Birth provided ({dob.strftime('%m/%d/%Y')}), you are {age} years old.\n\n"
                    "You must be 18+ to join this server. If you believe this is a mistake, you may rejoin and try again."
                )

                dm_sent = False
                try:
                    await interaction.user.send(deny_msg)
                    dm_sent = True
                except Exception:
                    pass

                kicked = False
                try:
                    await interaction.guild.kick(interaction.user, reason=f"Auto-Kicked via Verification: Underage ({age})")
                    kicked = True
                except Exception as e:
                    print(f"Failed to kick user {interaction.user.id}: {e}")

                admin_log = self.bot.get_channel(ADMIN_CHANNEL_ID)
                if admin_log:
                    auto_kick_embed = discord.Embed(
                        title="🤖 Auto-Kicked: Underage",
                        description=f"{interaction.user.mention} (`{interaction.user.id}`) was auto-kicked during verification.",
                        color=discord.Color.red(),
                        timestamp=datetime.now(UTC_TZ)
                    )
                    auto_kick_embed.add_field(name="Reason", value=f"Underage (Calculated Age: {age})", inline=False)
                    auto_kick_embed.add_field(name="Their Input", value=self.age_dob.value, inline=False)
                    auto_kick_embed.add_field(name="Actions Taken", value=f"DM Sent: {'Yes' if dm_sent else 'No'}\nKicked: {'Yes' if kicked else 'No'}", inline=False)
                    
                    try:
                        await admin_log.send(embed=auto_kick_embed)
                    except Exception as e:
                        print(f"Failed to send auto-kick log: {e}")

                return await interaction.followup.send(
                    "Your application was denied and you have been removed from the server because you did not meet the age requirements.",
                    ephemeral=True
                )

            # 2.5 AUTO-DENY CHECK
            try:
                db = get_connection()
                globals_col = db["globals"]
                global_doc = await globals_col.find_one({})
                
                if global_doc and "serverPassword" in global_doc:
                    expected_password = global_doc["serverPassword"].lower()
                    user_input = self.rules_and_password.value.lower()
                    
                    if expected_password not in user_input:
                        denied_until = datetime.now(UTC_TZ) + timedelta(days=1)
                        denied_data = load_json_file(DENIED_USERS_FILE)
                        denied_data[member_id_str] = denied_until.isoformat()
                        save_json_file(denied_data, DENIED_USERS_FILE)
                        
                        deny_reason = "Auto denied: Incorrect password"
                        
                        admin_log = self.bot.get_channel(ADMIN_CHANNEL_ID)
                        if admin_log:
                            auto_deny_embed = discord.Embed(
                                title="🤖 Auto-Denied Verification Form",
                                description=f"Form submitted by {interaction.user.mention} ({interaction.user.id}) was auto-denied.",
                                color=discord.Color.red(),
                                timestamp=datetime.now(UTC_TZ)
                            )
                            auto_deny_embed.add_field(name="Reason", value=deny_reason, inline=False)
                            auto_deny_embed.add_field(name="Their Input", value=self.rules_and_password.value, inline=False)
                            try:
                                await admin_log.send(embed=auto_deny_embed)
                            except Exception as e:
                                print(f"Failed to send auto-deny log: {e}")

                        welcome_channel = interaction.guild.get_channel(WELCOME_CHANNEL_ID)
                        if welcome_channel:
                            deny_ping_embed = discord.Embed(
                                title="🚫 Verification Denied",
                                description=(
                                    f"Your verification form was denied.\n\n"
                                    f"**Reason:** {deny_reason}\n\n"
                                    f"Please review the <#{RULES_CHANNEL_ID}> and submit a new form on "
                                    f"<t:{int(denied_until.timestamp())}:F> (<t:{int(denied_until.timestamp())}:R>). "
                                    "Thank you for your patience"
                                ),
                                color=discord.Color.red(),
                                timestamp=datetime.now(UTC_TZ)
                            )
                            try:
                                await welcome_channel.send(content=f"{interaction.user.mention}, please see below:", embed=deny_ping_embed)
                            except Exception as e:
                                print(f"Failed to send welcome channel auto-deny ping: {e}")
                        
                        return await interaction.followup.send(
                            "Your verification form was automatically denied because of an incorrect password. You may try again in 24 hours.",
                            ephemeral=True
                        )
            except Exception as e:
                print(f"Error checking global password in DB: {e}")

            # 3. MARK AS PENDING
            pending_data = load_json_file(PENDING_VERIFICATIONS_FILE)
            pending_data[member_id_str] = datetime.now(UTC_TZ).isoformat()
            save_json_file(pending_data, PENDING_VERIFICATIONS_FILE)

            # =========================
            # 3.5 SAVE APPLICATION TO MONGODB
            # =========================
            try:
                db = get_connection()
                applications_col = db["join_applications"]
                
                application_doc = {
                    "discordId": str(interaction.user.id),
                    "ageAndDob": formatted_age_dob, 
                    "howFoundServer": self.how_found.value,
                    "fursonaAndReason": self.fursona_and_looking_for.value,
                    "rulesAndPassword": self.rules_and_password.value,
                    "bio": self.bio.value,
                    "status": "pending",
                    "submittedAt": datetime.now(UTC_TZ)
                }
                
                await applications_col.update_one(
                    {"discordId": str(interaction.user.id)}, 
                    {"$set": application_doc}, 
                    upsert=True
                )
                
            except Exception as e:
                print(f"Error saving application to MongoDB: {e}")

            # 4. SEND SUCCESS MESSAGE TO USER
            try:
                await interaction.followup.send(
                    "Your verification form has been submitted for review! Please be patient as staff will review it within 24 hours",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                print(f"Failed to send ephemeral response to user: {e}")

            # =========================
            # 5. LOG FULL APPLICATION TO ADMIN CHANNEL
            # =========================
            admin_log = self.bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_log:
                created_at = interaction.user.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC_TZ)
                
                diff = now - created_at
                days = diff.days
                years, rem = divmod(days, 365)
                months, days_left = divmod(rem, 30)

                age_parts = []
                if years > 0: age_parts.append(f"{years}y")
                if months > 0: age_parts.append(f"{months}m")
                if days_left > 0 or not age_parts: age_parts.append(f"{days_left}d")
                account_age_str = " ".join(age_parts)

                warning_flag = ""
                if days < 30:
                    warning_flag = " ⚠️ **(NEW ACCOUNT)**"

                # Adding timestamp= to the embed automatically handles localized time display in the footer!
                embed = discord.Embed(
                    title="📝 New Verification Form Submission",
                    description=(
                        f"Form submitted by {interaction.user.mention} ({interaction.user.id})\n"
                        f"**Status:** ⏳ Pending\n"
                        f"**Age:** {account_age_str}{warning_flag}"
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.now(UTC_TZ)
                )
                embed.add_field(name="1. Age/DOB", value=formatted_age_dob, inline=False)
                embed.add_field(name="2. Found Server", value=self.how_found.value, inline=False)
                embed.add_field(name="3. Fursona & Reason for Joining", value=self.fursona_and_looking_for.value, inline=False)
                embed.add_field(name="4. Password", value=self.rules_and_password.value, inline=False)
                embed.add_field(name="5. Bio", value=self.bio.value, inline=False)
                embed.set_footer(text="Submitted")
                
                try:
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)
                except Exception:
                    pass

                try:
                    await admin_log.send(embed=embed, view=VerificationAdminView(self.bot, interaction.user.id))
                except Exception as e:
                    print(f"Failed to send full admin log: {e}")

            # 6. NOTIFY STAFF IN NOTIFY CHANNEL
            notify_channel = self.bot.get_channel(1485825407654559846)
            if notify_channel:
                now_notify = datetime.now(UTC_TZ)
                created_at_notify = interaction.user.created_at
                if created_at_notify.tzinfo is None:
                    created_at_notify = created_at_notify.replace(tzinfo=UTC_TZ)
                
                diff_notify = now_notify - created_at_notify
                days_notify = diff_notify.days
                
                if days_notify >= 365:
                    age_str = f"{days_notify // 365} year(s), {days_notify % 365} day(s)"
                elif days_notify >= 30:
                    age_str = f"{days_notify // 30} month(s), {days_notify % 30} day(s)"
                else:
                    age_str = f"{days_notify} day(s)"

                warning_flag_notify = ""
                if days_notify < 30:
                    warning_flag_notify = " ⚠️ **(NEW ACCOUNT)**"

                notify_embed = discord.Embed(
                    title="📝 New Join Application Submitted",
                    description=(
                        f"A new user has submitted their verification form for review.\n\n"
                        f"👤 **User:** {interaction.user.mention}\n"
                        f"🆔 **User ID:** `{interaction.user.id}`\n"
                        f"⏳ **Account Age:** `{age_str}`{warning_flag_notify}\n"
                        f"🔗 **Action:** View full details in <#1381975737808191599>"
                    ),
                    color=discord.Color.from_rgb(255, 105, 180), 
                    timestamp=now_notify
                )
                
                notify_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                notify_embed.set_footer(text="Zeo Verification System", icon_url="https://i.imgur.com/6EhF8A4.png")
                
                try:
                    await notify_channel.send(
                        content=f"🔔 <@&1358470109965979859> **New Join Application Created!**",
                        embed=notify_embed
                    )
                except Exception as e:
                    print(f"Failed to send staff notification: {e}")

class VerificationView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Start Verification", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button_id")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        unverified_role = interaction.guild.get_role(UNVERIFIED_ROLE_ID)

        if unverified_role and unverified_role not in interaction.user.roles:
            await interaction.response.send_message("You are already verified.", ephemeral=True)
            return

        await interaction.response.send_modal(VerificationModal(self.bot))

# Member Join Cog
class MemberJoin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_reminder_data()
        self.daily_unverified_reminder.start()

    def load_reminder_data(self):
        self.reminder_data = load_json_file(REMINDER_DATA_FILE)

    def save_reminder_data(self):
        save_json_file(self.reminder_data, REMINDER_DATA_FILE)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        pending_data = load_json_file(PENDING_VERIFICATIONS_FILE)
        member_id_str = str(member.id)

        if member_id_str in pending_data:
            admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                async for message in admin_channel.history(limit=50):
                    if message.author == self.bot.user and message.embeds:
                        embed = message.embeds[0]
                        if member_id_str in embed.description or member_id_str in str(embed.footer.text):
                            try:
                                await message.delete()
                            except discord.HTTPException:
                                pass
                            break
            del pending_data[member_id_str]
            save_json_file(pending_data, PENDING_VERIFICATIONS_FILE)

        await self.bot.wait_until_ready()
        guild = member.guild

        if guild.id != YOUR_GUILD_ID:
            print(f"Member joined a guild not configured for this bot: {guild.name} ({guild.id})")
            return
        
        try:
            db = get_connection()
            users = db["users"]

            user = await users.find_one(
                {"discordId": member.id},
                {"level": 1, "verifiedBy": 1, "nsfwVerifiedBy": 1}
            )

            if user:
                level: int = int(user.get("level", 1))
                verified_by = user.get("verifiedBy")
                nsfw_verified_by = user.get("nsfwVerifiedBy")

                if verified_by:
                    actions = []
                    discord_member_role = guild.get_role(DISCORD_MEMBER_ROLE_ID)
                    if discord_member_role and discord_member_role not in member.roles:
                        try:
                            await member.add_roles(discord_member_role, reason="Rejoined - restoring verified role")
                            actions.append("added verified role")
                        except Exception as e:
                            print(f"Failed to add verified role: {e}")

                    for level_range, role_id in LEVEL_ROLE_MAP.items():
                        if level in level_range:
                            level_role = guild.get_role(role_id)
                            if level_role and level_role not in member.roles:
                                try:
                                    await member.add_roles(level_role, reason="Rejoined - restoring level role")
                                    actions.append(f"added level role ({level_role.name})")
                                except Exception as e:
                                    print(f"Failed to add level role: {e}")
                            break

                    if nsfw_verified_by:
                        nsfw_role = guild.get_role(NSFW_ROLE_ID)
                        if nsfw_role and nsfw_role not in member.roles:
                            try:
                                await member.add_roles(nsfw_role, reason="Rejoined - restoring NSFW role")
                                actions.append("added NSFW role")
                            except Exception as e:
                                print(f"Failed to add NSFW role: {e}")
                    if actions:
                        print(f"{member.name} auto-restored: {', '.join(actions)}")
                    else:
                        print(f"{member.name} already had all restored roles.")
                    return
        except Exception as e:
            print(f"Error checking verification state for {member.name}: {e}")

        unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
        if unverified_role and unverified_role not in member.roles:
            try:
                await member.add_roles(unverified_role, reason="Auto-assigned on join (unverified)")
                print(f"Assigned unverified role to {member.name}.")
            except discord.Forbidden:
                print(f"Missing permissions to assign the role to {member.name}.")
            except Exception as e:
                print(f"Failed to assign unverified role to {member.name}: {e}")
        elif not unverified_role:
            print(f"Unverified role ({UNVERIFIED_ROLE_ID}) not found in guild {guild.name}.")
        
        welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
        member_count = guild.member_count

        if welcome_channel:
            embed = discord.Embed(
                title="🎉 Welcome to Kitty Kingdom!",
                description=(
                    f"Hey {member.mention}, welcome to **Kitty Kingdom**\n"
                    f"You are member **#{member_count:,}**!\n\n"
                    f"To gain full access, please read our <#{RULES_CHANNEL_ID}> "
                    "and click **'Start Verification'** below to fill out a quick form.\n\n"
                    "**Important:** Incorrect or incomplete submissions delay approval — "
                    "staff review all forms within 24 hours"
                ),
                color=discord.Color.from_str("#3af2c1"),
                timestamp=datetime.now(UTC_TZ)
            )
            try:
                embed.set_thumbnail(url=(member.avatar or member.display_avatar).url)
            except Exception:
                pass
            
            embed.set_footer(text="Joined")

            try:
                await welcome_channel.send(embed=embed, view=VerificationView(self.bot))
            except discord.Forbidden:
                print(f"Missing permissions to send welcome message in {welcome_channel.name}.")
            except discord.HTTPException as e:
                print(f"Could not send verification embed in {welcome_channel.name}: {e}")
        else:
            print(f"Welcome channel ({WELCOME_CHANNEL_ID}) not found in guild {guild.name}.")
        
        # Join log to activity channel
        log_channel = guild.get_channel(ACTIVITY_CHANNEL_ID)
        if log_channel:
            join_time = datetime.now(UTC_TZ)
            account_created = member.created_at
            if account_created.tzinfo is None:
                account_created = account_created.replace(tzinfo=UTC_TZ)
                
            account_age_days = (join_time - account_created).days
            
            # Use dynamic timestamp tag for account creation date
            dynamic_created_str = f"<t:{int(account_created.timestamp())}:F>"

            log_embed = discord.Embed(
                title="New Member Joined",
                description=f"{member.mention} ({member.id}) has joined the server.",
                color=discord.Color.green(),
                timestamp=datetime.now(UTC_TZ)
            )

            try:
                log_embed.set_thumbnail(url=(member.avatar or member.display_avatar).url)
            except Exception:
                pass

            log_embed.add_field(name="Account Created", value=f"{dynamic_created_str} ({account_age_days} days ago)", inline=False)
            log_embed.set_footer(text="Joined")

            try:
                await log_channel.send(embed=log_embed)

            except discord.Forbidden:
                print(f"Missing permissions to send join log message in {log_channel.name}.")
            except discord.HTTPException as e:
                print(f"Failed to send join log message in {log_channel.name}: {e}")
        else:
            print(f"Activity log channel ({ACTIVITY_CHANNEL_ID}) not found in guild {guild.name}.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        pass # Merged the logic with the join listener at the start of on_member_join

    # Periodic Reminder
    @tasks.loop(hours=24)
    async def daily_unverified_reminder(self):
        guild = self.bot.get_guild(YOUR_GUILD_ID)
        if guild is None:
            return

        unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
        reminder_channel = guild.get_channel(REMINDER_CHANNEL_ID)

        if not unverified_role:
            return

        if not reminder_channel:
            return

        unverified_members = [m for m in guild.members if unverified_role in m.roles]

        if not unverified_members:
            return

        now = datetime.now(UTC_TZ)
        last_sent_str = self.reminder_data.get("last_sent_date")

        if last_sent_str:
            try:
                last_sent = datetime.fromisoformat(last_sent_str)
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=UTC_TZ)

                time_difference = now - last_sent
                if time_difference.total_seconds() < 24 * 3600:
                    return

            except ValueError as e:
                print(f"Error parsing last sent date '{last_sent_str}': {e}. Resetting last_sent_date.")
                self.reminder_data["last_sent_date"] = None
                self.save_reminder_data()
            except Exception as e:
                print(f"Unexpected error comparing last_sent_date: {e}. Resetting last_sent_date.")
                self.reminder_data["last_sent_date"] = None
                self.save_reminder_data()

        embed = discord.Embed(
            title="🔔 Verification Reminder",
            description=(
                f"{unverified_role.mention}, this is a reminder to complete your verification!\n\n"
                "Please click **'Start Verification'** below to fill out the form.\n\n"
                f"**Important:** Failure to complete the form may result in removal from the server. "
                f"You can find the rules in <#{RULES_CHANNEL_ID}>."
            ),
            color=discord.Color.from_str("#f23a3a")
        )

        try:
            await reminder_channel.send(content=unverified_role.mention, embed=embed, view=VerificationView(self.bot))
            self.reminder_data["last_sent_date"] = now.isoformat()
            self.save_reminder_data()
        except discord.Forbidden:
            print(f"Missing permissions to send reminder message in {reminder_channel.name}.")
        except discord.HTTPException as e:
            print(f"Failed to send unverified reminder message: {e}")

    @daily_unverified_reminder.before_loop
    async def before_daily_unverified_reminder(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    cog = MemberJoin(bot)
    await bot.add_cog(cog)
    bot.add_view(VerificationView(bot))