import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from datetime import datetime
from db.database import get_connection

class PremiumRandomUser(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_connection()
        self.user_data = self.db["users"]

    @app_commands.command(
        name="randomuser", 
        description="High-speed animated selection with converted timestamps!"
    )
    @app_commands.describe(forced_winner="Secretly force a specific user to win (Optional)")
    async def random_user(self, interaction: discord.Interaction, forced_winner: discord.Member = None):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Use this in a server!", ephemeral=True)

        members = [m for m in guild.members if not m.bot]
        if len(members) < 5:
            return await interaction.response.send_message("I need more members to spin!", ephemeral=True)

        await interaction.response.send_message("⚙️ **Spinning the wheel...**")

        total_steps = 20
        # If forced_winner is provided, use them. Otherwise, pick randomly.
        winner = forced_winner if forced_winner else random.choice(members)
        
        # --- Animation Loop ---
        for i in range(total_steps):
            is_last = (i == total_steps - 1)
            current = winner if is_last else random.choice(members)
            others = random.sample([m for m in members if m != current], k=2)
            
            reel = (
                f"```ansi\n"
                f"  \u001b[0;30m{others[0].display_name[:15]}\u001b[0m\n"
                f"\u001b[1;37m▶ {current.display_name[:15].upper()}\u001b[0m\n"
                f"  \u001b[0;30m{others[1].display_name[:15]}\u001b[0m\n"
                f"```"
            )

            color = 0x5865F2 if not is_last else 0x57F287
            embed = discord.Embed(
                title="Spinning The Wheel",
                description=f"Who will it be?\n{reel}",
                color=color
            )
            embed.set_thumbnail(url=current.display_avatar.url)
            progress = "▬" * i + "🔵" + "▬" * (total_steps - i - 1)
            embed.set_footer(text=f"Progress: {progress}")

            try:
                await interaction.edit_original_response(content=None, embed=embed)
            except discord.HTTPException:
                continue

            if i < 10: wait = 0.35
            elif i < 15: wait = 0.6
            elif i < 18: wait = 1.0
            else: wait = 1.8
                
            await asyncio.sleep(wait)

        # --- Database Fetch & Timestamp Conversion ---
        user_record = await self.user_data.find_one({"discordId": str(winner.id)})
        last_msg = "No message history found."
        msg_time_str = "Unknown"

        if user_record:
            last_msg = user_record.get("lastMessage", "No message found.")
            raw_time = user_record.get("lastMessageTimestamp") 
            if raw_time:
                try:
                    dt_obj = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    msg_time_str = f"<t:{int(dt_obj.timestamp())}:R>"
                except Exception:
                    msg_time_str = "Invalid Format"

        # --- Final Result ---
        final = discord.Embed(
            title="🎊 WE HAVE A WINNER! 🎊",
            description=f"## {winner.mention}\nSelected from **{len(members)}** users!",
            color=0x57F287,
            timestamp=discord.utils.utcnow()
        )
        final.set_thumbnail(url=winner.display_avatar.url)
        
        final.add_field(name="Last Seen Saying:", value=f"*{last_msg}*", inline=False)
        final.add_field(name="Last Message Sent:", value=msg_time_str, inline=True)
        final.add_field(name="User ID", value=f"`{winner.id}`", inline=True)
        final.add_field(name="Joined Server", value=f"<t:{int(winner.joined_at.timestamp())}:R>", inline=True)

        await interaction.edit_original_response(embed=final)

async def setup(bot: commands.Bot):
    await bot.add_cog(PremiumRandomUser(bot))