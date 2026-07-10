import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta
from db.database import get_connection  # Should return a Mongo database object

REMINDER_CHANNEL_ID = 1358485891361804358
SETTINGS_CHANNEL_ID = 1382735420747419761

class DailyReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.send_reminders.start()

    def cog_unload(self):
        self.send_reminders.cancel()

    @tasks.loop(minutes=30)
    async def send_reminders(self):
        now = datetime.utcnow()
        db = get_connection()
        
        # ✅ FIX: Explicit None check to avoid NotImplementedError
        if db is None:
            return

        # Fetch users who have daily reminders enabled
        # Note: Using discordId to match your other Cogs' casing
        users_cursor = db.users.aggregate([
            {
                "$lookup": {
                    "from": "settings",
                    "localField": "discordId", 
                    "foreignField": "discordId",
                    "as": "settings"
                }
            },
            {"$unwind": "$settings"},
            {
                "$match": {
                    "settings.daily_reminder": True, 
                    "last_daily": {"$ne": None}
                }
            }
        ])

        to_notify = []
        
        # If using Motor (async driver)
        async for user_data in users_cursor:
            # ✅ Consistency Fix: Using discordId instead of discord_id
            discord_id = user_data.get("discordId")
            if not discord_id:
                continue
                
            last_daily = user_data.get("last_daily")
            last_reminded = user_data.get("last_reminded")

            try:
                if isinstance(last_daily, str):
                    last_daily = datetime.fromisoformat(last_daily)
                if last_reminded and isinstance(last_reminded, str):
                    last_reminded = datetime.fromisoformat(last_reminded)

                # logic: Daily expires after 48h. Remind if within 24h of that expiry.
                expiry_time = last_daily + timedelta(hours=48)
                within_24h = now + timedelta(hours=24) >= expiry_time > now
                not_already_reminded = not last_reminded or last_reminded < last_daily

                if within_24h and not_already_reminded:
                    to_notify.append((discord_id, now))
            except Exception as e:
                print(f"⚠️ Error processing reminder for {discord_id}: {e}")
                continue

        if not to_notify:
            return

        channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
        if not channel:
            return

        for user_id, remind_time in to_notify:
            # We use fetch_user if get_user returns None (user not in cache)
            user = self.bot.get_user(user_id)
            if not user:
                try:
                    user = await self.bot.fetch_user(user_id)
                except:
                    continue

            embed = discord.Embed(
                title="⏰ Daily Streak Reminder",
                description=(
                    f"Hey {user.mention}, your `/daily` streak will expire in less than 24 hours!\n\n"
                    f"Don't forget to claim it to keep your streak going.\n\n"
                    f"If you'd like to stop these reminders, manage your settings in <#{SETTINGS_CHANNEL_ID}>."
                ),
                color=discord.Color.orange()
            )

            try:
                await channel.send(content=user.mention, embed=embed)
                db.users.update_one(
                    {"discordId": user_id},
                    {"$set": {"last_reminded": remind_time}}
                )
            except Exception as e:
                print(f"❌ Failed to send reminder to {user_id}: {e}")
                continue

    @send_reminders.before_loop
    async def before_reminders(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(DailyReminder(bot))
    print("✅ Loaded DailyReminder Cog (Fixed Connection Check)")