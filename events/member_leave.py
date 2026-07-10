import discord
# Sasha Alexander Wildfang - Revamped MemberLeave Cog
from discord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

# Config: Only the main public leave channel is needed now
LEAVE_CHANNEL_ID = 1358485536511234164
UTC_TZ = ZoneInfo("UTC")

class MemberLeave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        now = datetime.now(tz=UTC_TZ)

        # 🕒 Calculate time spent in the server
        joined_at = member.joined_at
        if joined_at:
            # Ensure joined_at is offset-aware for comparison
            if joined_at.tzinfo is None:
                joined_at = joined_at.replace(tzinfo=UTC_TZ)
                
            delta = now - joined_at
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes = remainder // 60

            duration = (
                f"{days}d {hours}h {minutes}m"
                if days or hours or minutes
                else "Less than a minute"
            )
        else:
            duration = "Unknown (join date missing)"

        # 👋 Public leave message (Logs only to the main channel)
        leave_channel = member.guild.get_channel(LEAVE_CHANNEL_ID)
        if leave_channel:
            embed = discord.Embed(
                title="👋 A Member Has Left",
                description=(
                    f"**{member.mention}** has left the server.\n"
                    f"They were with us for **{duration}**."
                ),
                color=discord.Color.red(),
                timestamp=now
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Use the corrected username format (member.name) for current discord.py versions
            embed.set_footer(text=f"User ID: {member.id} • We hope to see you again!")
            
            try:
                await leave_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"❌ Permission error: Cannot send messages in channel {LEAVE_CHANNEL_ID}")
        else:
            print(f"⚠️ Leave channel {LEAVE_CHANNEL_ID} not found in guild.")

async def setup(bot):
    await bot.add_cog(MemberLeave(bot))
