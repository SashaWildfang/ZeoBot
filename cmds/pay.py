import discord
from discord.ext import commands
from discord import app_commands

from db.database import get_connection

# Your Discord ID
ADMIN_ID = 164577223162986498

class Pay(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def db(self):
        return get_connection()

    @app_commands.command(name="pay", description="Send Leaves to another user.")
    @app_commands.describe(user="The user to pay", amount="The amount of Leaves to send")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        sender = interaction.user

        # Basic validation
        if user.id == sender.id:
            await interaction.response.send_message("❌ You can't pay yourself!", ephemeral=True)
            return
            
        if user.bot:
            await interaction.response.send_message("❌ You cannot send Leaves to bots!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
            return
            
        # Prevent paying the admin/owner
        if user.id == ADMIN_ID:
            await interaction.response.send_message("❌ You cannot pay this user.", ephemeral=True)
            return

        users = self.db()["users"]
        globals_col = self.db()["globals"]

        # Fetch sender balance
        sender_doc = await users.find_one({"discordId": sender.id}, {"balance": 1})
        sender_balance = sender_doc.get("balance", 0) if sender_doc else 0

        # Check if the sender is the admin (Infinite money bypass)
        is_admin = (sender.id == ADMIN_ID)

        # Insufficient funds check (Admin bypasses this)
        if not is_admin and sender_balance < amount:
            await interaction.response.send_message(
                f"❌ You don't have enough Leaves. Current balance: **{sender_balance:,} <:leaf:1524758896659660831>**",
                ephemeral=True
            )
            return

        # Calculate 5% tax
        tax = int(amount * 0.05)
        net_amount = amount - tax

        # Perform atomic updates
        try:
            # 1. Deduct from sender (Skip if sender is admin to preserve infinite funds)
            if not is_admin:
                await users.update_one(
                    {"discordId": sender.id},
                    {"$inc": {"balance": -amount}},
                    upsert=True
                )

            # 2. Add to recipient (net amount after tax)
            await users.update_one(
                {"discordId": user.id},
                {"$inc": {"balance": net_amount}},
                upsert=True
            )
            
            # 3. Add tax to the casino jackpot
            if tax > 0:
                await globals_col.update_one(
                    {"_id": "casino_jackpot"},
                    {"$inc": {"amount": tax}},
                    upsert=True
                )

            # Build the success message
            msg = f"{sender.mention} sent **{net_amount:,} <:leaf:1524758896659660831>** to {user.mention}!"
            if tax > 0:
                msg += f"\n*(A 5% tax of **{tax:,} <:leaf:1524758896659660831>** went towards the server jackpot)*"

            await interaction.response.send_message(
                msg,
                allowed_mentions=discord.AllowedMentions(users=[user])
            )

        except Exception as e:
            print(f"❌ MongoDB error in /pay: {e}")
            await interaction.response.send_message(
                "⚠️ Something went wrong while processing the payment.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Pay(bot))