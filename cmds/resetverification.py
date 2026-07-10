import os
import json
import discord
from discord.ext import commands
from discord import app_commands

# --- Configuration ---
DENIED_USERS_FILE = "denied_users.json"
STAFF_ROLE_ID = 1358470109965979859

# --- Helper Functions ---
def load_json_file(filename: str) -> dict:
    """Loads a JSON file safely, returning an empty dict if it doesn't exist."""
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump({}, f)
    with open(filename, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json_file(data: dict, filename: str) -> None:
    """Saves data to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)


class ResetVerification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="resetverification", 
        description="Removes a user's verification denial lockout, allowing them to re-apply immediately."
    )
    @app_commands.describe(user="The user to remove from the denied list")
    async def reset_verification(self, interaction: discord.Interaction, user: discord.User):
        
        # 1. Role Verification
        # Check if the user executing the command has the required staff role
        has_permission = any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)
        if not has_permission:
            await interaction.response.send_message(
                "❌ You do not have the required permissions to use this command.", 
                ephemeral=True
            )
            return

        # 2. Defer response in case file operations take a moment
        await interaction.response.defer(ephemeral=True)

        # 3. Load Data & Process Removal
        denied_data = load_json_file(DENIED_USERS_FILE)
        user_id_str = str(user.id)

        if user_id_str in denied_data:
            # Remove the user from the dictionary
            del denied_data[user_id_str]
            # Save the updated dictionary back to the file
            save_json_file(denied_data, DENIED_USERS_FILE)
            
            await interaction.followup.send(
                f"✅ Successfully removed {user.mention} (`{user.id}`) from the denied users list. They can now submit a new verification form."
            )
        else:
            await interaction.followup.send(
                f"⚠️ {user.mention} (`{user.id}`) is not currently locked out in the denied users list."
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ResetVerification(bot))