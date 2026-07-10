import discord
from discord.ext import commands

# =========================
# Config / Constants
# =========================
FREDBOAT_ID = 184405311681986560

class FredboatManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # We only care if someone LEFT or MOVED OUT OF a voice channel
        if before.channel is not None and before.channel != after.channel:
            channel = before.channel
            
            # SAFER CHECK: Look directly in the channel's member list for FredBoat
            fredboat = discord.utils.get(channel.members, id=FREDBOAT_ID)
            
            # If FredBoat is in the channel that was just left
            if fredboat is not None:
                
                # Count how many humans (non-bots) are still in the channel
                humans_in_vc = [m for m in channel.members if not m.bot]
                
                # If no humans are left, disconnect FredBoat
                if len(humans_in_vc) == 0:
                    print(f"[{channel.guild.name}] Voice channel '{channel.name}' is empty. Disconnecting FredBoat.")
                    try:
                        # Moving a member to 'None' disconnects them from the voice channel
                        await fredboat.move_to(None)
                        print("✅ Successfully disconnected FredBoat.")
                    except discord.Forbidden:
                        print("❌ Error: I don't have the 'Move Members' permission to disconnect FredBoat!")
                    except Exception as e:
                        print(f"❌ An error occurred: {e}")

# =========================
# Setup
# =========================
async def setup(bot: commands.Bot):
    await bot.add_cog(FredboatManager(bot))