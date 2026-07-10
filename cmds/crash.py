import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import math
import time
from datetime import datetime
from pymongo import ReturnDocument
from db.database import get_connection

# --- CONFIGURATION ---
MIN_BET = 25
MAX_MULTIPLIER = 100.0  # Cap the multiplier so the bot doesn't get stuck in a 10,000x loop

class CrashView(discord.ui.View):
    def __init__(self, cog, original_interaction, user, bet):
        super().__init__(timeout=90.0) 
        self.cog = cog
        self.original_interaction = original_interaction
        self.user = user
        self.bet = bet
        self.current_mult = 1.0
        self.cashed_out = False
        self.crashed = False
        
        # Dynamically set the initial button label to show the wager return (Using text "Leaves" for button support)
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "crash_cashout":
                child.label = f"💸 Cash Out (+{self.bet:,} Leaves)"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="💸 Cash Out", style=discord.ButtonStyle.success, custom_id="crash_cashout")
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prevent double-clicking or cashing out after a crash
        if self.cashed_out or self.crashed:
            return await interaction.response.defer()
            
        self.cashed_out = True
        
        # Disable the button immediately
        for child in self.children:
            child.disabled = True
            
        # Resolve the win (this will edit the message using the new interaction)
        await self.cog.resolve_win(interaction, self.user, self.bet, self.current_mult, self)


class Crash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]
        self.logs_col = self.db["gambling_logs"]
        self.globals_col = self.db["globals"]

    def generate_crash_point(self) -> float:
        """
        Generates a crash point using an inverse proportional formula.
        Creates a high frequency of low crashes, and a rare frequency of huge crashes.
        """
        e = 0.95 
        r = random.random()
        
        # Prevent division by zero
        if r == 0: r = 0.0001
        
        crash_point = e / r
        
        # Ensure the minimum crash is always at least 1.01x
        return round(max(1.01, min(crash_point, MAX_MULTIPLIER)), 2)

    def generate_text_graph(self, multiplier: float) -> str:
        """
        Creates a 2D ascii text graph that simulates the curve of a real Crash game.
        """
        height = 5
        width = 25 
        
        # Logarithmic mapping: 1x -> 0%, 10x -> ~50%, 100x -> 100%
        if multiplier <= 1.0:
            progress = 0.0
        else:
            progress = min(math.log10(multiplier) / 2.0, 1.0)
            
        rocket_x = int(progress * width)
        rocket_y = int(progress * height)
        
        lines = []
        for y in range(height, -1, -1):
            row = [" "] * (width + 2)
            if y == rocket_y:
                # Place the rocket
                row[rocket_x] = "🚀"
            elif y < rocket_y:
                # Draw the trail line tracing up to the rocket
                path_x = int((y / rocket_y) * rocket_x) if rocket_y > 0 else 0
                row[path_x] = "╱"
                
            lines.append("│" + "".join(row))
            
        # Bottom axis
        lines.append("└" + "─" * (width + 2))
        return "```text\n" + "\n".join(lines) + "\n```"

    async def add_to_jackpot(self, amount: int):
        """Atomically adds lost bets to the global casino jackpot."""
        await self.globals_col.find_one_and_update(
            {"_id": "casino_jackpot"},
            {"$inc": {"amount": amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

    def build_embed(self, user, bet, multiplier, status):
        color = discord.Color.blurple()
        graph_str = self.generate_text_graph(multiplier)
        
        if status == "rising":
            title = "🚀 Crash | Rising..."
            desc = (
                f"Multiplier: **{multiplier:.2f}x**\n\n"
                f"{graph_str}\n\n"
                f"*Click the button below to cash out before it crashes!*"
            )
        elif status == "cashed_out":
            color = discord.Color.green()
            title = "💸 Crash | Cashed Out!"
            payout = int(bet * multiplier)
            desc = (
                f"You safely bailed at **{multiplier:.2f}x**!\n\n"
                f"{graph_str}\n\n"
                f"**You won {payout:,} <:leaf:1524758896659660831>!**"
            )
        elif status == "crashed":
            color = discord.Color.red()
            title = "💥 Game Over, Crash!"
            crashed_graph = graph_str.replace("🚀", "💥")
            desc = (
                f"The rocket exploded at **{multiplier:.2f}x**!\n\n"
                f"{crashed_graph}\n\n"
                f"**You lost {bet:,} <:leaf:1524758896659660831>**"
            )

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        return embed

    async def update_gambling_stats(self, user_id: int, spent: int, won: int, final_string: str):
        net = won - spent
        now = datetime.utcnow()
        stats = await self.gambling_col.find_one({"discordId": user_id}) or {}
        
        biggest_win = stats.get("biggest_win", 0)
        biggest_loss = stats.get("biggest_loss", 0)
        
        if won > biggest_win: biggest_win = won
        if net < biggest_loss: biggest_loss = net 

        update_data = {
            "$inc": {"total_spent": spent, "total_won": won, "net_profit": net, "total_spins": 1},
            "$set": {"biggest_win": biggest_win, "biggest_loss": biggest_loss}
        }

        if net > 0:
            update_data["$set"]["last_win"] = {"amount": net, "symbols": final_string, "timestamp": now}
        elif net < 0:
            update_data["$set"]["last_loss"] = {"amount": net, "symbols": final_string, "timestamp": now}

        await self.gambling_col.update_one({"discordId": user_id}, update_data, upsert=True)
        await self.logs_col.insert_one({
            "discordId": user_id, "spent": spent, "won": won, "net": net, 
            "symbols": final_string, "timestamp": now, "game": "crash"
        })

    async def resolve_win(self, interaction, user, bet, multiplier, view):
        payout = int(bet * multiplier)
        
        await self.users_col.update_one({"discordId": user.id}, {"$inc": {"balance": payout}})
        await self.update_gambling_stats(user.id, bet, payout, f"CRASH: {multiplier:.2f}x")
        
        embed = self.build_embed(user, bet, multiplier, "cashed_out")
        await interaction.response.edit_message(embed=embed, view=view)

    async def resolve_loss(self, interaction, user, bet, crash_point, view):
        await self.update_gambling_stats(user.id, bet, 0, f"CRASH: 💥 {crash_point:.2f}x")
        await self.add_to_jackpot(bet) # Add lost bet to global jackpot
        
        for child in view.children:
            child.disabled = True
            
        embed = self.build_embed(user, bet, crash_point, "crashed")
        
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except discord.errors.NotFound:
            pass 

    # ==========================================
    # THE UNIFIED /CRASH COMMAND
    # ==========================================
    @app_commands.command(name="crash", description="Play Crash or view the odds.")
    @app_commands.describe(
        action="Select an action",
        bet="Amount to wager (e.g. 25, 'all', 'half')"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🚀 Play", value="play"),
        app_commands.Choice(name="📊 View Odds", value="odds")
    ])
    async def crash(self, interaction: discord.Interaction, action: str, bet: str = "25"):
        if action == "play":
            await self._handle_play(interaction, bet)
        elif action == "odds":
            await self._handle_odds(interaction)

    # --- ACTION HANDLERS ---

    async def _handle_play(self, interaction: discord.Interaction, bet_str: str):
        await interaction.response.defer()
        user_id = interaction.user.id

        user_data = await self.users_col.find_one({"discordId": user_id})
        current_balance = user_data.get("balance", 0) if user_data else 0

        # Parse the custom bet string ("all", "half", or integer)
        bet_str = str(bet_str).lower().strip()
        if bet_str == "all":
            bet = current_balance
        elif bet_str == "half":
            bet = current_balance // 2
        else:
            try:
                bet = int(bet_str)
            except ValueError:
                return await interaction.followup.send("Error: Wager must be a valid number, 'all', or 'half'.", ephemeral=True)

        if bet < MIN_BET:
            return await interaction.followup.send(f"Error: Minimum wager is {MIN_BET} <:leaf:1524758896659660831>.", ephemeral=True)

        if current_balance < bet:
            return await interaction.followup.send(
                f"Error: Insufficient funds. Required: {bet:,} <:leaf:1524758896659660831>. Balance: {current_balance:,} <:leaf:1524758896659660831>", 
                ephemeral=True
            )

        await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": -bet}})

        crash_point = self.generate_crash_point()
        view = CrashView(self, interaction, interaction.user, bet)

        embed = self.build_embed(interaction.user, bet, 1.00, "rising")
        await interaction.followup.send(embed=embed, view=view)

        # The Smooth Time-Based Crash Loop
        start_time = time.time()
        current_mult = 1.00
        
        while current_mult < crash_point:
            # 1.2 seconds is the fastest safe loop rate in Discord (Limits are 5 edits / 5 seconds)
            await asyncio.sleep(1.2)
            
            if view.cashed_out:
                return 
                
            # Time-based continuous curve (m = e^(rt)). 
            # 0.15 rate = Hits ~2x at 4.5s, 10x at 15s, 100x at 30s. Perfect real-time feel.
            elapsed = time.time() - start_time
            current_mult = round(math.exp(elapsed * 0.15), 2)
            
            if current_mult >= crash_point:
                view.crashed = True
                await self.resolve_loss(interaction, interaction.user, bet, crash_point, view)
                return
                
            view.current_mult = current_mult
            
            # Update the button label with the current real-time payout value
            current_payout = int(bet * current_mult)
            for child in view.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == "crash_cashout":
                    child.label = f"💸 Cash Out (+{current_payout:,} Leaves)"
            
            embed = self.build_embed(interaction.user, bet, current_mult, "rising")
            
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except discord.errors.HTTPException:
                pass 
            except discord.errors.NotFound:
                return 

    async def _handle_odds(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Crash Odds & Rules",
            description="Welcome to Crash. Here is how the rocket flies and how your odds are calculated.",
            color=discord.Color.blurple()
        )
        
        embed.add_field(
            name="📜 Server Rules",
            value=(
                f"• Minimum Bet: **{MIN_BET} <:leaf:1524758896659660831>**\n"
                "• You must click **Cash Out** before the multiplier crashes.\n"
                "• All losing wagers are deposited into the **Global Slots Jackpot**."
            ),
            inline=False
        )
        
        embed.add_field(
            name="📈 Statistical Probabilities",
            value=(
                "• **The Curve:** The game uses an inverse proportional curve. Lower multipliers are common, while huge multipliers become exponentially rarer.\n"
                f"• **Minimum Win:** The rocket will always clear at least **1.01x**.\n"
                f"• **Maximum Win:** The rocket is hard-capped at **{MAX_MULTIPLIER}x** to prevent infinite loops."
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Crash(bot))