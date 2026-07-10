import discord
from discord.ext import commands
from discord import app_commands
from db.database import get_connection
import re
import time

class GetJoinApp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="getjoinapp", description="View a user's join application by ID or mention")
    @app_commands.describe(
        target_user="The user ID or @mention whose application you want to view",
        silent="Whether the response should be hidden (True by default)"
    )
    @app_commands.checks.has_role(1358470109965979859)  # Staff Team role ID
    async def getjoinapp(self, interaction: discord.Interaction, target_user: str, silent: bool = True):
        await interaction.response.defer(ephemeral=silent)

        # Extract the raw ID in case a staff member @mentions them instead of pasting the ID
        user_id_str = re.sub(r'\D', '', target_user)
        
        if not user_id_str:
            return await interaction.followup.send("❌ Please provide a valid Discord ID or @mention.", ephemeral=silent)

        try:
            db = get_connection()
            applications_col = db["join_applications"]
            
            # Fetch the application from the database using the user's ID
            app_data = await applications_col.find_one({"discordId": user_id_str})
            
            # Attempt to fetch the user globally
            user_obj = None
            member_obj = interaction.guild.get_member(int(user_id_str))
            
            try:
                user_obj = member_obj or await self.bot.fetch_user(int(user_id_str))
            except discord.NotFound:
                pass

            display_name = user_obj.display_name if user_obj else "Unknown User"
            
            embed = discord.Embed(
                title=f"📄 Join Application: {display_name}",
                color=discord.Color.blue()
            )
            
            if user_obj and user_obj.avatar:
                embed.set_thumbnail(url=user_obj.avatar.url)
            
            if user_obj:
                created_timestamp = int(user_obj.created_at.timestamp())
                embed.add_field(
                    name="Discord Info", 
                    value=f"**Account Created:** <t:{created_timestamp}:D> (<t:{created_timestamp}:R>)", 
                    inline=False
                )
            
            if member_obj and member_obj.joined_at:
                joined_timestamp = int(member_obj.joined_at.timestamp())
                embed.add_field(
                    name="Server Info", 
                    value=f"**Joined Server:** <t:{joined_timestamp}:D> (<t:{joined_timestamp}:R>)", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Server Info", 
                    value="**Status:** User is not currently in the server.", 
                    inline=False
                )

            if app_data:
                status = app_data.get("status", "unknown").upper()
                
                if status == "APPROVED":
                    embed.color = discord.Color.green()
                elif status == "DENIED":
                    embed.color = discord.Color.red()
                elif status == "PENDING":
                    embed.color = discord.Color.yellow()
                
                desc = f"**Current Status:** `{status}`\n"
                if app_data.get("verifiedBy"):
                    desc += f"**Handled By:** <@{app_data['verifiedBy']}>\n"
                desc += f"User ID: `{user_id_str}`"
                
                embed.description = desc
                
                embed.add_field(name="1. Age & DOB", value=app_data.get("ageAndDob", "N/A"), inline=False)
                embed.add_field(name="2. Found Server", value=app_data.get("howFoundServer", "N/A"), inline=False)
                embed.add_field(name="3. Fursona & Reason", value=app_data.get("fursonaAndReason", "N/A"), inline=False)
                embed.add_field(name="4. Rules & Password", value=app_data.get("rulesAndPassword", "N/A"), inline=False)
                embed.add_field(name="5. Bio", value=app_data.get("bio", "N/A"), inline=False)
                
                if "submittedAt" in app_data:
                    sub_time = app_data["submittedAt"]
                    if hasattr(sub_time, 'strftime'):
                        embed.set_footer(text=f"Submitted at: {sub_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    else:
                        embed.set_footer(text=f"Submitted at: {sub_time}")

                # ==========================================
                # NEW LOGIC: Record that the staff member checked this app
                # ==========================================
                if not hasattr(self.bot, 'join_app_checks'):
                    self.bot.join_app_checks = {}
                # Maps (staff_id, target_user_id) to the current UNIX timestamp
                self.bot.join_app_checks[(interaction.user.id, int(user_id_str))] = time.time()

            else:
                embed.description = f"User ID: `{user_id_str}`\n\n❌ **No application found in the database for this user.**"
                embed.color = discord.Color.red()

            await interaction.followup.send(embed=embed, ephemeral=silent)

        except Exception as e:
            print(f"Error fetching join application: {e}")
            await interaction.followup.send("❌ An error occurred while fetching data from the database.", ephemeral=silent)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingRole):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ You must have the Staff Team role to use this command.", ephemeral=True)
            else:
                await interaction.followup.send("❌ You must have the Staff Team role to use this command.", ephemeral=True)
        else:
            print(f"Error in GetJoinApp cog: {error}")

async def setup(bot):
    await bot.add_cog(GetJoinApp(bot))