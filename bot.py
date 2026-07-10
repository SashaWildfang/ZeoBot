import discord
from discord.ext import commands, tasks
import os
import asyncio
import logging 

# Set up logging to catch library-level errors
logging.basicConfig(level=logging.INFO) 
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.WARNING)

from config import TOKEN, PREFIX
from cmds.selector import RoleView, ROLE_DATA, SummaryView, IDVerificationView, ArtistApplicationView
from cmds.nsfw_selector import NSFWView, NSFW_ROLE_DATA, NSFWSummaryView
from cmds.vc_embed import VCAcceptView

# ==========================================
# Database Connection
# ==========================================
from db.database import get_connection

# ==========================================
# Persistent Views
# ==========================================
from cmds.settings import (
    HugSettingsView,
    BoopSettingsView,
    DailyReminderView,
    MilestoneNotifyView
)

from ticketing.ui_buttons import NSFWVerifyButton, StaffApplyButton, SupportTicketButton
from ticketing.ticket_controls import TicketControlButtons
from ticketing.ticket_commands import TicketControlsView

# IMPORT: We need both the main view and the admin view for the listener
from events.member_join import VerificationView, VerificationAdminView 

from events.on_ready import StartupView


# ===========================================================
# BOT + INTENTS
# ===========================================================
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True      # <-- REQUIRED
intents.members = True
intents.presences = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


# ===========================================================
# AUTO-LOAD COGS FROM cmds/
# ===========================================================
async def load_command_cogs():
    folders_to_load = ["./cmds", "./store"]

    for folder in folders_to_load:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.endswith(".py") and not filename.startswith("__"):
                    folder_name = folder.replace("./", "") 
                    module = f"{folder_name}.{filename[:-3]}"
                    
                    try:
                        await bot.load_extension(module)
                        print(f"✅ Loaded {module}")
                    except Exception as e:
                        print(f"❌ Failed to load {module}: {e}")
        else:
            print(f"⚠️ Warning: The folder '{folder}' was not found.")


# ===========================================================
# AUTO-LOAD COGS FROM events/
# ===========================================================
async def load_event_cogs():
    if os.path.exists("./events"):
        for filename in os.listdir("./events"):
            if filename.endswith(".py") and not filename.startswith("__"):
                module = f"events.{filename[:-3]}"
                try:
                    await bot.load_extension(module)
                    print(f"✅ Loaded {module}")
                except Exception as e:
                    print(f"❌ Failed to load {module}: {e}")


# ===========================================================
# MANUAL EXTENSIONS
# ===========================================================
async def load_extensions():
    REAL_COGS = [
        "ticketing.ticket_events",   
        "ticketing.ticket_commands",
        "ticketing.ticketadmin",
        "ticketing.staff_panel",
        "ticketing.support_panel",
        "ticketing.nsfw_panel",   
    ]

    for ext in REAL_COGS:
        try:
            await bot.load_extension(ext)
            print(f"✅ Loaded {ext}")
        except Exception as e:
            print(f"❌ Failed to load {ext}: {e}")


# ===========================================================
# DYNAMIC INTERACTION LISTENER
# ===========================================================
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")
        
        if custom_id and custom_id.startswith(("v_acc_", "v_deny_", "v_ban_")):
            try:
                member_id = int(custom_id.split("_")[-1])
                view = VerificationAdminView(bot, member_id)
                bot.add_view(view)
            except Exception as e:
                print(f"Error re-registering admin view: {e}")


# ===========================================================
# BACKGROUND TASKS (UPDATES WEBSITE DB)
# ===========================================================
# ✅ Specifically targeting only your requested staff role ID
STAFF_ROLE_IDS = [1358470109965979859] 

@tasks.loop(minutes=5)
async def update_online_staff_count():
    if not hasattr(bot, 'db'):
        return

    online_count = 0
    # Loops through all guilds the bot is in
    for guild in bot.guilds:
        for member in guild.members:
            # Check if they are online/idle/dnd AND have the staff role
            if member.status != discord.Status.offline:
                if any(role.id in STAFF_ROLE_IDS for role in member.roles):
                    online_count += 1

    try:
        # Saving into a 'server_stats' collection inside your 'website' database
        stats_col = bot.db["server_stats"]
        await stats_col.update_one(
            {"_id": "live_staff_count"}, 
            {"$set": {"online_count": online_count}},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Failed to update DB with staff count: {e}")

@update_online_staff_count.before_loop
async def before_update_online_staff_count():
    await bot.wait_until_ready() # Wait until bot is fully loaded before counting


# ===========================================================
# ON READY
# ===========================================================
@bot.event
async def on_ready():
    if not hasattr(bot, "synced"):
        cmds = await bot.tree.sync()
        bot.synced = True
        print(f"📌 Synced {len(cmds)} global slash commands.")

    # Start the background task that feeds data to Next.js
    if not update_online_staff_count.is_running():
        update_online_staff_count.start()

    print(f"🤖 Zeo online as {bot.user}")
    restart_channel = bot.get_channel(1360344042705256660)
    if restart_channel:
        await restart_channel.send("✅ Zeo has restarted successfully.")


# ===========================================================
# MAIN RUNNER
# ===========================================================
async def main():
    # Connect to MongoDB and set up bot.db
    print("🗄️ Connecting to MongoDB...")
    db_instance = get_connection() 
    
    if db_instance is not None:
        # ✅ Directly attaching to the "website" database from your screenshot
        bot.db = db_instance.client["website"]
        print("✅ Database attached! Bot is currently using the 'website' database.")
    else:
        print("❌ WARNING: MongoDB failed to connect.")

    async with bot:
        print("🔧 Loading CMD cogs...")
        await load_command_cogs()

        print("🔧 Loading EVENT cogs...")
        await load_event_cogs()

        print("🔧 Loading manual extension cogs...")
        await load_extensions()

        print("🔒 Registering persistent views...")
        bot.add_view(HugSettingsView())
        bot.add_view(BoopSettingsView())
        bot.add_view(DailyReminderView())
        bot.add_view(MilestoneNotifyView())
        bot.add_view(NSFWVerifyButton())
        bot.add_view(StaffApplyButton()) 
        bot.add_view(SupportTicketButton()) 
        bot.add_view(TicketControlButtons())
        bot.add_view(TicketControlsView())
        bot.add_view(StartupView(bot))

        bot.add_view(VerificationView(bot))
        bot.add_view(ArtistApplicationView())

        bot.add_view(VCAcceptView())
        bot.add_view(SummaryView())
        bot.add_view(IDVerificationView())
        for category in ROLE_DATA.keys():
            bot.add_view(RoleView(category))

        bot.add_view(NSFWSummaryView())
        for category in NSFW_ROLE_DATA.keys():
            bot.add_view(NSFWView(category))

        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped.")