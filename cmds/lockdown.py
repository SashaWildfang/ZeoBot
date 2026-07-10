import discord
from discord.ext import commands
from discord import app_commands
import json
import os

LOCKDOWN_STATE_FILE = "lockdown.json"
BOT_LOGS_CHANNEL_ID = 1360344042705256660

# 📢 Channels that get the Embed + The Role Ping
ANNOUNCE_CHANNELS = [1358485236073238528] 

# 💬 Channels that ONLY get the Embed (No Ping)
GENERAL_CHANNELS = [
    1358452494660796448, # SFW General
    1358487735811182682  # NSFW General
]

# 🔔 The Role to Ping in Announce Channels
PING_ROLE_ID = 1363972415822237747

ADMIN_ROLE_IDS = {
    1358472511133585564,  # Admin
    1358472635234779207,  # Sr Admin
    1358473248534167663   # Owner
}

class Lockdown(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = self._load_state()

    # -------------------------------
    # 🔐 State Helpers
    # -------------------------------

    def _load_state(self):
        # We replaced "reason" and "updated_at" with an "updates" list
        default_state = {"enabled": False, "issuer": None, "updates": []}
        if os.path.isfile(LOCKDOWN_STATE_FILE):
            try:
                with open(LOCKDOWN_STATE_FILE, "r") as f:
                    data = json.load(f)
                    
                    # Migration catch: just in case the file still has the old format
                    if "reason" in data and "updates" not in data:
                        data["updates"] = [{
                            "msg": data["reason"], 
                            "time": data.get("updated_at", 0), 
                            "user": data.get("issuer", "Unknown")
                        }] if data.get("reason") else []
                        
                    return {**default_state, **data} 
            except Exception:
                return default_state
        return default_state

    def _save_state(self):
        with open(LOCKDOWN_STATE_FILE, "w") as f:
            json.dump(self.state, f)

    # -------------------------------
    # 🔐 Permission Helpers
    # -------------------------------

    def is_admin(self, member: discord.Member) -> bool:
        return any(role.id in ADMIN_ROLE_IDS for role in member.roles)

    # -------------------------------
    # 🚨 Lockdown Command
    # -------------------------------

    @app_commands.command(
        name="lockdown",
        description="Toggle server lockdown (Auto-kick, pause invites)."
    )
    @app_commands.describe(reason="Reason for the lockdown (Only used when turning it ON).")
    async def lockdown_cmd(self, interaction: discord.Interaction, reason: str = "Emergency security situation. No specific reason provided."):
        # 🔐 Admin+ check
        if not self.is_admin(interaction.user):
            return await interaction.response.send_message(
                "🚫 Admins only.",
                ephemeral=True
            )

        is_currently_locked = self.state["enabled"]
        action = "disable" if is_currently_locked else "enable"
        title = f"⚠️ Confirm {action.capitalize()} Lockdown"

        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=15)
                self.value = None

            @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
            async def confirm(self, i: discord.Interaction, _):
                self.value = True
                await i.response.defer()
                self.stop()

            @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
            async def cancel(self, i: discord.Interaction, _):
                self.value = False
                await i.response.defer()
                self.stop()

        view = ConfirmView()
        
        # Show prompt text based on whether we are turning it on or off
        prompt_text = f"{title}\nAre you sure you want to **{action}** lockdown mode?"
        if not is_currently_locked:
            prompt_text += f"\n**Reason:** {reason}"

        await interaction.response.send_message(prompt_text, view=view)

        await view.wait()

        msg = await interaction.original_response()
        for btn in view.children:
            btn.disabled = True
        await msg.edit(view=view)

        if view.value is None:
            return await interaction.followup.send("⌛ Timed out.", ephemeral=True)
        if view.value is False:
            return await interaction.followup.send("❌ Cancelled.", ephemeral=True)

        # Toggle state & update data
        if not is_currently_locked:
            self.state["enabled"] = True
            self.state["issuer"] = interaction.user.mention
            # Start the new updates trail
            self.state["updates"] = [{
                "msg": reason,
                "time": int(discord.utils.utcnow().timestamp()),
                "user": interaction.user.mention
            }]
        else:
            self.state["enabled"] = False
            self.state["issuer"] = None
            self.state["updates"] = []
            
        self._save_state()

        # 🛑 Pause or unpause invites
        try:
            await interaction.guild.edit(invites_disabled=self.state["enabled"])
        except discord.Forbidden:
            print("❌ Bot lacks 'Manage Server' permission to toggle invites.")
        except Exception as e:
            print(f"❌ Failed to toggle invites: {e}")

        state_msg = (
            "🔒 Lockdown enabled. Auto-kick active and invites paused."
            if self.state["enabled"] else
            "🔓 Lockdown lifted. Normal operations and invites resumed."
        )
        await interaction.followup.send(state_msg)

        # Build the Embed
        if self.state["enabled"]:
            embed = discord.Embed(
                title="🚨 Server Lockdown Activated",
                description=(
                    "**Effective Immediately:** The server is now under **emergency lockdown**.\n\n"
                    "🛑 **Server invites have been temporarily paused.**\n"
                    "🛡️ **Security verification has been elevated to MAXIMUM (Verified phone number required).**\n"
                    "❌ New members attempting to join will be **automatically removed**.\n\n"
                    "Please remain patient while staff resolves the situation. Further updates will follow.\n"
                    "🔎 **You can check the update of the lockdown at any time with `/lockdownstatus`.**"
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text="This action was taken to ensure server safety.")
        else:
            embed = discord.Embed(
                title="✅ Server Lockdown Lifted",
                description="The server has returned to normal operations. Invites are open and security has been restored to standard levels.",
                color=discord.Color.green()
            )
            embed.set_footer(text="Lockdown deactivated.")

        # 1️⃣ Send to Announce Channels (WITH PING)
        ping_content = f"<@&{PING_ROLE_ID}>"
        for cid in ANNOUNCE_CHANNELS:
            try:
                announce_channel = interaction.guild.get_channel(cid)
                if announce_channel:
                    await announce_channel.send(content=ping_content, embed=embed)
            except Exception as e:
                print(f"❌ Failed to announce in channel {cid}: {e}")

        # 2️⃣ Send to General Channels (NO PING)
        for cid in GENERAL_CHANNELS:
            try:
                general_channel = interaction.guild.get_channel(cid)
                if general_channel:
                    await general_channel.send(embed=embed)
            except Exception as e:
                print(f"❌ Failed to send to general channel {cid}: {e}")

        # Log action
        try:
            log = interaction.guild.get_channel(BOT_LOGS_CHANNEL_ID)
            if log:
                await log.send(
                    f"{'🔒 Lockdown mode **ENABLED** (Invites paused)' if self.state['enabled'] else '🔓 Lockdown mode **DISABLED** (Invites restored)'} "
                    f"by {interaction.user.mention}."
                )
        except Exception as e:
            print(f"❌ Failed to log lockdown toggle: {e}")

    # -------------------------------
    # ✏️ Update Lockdown Command
    # -------------------------------
    
    @app_commands.command(
        name="updatelockdown",
        description="Add a new update to the active lockdown trail."
    )
    @app_commands.describe(message="The new update message for users to see.")
    async def update_lockdown(self, interaction: discord.Interaction, message: str):
        # 🔐 Admin+ check
        if not self.is_admin(interaction.user):
            return await interaction.response.send_message(
                "🚫 Admins only.",
                ephemeral=True
            )
            
        if not self.state["enabled"]:
            return await interaction.response.send_message(
                "🚫 The server is not currently in lockdown.", 
                ephemeral=True
            )
            
        # Append the new update to the list
        new_update = {
            "msg": message,
            "time": int(discord.utils.utcnow().timestamp()),
            "user": interaction.user.mention
        }
        self.state["updates"].append(new_update)
        self._save_state()
        
        await interaction.response.send_message(f"✅ Lockdown update added:\n> {message}", ephemeral=True)


    # -------------------------------
    # 📊 Lockdown Status
    # -------------------------------

    @app_commands.command(
        name="lockdownstatus",
        description="Check the current lockdown status and latest updates."
    )
    async def lockdown_status(self, interaction: discord.Interaction):
        if self.state["enabled"]:
            embed = discord.Embed(
                title="🔒 Active Lockdown Status", 
                color=discord.Color.red()
            )
            
            updates = self.state.get("updates", [])
            
            if not updates:
                embed.add_field(name="Lockdown Trail", value="No reasons or updates provided.", inline=False)
            else:
                # Format the trail, showing up to the last 5 updates to prevent breaking Discord's 1024 char limit
                display_updates = updates[-5:] if len(updates) > 5 else updates
                trail_text = ""
                
                if len(updates) > 5:
                    trail_text += "*...older updates hidden...*\n\n"
                    
                for i, update in enumerate(display_updates):
                    msg = update.get("msg", "Unknown update")
                    time = update.get("time", 0)
                    user = update.get("user", "Unknown Admin")
                    
                    # If it's the very first update in the entire list, call it Initial Reason
                    is_first = (len(updates) <= 5 and i == 0)
                    header = "🚨 **Initial Reason**" if is_first else "📝 **Update**"
                    
                    trail_text += f"{header} - {user} (<t:{time}:R>)\n> {msg}\n\n"
                    
                embed.add_field(name="Lockdown Trail", value=trail_text, inline=False)
                
            embed.set_footer(text="Auto-kick and invite pausing are currently active.")
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            await interaction.response.send_message("🔓 **All clear.** The server is not currently in lockdown.", ephemeral=False)

    # -------------------------------
    # 👢 Auto-kick on Join
    # -------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if self.state["enabled"]:
            try:
                await member.send(
                    "🚫 The server is currently under lockdown.\n"
                    "You were automatically removed for security reasons. Please try again later."
                )
            except Exception:
                pass

            await member.kick(
                reason="Joined during lockdown (auto-kick)"
            )

# -------------------------------
# ⚙️ Setup
# -------------------------------

async def setup(bot):
    await bot.add_cog(Lockdown(bot))