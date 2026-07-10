import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal

# ==========================================
# ROLE & CATEGORY IDs
# ==========================================
STAFF_TEAM_ROLE = 1358470109965979859
SFW_ARTIST_ROLE = 1499426309972033746
NSFW_ARTIST_ROLE = 1499426344025723103
CLAIMED_TICKETS_CATEGORY_ID = 1362461644768411758

# ==========================================
# CONFIRMATION VIEW
# ==========================================
class ConfirmGrantView(discord.ui.View):
    def __init__(self, invoker: discord.Member, target: discord.Member, role: discord.Role):
        super().__init__(timeout=60)
        self.invoker = invoker
        self.target = target
        self.role = role

    # Prevent other people in the channel from clicking the buttons
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.invoker:
            await interaction.response.send_message("Only the person who ran the command can click these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Grant", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable buttons after clicking
        for child in self.children:
            child.disabled = True
            
        try:
            await self.target.add_roles(self.role)
            await interaction.response.edit_message(
                content=f"**Success!** {self.invoker.mention} granted the {self.role.mention} role to {self.target.mention}.", 
                view=self
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="❌ **Error:** I don't have permission to manage roles, or my bot role is lower than the Artist role.", 
                view=self
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
            
        await interaction.response.edit_message(
            content=f"❌ **Cancelled.** {self.target.mention} was not given the role.", 
            view=self
        )
        self.stop()

    # Handle timeout if they don't click anything for 60 seconds
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        
        # We use the message object to edit it since there is no interaction to respond to on timeout
        try:
            await self.message.edit(content="⏳ **Timed out.** You took too long to confirm.", view=self)
        except Exception:
            pass


# ==========================================
# COMMAND COG
# ==========================================
class GrantRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="grantrole", description="Grant the SFW or NSFW Artist role to a user")
    @app_commands.describe(
        user="The user you want to give the role to",
        role_type="Which role to grant (Select from the list)"
    )
    async def grant_artist(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        role_type: Literal["SFW Artist", "NSFW Artist"]
    ):
        # 1. Category Check (MUST be in the Claimed Tickets Category)
        if getattr(interaction.channel, "category_id", None) != CLAIMED_TICKETS_CATEGORY_ID:
            return await interaction.response.send_message(
                f"{interaction.user.mention}, this command can only be used in a claimed ticket channel.", 
                ephemeral=False
            )

        # 2. Staff Team Check
        is_staff_team = any(r.id == STAFF_TEAM_ROLE for r in interaction.user.roles)
        if not is_staff_team:
            return await interaction.response.send_message(
                f"{interaction.user.mention}, you need the **Staff Team** role to use this command.", 
                ephemeral=False
            )

        # 3. Determine which role ID to use based on the dropdown selection
        role_id = SFW_ARTIST_ROLE if role_type == "SFW Artist" else NSFW_ARTIST_ROLE
        role_obj = interaction.guild.get_role(role_id)

        # Safety check in case the role was deleted
        if not role_obj:
            return await interaction.response.send_message(
                f"❌ Could not find the **{role_type}** role in this server. Please check the role IDs.", 
                ephemeral=False
            )

        # 4. Check if the user already has the role
        if role_obj in user.roles:
            return await interaction.response.send_message(
                f"{user.mention} already has the {role_obj.mention} role!", 
                ephemeral=False
            )

        # 5. Send the non-ephemeral confirmation message
        view = ConfirmGrantView(invoker=interaction.user, target=user, role=role_obj)
        
        await interaction.response.send_message(
            f"{interaction.user.mention}, are you sure you want to grant the {role_obj.mention} role to {user.mention}?",
            view=view,
            ephemeral=False
        )
        
        # Save the message object to the view so it can be edited if it times out
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(GrantRole(bot))