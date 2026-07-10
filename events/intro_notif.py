import discord
from discord.ext import commands

class IntroNotification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.NOTIF_CHANNEL_ID = 1497237389741920446
        self.PING_ROLE_ID = 1497237607044747375

    @commands.Cog.listener("on_new_profile")
    async def on_new_profile(self, member: discord.Member, profile_data: dict):
        """Triggered automatically when a new profile is saved."""
        channel = self.bot.get_channel(self.NOTIF_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(self.NOTIF_CHANNEL_ID)
            except discord.NotFound:
                return

        # Build a short, snappy embed
        # Note: Backticks removed from the mention so Discord actually resolves it!
        embed = discord.Embed(
            title=f"New Profile: {profile_data.get('name', member.display_name)}!",
            description=f"Say hello to {member.mention}! They just set up their dating profile. Run **/profile** {member.mention} to see the whole thing!",
            color=discord.Color.fuchsia()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # Quick details for a glance
        embed.add_field(name="Age", value=profile_data.get("age", "N/A"), inline=True)
        embed.add_field(name="Gender", value=profile_data.get("gender", "N/A"), inline=True)
        embed.add_field(name="Sexuality", value=profile_data.get("sexuality", "N/A"), inline=True)
        
        embed.add_field(name="Location", value=profile_data.get("location", "N/A"), inline=True)
        embed.add_field(name="Looking For", value=profile_data.get("looking_for_relationship_type", "N/A"), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) # Blank field to balance the layout perfectly
        
        # Include a snippet of their bio if they wrote one
        bio = profile_data.get("bio", "")
        if bio and bio.lower() not in ["n/a", "none", "skip"]:
            embed.add_field(name="Bio Preview", value=f"*{bio[:150]}...*", inline=False)

        # Send the ping explicitly OUTSIDE the embed as message content
        ping_text = f"<@&{self.PING_ROLE_ID}> A new profile just dropped!"
        
        await channel.send(content=ping_text, embed=embed)

async def setup(bot):
    await bot.add_cog(IntroNotification(bot))