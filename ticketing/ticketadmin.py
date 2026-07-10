import discord
from discord import app_commands
from discord.ext import commands
import traceback
from typing import Literal
import re
from datetime import datetime

# ==========================================================
# IMPORTS
# ==========================================================
from db.database import get_connection
from ticketing.ticket_manager import TicketManager

TRANSCRIPT_LOG_CHANNEL_ID = 1445923851178610718

class TicketAdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketadmin", description="Admin commands for managing and auditing tickets")
    @app_commands.describe(
        action="The admin action to perform",
        user="The user to look up (Used for get_tickets / grab_transcripts)",
        ticket_id="The ticket ID to look up (Used for getinfo, e.g., TK-00315 or 315)"
    )
    @app_commands.default_permissions(administrator=True)
    async def ticketadmin_action(
        self, 
        interaction: discord.Interaction, 
        action: Literal["get_tickets", "grab_transcripts", "sync_transcripts", "getinfo"],
        user: discord.User = None,
        ticket_id: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            tm = TicketManager(get_connection())

            # ==========================================
            # ACTION: SYNC TRANSCRIPTS
            # ==========================================
            if action == "sync_transcripts":
                log_channel = interaction.guild.get_channel(TRANSCRIPT_LOG_CHANNEL_ID)
                if not log_channel:
                    return await interaction.followup.send("❌ Transcript channel not found.", ephemeral=True)

                await interaction.followup.send("⏳ **Reconstructing Database...** Parsing mentions and IDs from transcripts.", ephemeral=True)

                stats = {"created": 0, "updated": 0, "already_linked": 0, "failed": 0}

                async for msg in log_channel.history(limit=None, oldest_first=False):
                    if not msg.embeds: continue
                    
                    embed = msg.embeds[0]
                    t_id = None
                    opener_id = "Unknown"
                    closer_id = None

                    for field in embed.fields:
                        val = field.value.strip()
                        clean_id = re.sub(r'[^0-9]', '', val)

                        if field.name == "Ticket ID":
                            t_id = val.replace("`", "").strip()
                        elif "Opened By" in field.name or "Opener ID" in field.name:
                            opener_id = clean_id if clean_id else "Unknown"
                        elif "Deleted By" in field.name or "Closed By" in field.name:
                            closer_id = clean_id if clean_id else None
                    
                    if not t_id: continue
                    
                    result = await tm.tickets.update_one(
                        {"ticket_id": t_id},
                        {"$set": {"transcript_id": str(msg.id)}}
                    )

                    if result.modified_count > 0:
                        stats["updated"] += 1
                    elif result.matched_count > 0:
                        stats["already_linked"] += 1
                    else:
                        try:
                            new_doc = {
                                "ticket_id": t_id,
                                "ticket_type": "nsfw", 
                                "user_id": opener_id,
                                "opened_by": opener_id,
                                "guild_id": str(interaction.guild.id),
                                "channel_id": "deleted", 
                                "topic": "NSFW Verification (Restored)",
                                "status": "deleted",
                                "claimed_by": None,
                                "opened_at": msg.created_at,
                                "last_updated": msg.created_at,
                                "closed_at": msg.created_at,
                                "closed_by": closer_id,
                                "transcript_id": str(msg.id)
                            }
                            await tm.tickets.insert_one(new_doc)
                            stats["created"] += 1
                        except Exception:
                            stats["failed"] += 1

                summary = (
                    f"✅ **Restoration Complete!**\n"
                    f"• **{stats['created']}** entries built from mentions/IDs.\n"
                    f"• **{stats['updated']}** existing records linked.\n"
                    f"• **{stats['already_linked']}** records were already linked.\n"
                    f"• **{stats['failed']}** errors."
                )
                await interaction.followup.send(summary, ephemeral=True)

            # ==========================================
            # ACTION: GET TICKETS
            # ==========================================
            elif action == "get_tickets":
                if not user:
                    return await interaction.followup.send("❌ Please provide a `user` for this action.", ephemeral=True)
                
                cursor = tm.tickets.find({"user_id": str(user.id)}).sort("opened_at", -1)
                user_tickets = await cursor.to_list(length=15)
                
                if not user_tickets:
                    return await interaction.followup.send(f"📭 No tickets found for {user.mention}.", ephemeral=True)

                embed = discord.Embed(
                    title=f"📋 Ticket Audit: {user.display_name}", 
                    description=f"Showing last {len(user_tickets)} tickets found in database.",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=user.display_avatar.url)

                for t in user_tickets:
                    t_id = t.get('ticket_id', 'Unknown')
                    status = t.get('status', 'Unknown')
                    
                    opened_at = t.get('opened_at')
                    time_str = f"<t:{int(opened_at.timestamp())}:R>" if opened_at else "`Unknown`"
                    
                    closed_by = t.get('closed_by')
                    closer_str = f"<@{closed_by}>" if closed_by and str(closed_by).isdigit() else "`N/A`"
                    
                    trans_id = t.get('transcript_id')
                    trans_str = f"`{trans_id}`" if trans_id else "*None*"

                    embed.add_field(
                        name=f"🎫 {t_id}", 
                        value=(
                            f"**Status:** `{status}`\n"
                            f"**Opened:** {time_str}\n"
                            f"**Closed By:** {closer_str}\n"
                            f"**Transcript ID:** {trans_str}"
                        ), 
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)

            # ==========================================
            # ACTION: GRAB TRANSCRIPTS
            # ==========================================
            elif action == "grab_transcripts":
                if not user:
                    return await interaction.followup.send("❌ Please provide a `user` for this action.", ephemeral=True)
                
                cursor = tm.tickets.find(
                    {"user_id": str(user.id), "transcript_id": {"$ne": None}}
                ).sort("opened_at", -1)
                
                user_tickets = await cursor.to_list(length=None)
                
                if not user_tickets:
                    return await interaction.followup.send(f"❌ No transcripts found in DB for {user.mention}.", ephemeral=True)

                log_channel = interaction.guild.get_channel(TRANSCRIPT_LOG_CHANNEL_ID)
                if not log_channel:
                    return await interaction.followup.send("❌ Log channel not found.", ephemeral=True)

                await interaction.followup.send(f"🔍 Found **{len(user_tickets)}** transcripts for {user.display_name}. Sorting and fetching files...", ephemeral=True)

                # Dictionary to hold files sorted by ticket type
                grouped_files = {}
                failed_tickets = []

                for ticket in user_tickets:
                    t_id = ticket.get('ticket_id')
                    msg_id = ticket.get('transcript_id')
                    
                    # Safely handle missing or differently named type fields, default to "General"
                    raw_type = str(ticket.get("type", ticket.get("ticket_type", "general")))
                    display_type = raw_type.replace("_", " ").replace("-", " ").title()

                    try:
                        log_msg = await log_channel.fetch_message(int(msg_id))
                        if not log_msg.attachments:
                            failed_tickets.append(f"`{t_id}` (Missing file attachment)")
                            continue
                        
                        file = await log_msg.attachments[0].to_file()
                        
                        # Add the file to its respective category
                        if display_type not in grouped_files:
                            grouped_files[display_type] = []
                        grouped_files[display_type].append((t_id, file))
                        
                    except discord.NotFound:
                        failed_tickets.append(f"`{t_id}` (Message deleted from log channel)")
                    except Exception as e:
                        failed_tickets.append(f"`{t_id}` (Error: {e})")

                if not grouped_files:
                    return await interaction.followup.send(f"❌ Failed to extract any valid files.\n**Errors:**\n" + "\n".join(failed_tickets), ephemeral=True)

                # Send files grouped by their type
                for cat_name, items in grouped_files.items():
                    chunk_size = 10
                    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

                    for idx, chunk in enumerate(chunks):
                        files_in_chunk = [f[1] for f in chunk]
                        ticket_ids_in_chunk = [f[0] for f in chunk]
                        
                        # Add batch numbering only if there are multiple chunks for this category
                        batch_str = f" (Batch {idx + 1}/{len(chunks)})" if len(chunks) > 1 else ""
                        msg_text = f"📂 **{cat_name} Tickets**{batch_str}\nTickets included: `{', '.join(ticket_ids_in_chunk)}`"
                        
                        await interaction.followup.send(content=msg_text, files=files_in_chunk, ephemeral=True)

                if failed_tickets:
                    await interaction.followup.send(f"⚠️ **Could not fetch some transcripts:**\n" + "\n".join(failed_tickets), ephemeral=True)

            # ==========================================
            # ACTION: GET INFO (Ticket ID Lookup)
            # ==========================================
            elif action == "getinfo":
                if not ticket_id:
                    return await interaction.followup.send("❌ Please provide a `ticket_id` for this action.", ephemeral=True)

                # Clean the input: removes "TK-", "#", and spaces, then makes it uppercase
                clean_id = re.sub(r'^(TK-|-|#)+', '', ticket_id.strip(), flags=re.IGNORECASE).upper()
                
                # Search the DB using a regex that checks if the ID ends with the provided string
                ticket = await tm.tickets.find_one({"ticket_id": re.compile(f"{re.escape(clean_id)}$", re.IGNORECASE)})

                if not ticket:
                    return await interaction.followup.send(f"❌ Could not find any ticket matching `{ticket_id}` in the database.", ephemeral=True)
                
                # Extract basic data
                t_id = ticket.get('ticket_id', 'Unknown')
                status = ticket.get('status', 'Unknown')
                opener_id = ticket.get('user_id', 'Unknown')
                channel_id = ticket.get('channel_id', 'Unknown')
                is_special = ticket.get('special_ticket', False)
                
                # Timestamps
                opened_at = ticket.get('opened_at')
                if isinstance(opened_at, datetime):
                    opened_str = f"<t:{int(opened_at.timestamp())}:F>"
                else:
                    opened_str = "`Not Closed`"

                closed_at = ticket.get('closed_at')
                closed_str = f"<t:{int(closed_at.timestamp())}:F>" if isinstance(closed_at, datetime) else "`Not Closed`"
                
                # User Identifiers
                claimed_by = ticket.get('claimed_by')
                claimer_str = f"<@{claimed_by}>" if claimed_by else "`Unclaimed`"
                
                closed_by = ticket.get('closed_by')
                closer_str = f"<@{closed_by}>" if closed_by and str(closed_by).isdigit() else "`N/A`"
                
                # Transcript Info
                trans_id = ticket.get('transcript_id')
                trans_str = f"`{trans_id}`" if trans_id else "*None*"

                # Build the Embed
                embed = discord.Embed(
                    title=f"🔍 Ticket Lookup: {t_id}",
                    color=discord.Color.gold() if is_special else discord.Color.blurple()
                )
                embed.add_field(name="Status", value=f"`{status.capitalize()}`", inline=True)
                embed.add_field(name="Type", value="Special Support" if is_special else "Standard", inline=True)
                embed.add_field(name="Channel ID", value=f"`{channel_id}`", inline=True)
                
                embed.add_field(name="Opened By", value=f"<@{opener_id}>" if opener_id != 'Unknown' else "`Unknown`", inline=True)
                embed.add_field(name="Claimed By", value=claimer_str, inline=True)
                embed.add_field(name="Closed By", value=closer_str, inline=True)
                
                embed.add_field(name="Opened At", value=opened_str, inline=False)
                embed.add_field(name="Closed At", value=closed_str, inline=False)
                embed.add_field(name="Transcript Msg ID", value=trans_str, inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(traceback.format_exc())
            await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketAdminCommands(bot))