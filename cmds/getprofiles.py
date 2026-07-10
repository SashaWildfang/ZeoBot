import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection

class AdminUtils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="listprofiles", description="[Admin Only] List all users who have created a dating profile.")
    @app_commands.checks.has_any_role(1358472511133585564, 1358472635234779207, 1358473248534167663) # Admin roles
    async def list_profiles(self, interaction: discord.Interaction):
        """Fetches all profile IDs from the async database and lists them."""
        await interaction.response.defer(ephemeral=True)

        try:
            db = get_connection()
            dating_col = db["dating_profiles"]

            # Use to_list(length=None) to fetch all documents from the AsyncIOMotorCursor
            # We only fetch the _id field to save memory/speed
            cursor = dating_col.find({}, {"_id": 1})
            profiles = await cursor.to_list(length=None)

            if not profiles:
                await interaction.followup.send("📭 No dating profiles found in the database.", ephemeral=True)
                return

            # Extract IDs and format into mentions
            mentions = [f"<@{doc['_id']}>" for doc in profiles]
            
            # Format results
            header = f"✅ **Found {len(mentions)} profiles:**\n\n"
            result_text = ", ".join(mentions)

            # Discord character limit is 2000. We use 1900 to be safe.
            if len(header + result_text) > 1900:
                await interaction.followup.send(header, ephemeral=True)
                # Split mentions into chunks that fit in Discord messages
                current_chunk = ""
                for mention in mentions:
                    if len(current_chunk) + len(mention) + 2 > 1900:
                        await interaction.followup.send(current_chunk, ephemeral=True)
                        current_chunk = mention
                    else:
                        current_chunk += (", " if current_chunk else "") + mention
                
                if current_chunk:
                    await interaction.followup.send(current_chunk, ephemeral=True)
            else:
                await interaction.followup.send(f"{header}{result_text}", ephemeral=True)

        except Exception as e:
            print(f"Error fetching profiles: {e}")
            await interaction.followup.send(f"❌ An error occurred: `{str(e)}`", ephemeral=True)

    @list_profiles.error
    async def list_profiles_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message("⛔ You do not have permission to use this command.", ephemeral=True)
        else:
            # Fallback for other errors
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminUtils(bot))