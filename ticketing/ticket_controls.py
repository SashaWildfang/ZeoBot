import discord
import asyncio
import zipfile
from discord.ui import View, button
from discord import ButtonStyle
from db.database import get_connection
from ticketing.ticket_manager import TicketManager
from datetime import datetime
import pytz
import os
import html
import aiohttp
from pathlib import Path
import shutil
import traceback

# ==========================================================
# STAFF ROLES & CHANNELS
# ==========================================================
STAFF_ROLES = {
    1358472557862457537,
    1358470109965979859,
    1358472532222808126,
    1358472588430676018,
    1358472511133585564,
    1358472635234779207,
    1416866395366359193,
    1431581220386373712,
    1358473248534167663
}

TRANSCRIPT_LOG_CHANNEL_ID = 1445923851178610718
BOT_LOG_CHANNEL_ID = 1360344042705256660
CAT_OPEN = 1362459990245245151
CAT_CLAIMED = 1362461644768411758
CAT_CLOSED = 1448247633574363237

# ==========================================================
# LOGGING HELPER FUNCTION
# ==========================================================
async def log_ticket_action(guild: discord.Guild, action: str, ticket: dict, user: discord.Member, color: discord.Color, channel_name: str = None):
    """Generates and sends an embed to the bot-logs channel for any ticket action."""
    log_channel = guild.get_channel(BOT_LOG_CHANNEL_ID)
    if not log_channel:
        return

    ticket_id = ticket.get("ticket_id", "UNKNOWN")
    
    # Safely handle missing or differently named type fields
    raw_type = str(ticket.get("type", ticket.get("ticket_type", "general")))
    display_type = raw_type.replace("_", " ").title()

    # Channel name resolution
    if not channel_name:
        chan_id = int(ticket.get("channel_id", 0))
        chan = guild.get_channel(chan_id)
        if chan:
            channel_name = chan.name
        else:
            # Reconstruct if the channel was already deleted
            if raw_type == "support": prefix = "sup"
            elif raw_type == "nsfw": prefix = "nsfw"
            elif raw_type == "staff-application": prefix = "staff"
            else: prefix = "ticket"
            
            user_id_val = int(ticket.get("user_id", 0))
            member = guild.get_member(user_id_val)
            clean_name = member.name.lower().replace(" ", "-") if member else str(user_id_val)
            channel_name = f"{prefix}-{clean_name}"

    embed = discord.Embed(
        title=f"🎟️ Ticket Action: {action.upper()}",
        color=color,
        timestamp=datetime.now(pytz.utc)
    )
    embed.add_field(name="Channel", value=f"`{channel_name}`", inline=True)
    embed.add_field(name="Database ID", value=f"`{ticket_id}`", inline=True)
    embed.add_field(name="Ticket Type", value=f"{display_type} (`{raw_type}`)", inline=False)
    embed.add_field(name="Action By", value=f"{user.mention} (`{user.id}`)", inline=False)

    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to log ticket action: {e}")

# ==========================================================
# CSS (written into ZIP)
# ==========================================================
CSS_CONTENT = """/* Discord Ticket Transcript CSS */

body {
    background-color: #18191c;
    color: #e3e3e3;
    font-family: "Segoe UI", Tahoma, sans-serif;
    padding: 25px;
}

h1 {
    color: #ff8b3d;
    font-size: 28px;
    margin-bottom: 20px;
}

.meta-box, .participants-box {
    background: #202225;
    padding: 14px 18px;
    border-radius: 8px;
    border-left: 4px solid #ff8b3d;
    margin-bottom: 20px;
}

.msg {
    display: flex;
    gap: 14px;
    background: #2a2d31;
    padding: 14px;
    border-radius: 12px;
    margin-bottom: 14px;
    border-left: 4px solid #ff8b3d;
}

.avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
}

.msg-content { flex: 1; }

.author {
    font-size: 16px;
    font-weight: bold;
    color: #ff8b3d;
}

.staff-badge {
    background-color: #ff8b3d;
    color: black;
    padding: 2px 6px;
    border-radius: 4px;
    margin-left: 8px;
    font-size: 11px;
    font-weight: 700;
}

.userid {
    font-size: 12px;
    color: #bdbdbd;
}

.timestamp {
    font-size: 12px;
    color: #aaaaaa;
}

.content {
    margin-top: 6px;
    white-space: pre-wrap;
}

.embed-box {
    background: #232529;
    padding: 10px 12px;
    border-radius: 6px;
    border-left: 4px solid #ff8b3d;
    margin-top: 10px;
}

.embed-title { font-weight: bold; color: #ff8b3d; }
.embed-field { margin-top: 5px; }

.embed-image, .embed-thumb {
    margin-top: 8px;
    max-width: 300px;
    border-radius: 6px;
}

.button-row {
    margin-top: 10px;
    padding: 8px;
    background: #232529;
    border-radius: 6px;
    border-left: 4px solid #ff8b3d;
    font-size: 14px;
}

.attachment a { color: #4aa3ff; }

.attachment-preview {
    max-width: 450px;
    margin-top: 6px;
    border-radius: 8px;
}
"""

# ==========================================================
# TIME FORMAT
# ==========================================================
def format_est(dt: datetime):
    est = pytz.timezone("US/Eastern")
    return dt.astimezone(est).strftime("%m/%d/%Y • %I:%M %p")

# ==========================================================
# HTML BUILDER
# ==========================================================
def build_html(messages, ticket_id, opener, deleter, participants):
    created_ts = format_est(messages[0]["created_at"])

    participants_html = "<br>".join(
        f"• <b>{html.escape(name)}</b> — {uid}"
        for name, uid in sorted(participants)
    )

    out = [f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Transcript {ticket_id}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>

<h1>Transcript — #{ticket_id} ({created_ts})</h1>

<div class="meta-box">
<b>Opened by:</b> {opener}<br>
<b>Deleted by:</b> {deleter}<br>
<b>Total Messages:</b> {len(messages)}
</div>

<div class="participants-box">
<b>Participants:</b><br>
{participants_html}
</div>
"""]

    for msg in messages:
        author = html.escape(msg["author_name"])
        uid = msg["author_id"]
        ts = format_est(msg["created_at"])
        avatar = msg["avatar"]
        content = html.escape(msg.get("content", "") or "")
        is_staff = msg["is_staff"]
        staff_tag = '<span class="staff-badge">STAFF</span>' if is_staff else ""

        out.append(f"""
<div class="msg">
    <img src="avatars/{avatar}" class="avatar">
    <div class="msg-content">
        <div class="author">{author} {staff_tag}</div>
        <div class="userid">User ID: {uid}</div>
        <div class="timestamp">{ts}</div>
        <div class="content">{content}</div>
""")

        if msg.get("buttons"):
            out.append(
                f'<div class="button-row">Buttons: {", ".join(msg["buttons"])}</div>'
            )

        for emb in msg["embeds"]:
            out.append('<div class="embed-box">')

            if emb["title"]:
                out.append(f'<div class="embed-title">{html.escape(emb["title"])}</div>')

            if emb["description"]:
                out.append(f'<div class="embed-desc">{html.escape(emb["description"])}</div>')

            for field in emb["fields"]:
                out.append(
                    f'<div class="embed-field"><b>{html.escape(field["name"])}:</b> {html.escape(field["value"])}</div>'
                )

            if emb.get("thumbnail"):
                out.append(f'<img src="{emb["thumbnail"]}" class="embed-thumb">')

            if emb.get("image"):
                out.append(f'<img src="{emb["image"]}" class="embed-image">')

            out.append("</div>")

        for fp in msg["attachments"]:
            rel = "attachments/" + fp.split("attachments/")[1]
            fn = os.path.basename(fp)

            out.append(f'<div class="attachment">📎 <a href="{rel}">{fn}</a>')

            if fn.lower().endswith(("png", "jpg", "jpeg", "gif", "webp")):
                out.append(f'<br><img src="{rel}" class="attachment-preview">')

            out.append("</div>")

        out.append("</div></div>")

    out.append("</body></html>")
    return "\n".join(out)

# ==========================================================
# DOWNLOAD IMAGE
# ==========================================================
async def download_image(url: str, dest: Path):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.read()
                    dest.write_bytes(data)
                    return True
    except:
        pass
    return False

# ==========================================================
# CONFIRM DELETE VIEW
# ==========================================================
class ConfirmDeleteView(View):
    def __init__(self, ticket_id):
        super().__init__(timeout=20)
        self.ticket_id = ticket_id

    @staticmethod
    def clean_filename(name: str) -> str:
        for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            name = name.replace(ch, "_")
        return name.strip()

    @button(label="✅ Confirm Delete", style=ButtonStyle.red, custom_id="ticket_confirm_delete")
    async def confirm(self, interaction: discord.Interaction, btn):
        
        # Disable buttons and show generating status
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(
            content="⏳ **Generating Transcript & Deleting Channel...**\n*Please wait, this may take a moment.*", 
            view=self
        )

        try:
            guild = interaction.guild
            channel = interaction.channel
            chan_name = channel.name # Save the name before it gets deleted!

            tm = TicketManager(get_connection())
            ticket = await tm.get_by_channel(channel.id)

            if not ticket:
                return await interaction.followup.send("❌ Ticket not found in DB.", ephemeral=True)

            # --- AUTHORIZATION CHECK ---
            is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
            is_creator = interaction.user.id == int(ticket["user_id"])

            if not (is_staff or is_creator):
                return await interaction.followup.send("⛔ You do not have permission to delete this ticket.", ephemeral=True)
            # -------------------------------

            opener_id = int(ticket["user_id"])
            opener_member = guild.get_member(opener_id)
            opener_name = opener_member.display_name if opener_member else f"Unknown ({opener_id})"

            # ==================================================
            # DIRECTORY SETUP
            # ==================================================
            folder = Path(f"transcripts/{self.ticket_id}")
            avatars_folder = folder / "avatars"
            attachments_root = folder / "attachments"
            embeds_folder = folder / "embeds"

            avatars_folder.mkdir(parents=True, exist_ok=True)
            attachments_root.mkdir(parents=True, exist_ok=True)
            embeds_folder.mkdir(parents=True, exist_ok=True)

            messages = []
            participants = set()

            total_attachments = 0
            total_embeds = 0
            total_buttons = 0
            
            # Flag to track if any real user sent a message
            has_user_messages = False

            # ==================================================
            # SCRAPE CHANNEL
            # ==================================================
            async for msg in channel.history(limit=None, oldest_first=True):
                
                # Check if the message is from a real user
                if not msg.author.bot:
                    has_user_messages = True

                participants.add((msg.author.display_name, msg.author.id))

                # Save avatar
                avatar_file = f"{msg.author.id}.png"
                try:
                    bytes_ = await msg.author.display_avatar.replace(size=128).read()
                    (avatars_folder / avatar_file).write_bytes(bytes_)
                except:
                    pass

                # Buttons
                button_labels = []
                if msg.components:
                    for row in msg.components:
                        for comp in row.children:
                            button_labels.append(comp.label)
                            total_buttons += 1

                # Attachments
                user_folder = attachments_root / self.clean_filename(msg.author.display_name)
                user_folder.mkdir(exist_ok=True)

                saved_paths = []
                for att in msg.attachments:
                    fpath = user_folder / att.filename
                    fpath.write_bytes(await att.read())
                    saved_paths.append(str(fpath))
                    total_attachments += 1

                # Embeds
                embed_data = []
                for emb in msg.embeds:
                    ed = {
                        "title": emb.title or "",
                        "description": emb.description or "",
                        "fields": [],
                        "thumbnail": None,
                        "image": None
                    }

                    for field in emb.fields:
                        ed["fields"].append({"name": field.name, "value": field.value})

                    # Thumbnail
                    if emb.thumbnail and emb.thumbnail.url:
                        thumb = embeds_folder / f"{msg.id}_thumb.png"
                        if await download_image(emb.thumbnail.url, thumb):
                            ed["thumbnail"] = f"embeds/{thumb.name}"

                    # Image
                    if emb.image and emb.image.url:
                        img = embeds_folder / f"{msg.id}_embed.png"
                        clean_url = emb.image.url.split("?")[0]
                        if await download_image(clean_url, img):
                            ed["image"] = f"embeds/{img.name}"

                    embed_data.append(ed)
                    total_embeds += 1

                messages.append({
                    "author_name": msg.author.display_name,
                    "author_id": msg.author.id,
                    "avatar": avatar_file,
                    "content": msg.content,
                    "attachments": saved_paths,
                    "created_at": msg.created_at,
                    "embeds": embed_data,
                    "buttons": button_labels,
                    "is_staff": any(r.id in STAFF_ROLES for r in msg.author.roles)
                })

            # ==================================================
            # ABORT TRANSCRIPT IF NO USER MESSAGES EXIST
            # ==================================================
            if not has_user_messages:
                shutil.rmtree(folder, ignore_errors=True)
                
                # Mark as deleted in DB (transcript_id remains null)
                await tm.tickets.update_one(
                    {"ticket_id": self.ticket_id}, 
                    {"$set": {"status": "deleted"}}
                )

                await interaction.followup.send(
                    f"🗑️ Ticket `{self.ticket_id}` deleted. *(No transcript generated because there were no user messages).* ",
                    ephemeral=True
                )

                # Log deletion Action with Explicit Channel Name
                await log_ticket_action(interaction.guild, "DELETE", ticket, interaction.user, discord.Color.red(), chan_name)

                await channel.delete()
                return

            # ==================================================
            # WRITE HTML + CSS
            # ==================================================
            (folder / "index.html").write_text(build_html(
                messages,
                self.ticket_id,
                html.escape(opener_name),
                html.escape(interaction.user.display_name),
                participants
            ), encoding="utf-8")

            (folder / "style.css").write_text(CSS_CONTENT, encoding="utf-8")

            # ==================================================
            # ZIP EVERYTHING
            # ==================================================
            zip_path = Path(f"transcripts/{self.ticket_id}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:

                z.write(folder / "index.html", "index.html")
                z.write(folder / "style.css", "style.css")

                for av in avatars_folder.iterdir():
                    z.write(av, f"avatars/{av.name}")

                for root, dirs, files in os.walk(attachments_root):
                    for file in files:
                        fp = Path(root) / file
                        arc = str(fp).split(f"transcripts/{self.ticket_id}/")[1]
                        z.write(fp, arc)

                for file in embeds_folder.iterdir():
                    z.write(file, f"embeds/{file.name}")

            # ==================================================
            # DELETE WORKING FOLDER
            # ==================================================
            shutil.rmtree(folder, ignore_errors=True)
            
            # ==================================================
            # LOG SUMMARY & SEND
            # ==================================================
            transcript_message_id = None
            log_ch = guild.get_channel(TRANSCRIPT_LOG_CHANNEL_ID)
            
            if log_ch:
                embed = discord.Embed(
                    title=f"📄 Transcript Generated — {self.ticket_id}",
                    color=0xff8b3d
                )
                embed.add_field(name="Ticket ID", value=f"`{self.ticket_id}`", inline=True)
                embed.add_field(name="Messages", value=f"`{len(messages)}`", inline=True)
                embed.add_field(name="Attachments", value=f"`{total_attachments}`", inline=True)
                embed.add_field(name="Embeds", value=f"`{total_embeds}`", inline=True)
                embed.add_field(name="Buttons", value=f"`{total_buttons}`", inline=True)
                
                embed.add_field(name="Opened By", value=f"<@{opener_id}>", inline=True)
                embed.add_field(name="Opener ID", value=f"`{opener_id}`", inline=True)
                embed.add_field(name="Deleted By", value=interaction.user.mention, inline=True)

                max_bytes = 24 * 1024 * 1024  
                file_size = zip_path.stat().st_size 

                try:
                    if file_size <= max_bytes:
                        # Capture the message object to get its ID!
                        log_msg = await log_ch.send(embed=embed, file=discord.File(zip_path))
                        transcript_message_id = str(log_msg.id)
                    else:
                        embed.color = discord.Color.yellow()
                        embed.add_field(
                            name="⚠️ File Too Large", 
                            value=f"The transcript ZIP is **{file_size / (1024*1024):.2f} MB**, which exceeds Discord's limit.",
                            inline=False
                        )
                        # Capture the message object even if file failed
                        log_msg = await log_ch.send(embed=embed)
                        transcript_message_id = str(log_msg.id)
                except discord.HTTPException as e:
                    await log_ch.send(f"❌ Failed to upload transcript for `{self.ticket_id}`: {e}")
                
                # --- AGGRESSIVE CLEANUP ---
                if zip_path.exists():
                    os.remove(zip_path)

            # ==================================================
            # DATABASE UPDATE
            # ==================================================
            # Prepare the data dictionary
            update_data = {"status": "deleted"}
            
            # If we successfully sent the log, add the transcript_id!
            if transcript_message_id:
                update_data["transcript_id"] = transcript_message_id
                
            # Perform a single database update
            await tm.tickets.update_one(
                {"ticket_id": self.ticket_id}, 
                {"$set": update_data}
            )

            # ==================================================
            # RESPOND TO STAFF/USER & CHANNEL DELETION
            # ==================================================
            await interaction.followup.send(
                f"🗑️ Ticket `{self.ticket_id}` deleted & transcript processed.",
                ephemeral=True
            )

            # Log deletion Action with explicit channel name
            await log_ticket_action(interaction.guild, "DELETE", ticket, interaction.user, discord.Color.red(), chan_name)

            await channel.delete()

        except Exception:
            tb = traceback.format_exc()
            log_ch = interaction.guild.get_channel(TRANSCRIPT_LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(f"❌ **Transcript Error**\n```py\n{tb}\n```")

# ==========================================================
# MAIN BUTTON PANEL
# ==========================================================
class TicketControlButtons(View):
    def __init__(self, ticket=None):
        super().__init__(timeout=None)
        self.ticket = ticket or {"ticket_id": "UNKNOWN"}
        self.ticket_id = self.ticket["ticket_id"]

    async def ensure_staff(self, interaction: discord.Interaction):
        if not any(r.id in STAFF_ROLES for r in interaction.user.roles):
            await interaction.response.send_message("⛔ Staff only.", ephemeral=True)
            return False
        return True

    @button(label="🎟️ Claim", style=ButtonStyle.blurple, custom_id="ticket_claim_button")
    async def claim_btn(self, interaction: discord.Interaction, btn):
        if not await self.ensure_staff(interaction):
            return

        await interaction.response.defer()

        try:
            tm = TicketManager(get_connection())
            ticket = await tm.get_by_channel(interaction.channel.id)

            if not ticket:
                return await interaction.followup.send("❌ Ticket not found in DB.", ephemeral=True)

            if ticket.get("status") in ["closed", "deleted"]:
                return await interaction.followup.send("⚠️ This ticket is closed! You must reopen it before claiming.", ephemeral=True)

            if ticket.get("claimed_by"):
                return await interaction.followup.send("⚠️ Already claimed.", ephemeral=True)

            await tm.claim(ticket["ticket_id"], interaction.user.id)

            claimed_category = interaction.guild.get_channel(1362461644768411758)
            if claimed_category:
                await interaction.channel.edit(category=claimed_category)

            await interaction.followup.send(f"🎟️ Ticket claimed by {interaction.user.mention}.")
            
            # Log Claim Action with Channel Name
            await log_ticket_action(interaction.guild, "CLAIM", ticket, interaction.user, discord.Color.blurple(), interaction.channel.name)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"Claim Error:\n{tb}")
            await interaction.followup.send(f"❌ **Error while claiming:**\n```py\n{e}\n```", ephemeral=True)

    @button(label="🔒 Close", style=ButtonStyle.grey, custom_id="ticket_close_button")
    async def close_btn(self, interaction, btn):
        await interaction.response.defer()

        try:
            tm = TicketManager(get_connection())
            ticket = await tm.get_by_channel(interaction.channel.id)
            if not ticket: 
                return await interaction.followup.send("❌ Not found in DB.", ephemeral=True)

            # --- AUTHORIZATION CHECK ---
            is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
            is_creator = interaction.user.id == int(ticket["user_id"])

            if not (is_staff or is_creator):
                return await interaction.followup.send("⛔ You do not have permission to close this ticket.", ephemeral=True)
            # -------------------------------

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

            # --- CUSTOM CLOSE MESSAGE LOGIC ---
            if is_staff:
                # Regular message for Staff
                await interaction.followup.send("🔒 Ticket closed and channel locked.")
            else:
                # Custom message for the Ticket Creator
                await interaction.followup.send(
                    "🔒 **Ticket closed and channel locked.**\n\n"
                    "⚠️ *Note: You cannot reopen this ticket. However, you are free to delete the ticket if you wish by using the Delete button or `/ticket delete`*"
                )

            # Log Close Action with Channel Name
            await log_ticket_action(interaction.guild, "CLOSE", ticket, interaction.user, discord.Color.dark_grey(), interaction.channel.name)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @button(label="🔓 Reopen", style=ButtonStyle.green, custom_id="ticket_reopen_button")
    async def reopen_btn(self, interaction, btn):
        # Kept staff-only to prevent user spam
        if not await self.ensure_staff(interaction): return
        await interaction.response.defer()

        try:
            tm = TicketManager(get_connection())
            ticket = await tm.get_by_channel(interaction.channel.id)
            if not ticket: return await interaction.followup.send("❌ Not found in DB.", ephemeral=True)

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

            # Log Reopen Action with Channel Name
            await log_ticket_action(interaction.guild, "REOPEN", ticket, interaction.user, discord.Color.green(), interaction.channel.name)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @button(label="🗑️ Delete", style=ButtonStyle.red, custom_id="ticket_delete_button")
    async def delete_btn(self, interaction, btn):
        tm = TicketManager(get_connection())
        ticket = await tm.get_by_channel(interaction.channel.id)
        
        if not ticket:
            return await interaction.response.send_message("❌ Not found in DB.", ephemeral=True)

        # --- NEW AUTHORIZATION CHECK ---
        is_staff = any(r.id in STAFF_ROLES for r in interaction.user.roles)
        is_creator = interaction.user.id == int(ticket["user_id"])

        if not (is_staff or is_creator):
            return await interaction.response.send_message("⛔ You do not have permission to delete this ticket.", ephemeral=True)
        # -------------------------------

        await interaction.response.send_message(
            f"⚠️ Confirm deletion of ticket `{ticket['ticket_id']}`?",
            view=ConfirmDeleteView(ticket["ticket_id"]),
            ephemeral=True
        )