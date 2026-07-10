import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection  # Adjust this import if your path is different

class ConfirmPasswordChange(discord.ui.View):
    def __init__(self, new_password: str, bot: commands.Bot):
        super().__init__(timeout=60)
        self.new_password = new_password
        self.bot = bot

    @discord.ui.button(label="Confirm Change", style=discord.ButtonStyle.success, custom_id="confirm_pass")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        try:
            db = get_connection()
            globals_col = db["globals"]
            
            # 1. Update the password in the database
            await globals_col.update_one({}, {"$set": {"serverPassword": self.new_password}}, upsert=True)
            
            # 2. Automatically update the existing rules embeds in both channels
            rule_channel_ids = [1358485180146384906, 1383559103913267282]
            for c_id in rule_channel_ids:
                channel = interaction.guild.get_channel(c_id)
                if channel:
                    # Scan the last 15 messages to find the bot's rules embed
                    async for msg in channel.history(limit=15):
                        if msg.author == self.bot.user and msg.embeds:
                            embed = msg.embeds[0]
                            # Identify the main rules embed by its title
                            if embed.title == "🐾 Kitty Kingdom — Server Rules":
                                # Field index 11 is Rule 12 (since it's 0-indexed)
                                embed.set_field_at(
                                    11,
                                    name="**12. Privacy, Safety & Off-Server Conduct**",
                                    value=(
                                        "• Do not share personal information or private messages.\n"
                                        "• No doxxing, threats, or intimidation.\n"
                                        "• Harassment or conflict related to this server may be acted on even outside Discord.\n"
                                        f"• If you want to get into the server, remember **{self.new_password}**."
                                    ),
                                    inline=False
                                )
                                # Edit the message silently
                                await msg.edit(embed=embed)
                                break  # Stop looking in this channel once we found and edited it

            # 3. Disable buttons after a successful click
            for child in self.children:
                child.disabled = True
            await interaction.edit_original_response(
                content=f"Password successfully changed to `{self.new_password}` in the database, and the rules channels have been auto-updated!", 
                view=self
            )
            
            # 4. Notify the staff channel
            staff_channel = self.bot.get_channel(1358486734714835125)
            if staff_channel:
                embed = discord.Embed(
                    title="🔐 Server Password Changed",
                    description=f"The server verification password was just updated by {interaction.user.mention}.",
                    color=discord.Color.green()
                )
                embed.add_field(name="New Password", value=f"`{self.new_password}`", inline=False)
                
                # Ping the staff role outside the embed so it actually triggers a notification
                await staff_channel.send(content="<@&1358470109965979859>", embed=embed)

        except Exception as e:
            print(f"Failed to update password: {e}")
            await interaction.followup.send(f"❌ An error occurred while updating the database or rules.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_pass")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable buttons and abort
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Password change cancelled.", view=self)


class PasswordManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="getpassword", description="Get the current server verification password")
    @app_commands.checks.has_role(1358470109965979859)  # Staff Role Check
    async def getpassword(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            db = get_connection()
            globals_col = db["globals"]
            doc = await globals_col.find_one({})
            
            if doc and "serverPassword" in doc:
                await interaction.followup.send(f"🔐 The current active server password is: `{doc['serverPassword']}`", ephemeral=True)
            else:
                await interaction.followup.send("⚠️ No server password is currently set in the database.", ephemeral=True)
        except Exception as e:
            print(f"Error fetching password: {e}")
            await interaction.followup.send("❌ Database error while trying to fetch the password.", ephemeral=True)

    @app_commands.command(name="changepassword", description="Change the server verification password")
    @app_commands.describe(new_pass="The new password to require for verification")
    @app_commands.default_permissions(administrator=True)  # Still Admin Only
    async def changepassword(self, interaction: discord.Interaction, new_pass: str):
        view = ConfirmPasswordChange(new_password=new_pass, bot=self.bot)
        
        await interaction.response.send_message(
            f"Are you sure you want to change the server password to `{new_pass}`?\n\n*This will update the database, automatically edit the rules embeds, and notify the staff team.*", 
            view=view, 
            ephemeral=True
        )

    # This catches the error if someone without the staff role tries to use /getpassword
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingRole):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ You must have the Staff Team role to use this command.", ephemeral=True)
            else:
                await interaction.followup.send("❌ You must have the Staff Team role to use this command.", ephemeral=True)
        else:
            print(f"Error in PasswordManager cog: {error}")

async def setup(bot):
    await bot.add_cog(PasswordManager(bot))