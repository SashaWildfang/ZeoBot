import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import datetime
from pymongo import ReturnDocument
from db.database import get_connection

# --- CONFIGURATION ---
MIN_BET = 25
JACKPOT_CONTRIBUTION = 1.0  # 100% of losing bets goes to the global jackpot (adjust if needed)
BASE_JACKPOT = 100000

# Custom Result Emotes (Matching your existing ecosystem)
EMOTE_YES = "<:yes:1506394068513722428>"
EMOTE_UP = "<:up:1506396328559906886>"
EMOTE_DOWN = "<:down:1506396307470680246>"
EMOTE_EQUAL = "<:equal:1506394051409346724>"
EMOTE_BLUE_EQUAL = "<:blue_equal:1506397046754775080>"

# Roulette Colors and Payouts
COLOR_EMOJIS = {
    "red": "🟥",
    "black": "⬛",
    "green": "🟩"
}

PAYOUTS = {
    "red": 2,    # 1:1 payout (returns original bet + 1x profit)
    "black": 2,  # 1:1 payout
    "green": 36  # 35:1 payout (Standard European Roulette odds for 0)
}

# Wheel probabilities (Standard European Roulette: 18 Red, 18 Black, 1 Green)
WHEEL_WEIGHTS = {
    "red": 18,
    "black": 18,
    "green": 1
}

class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.users_col = self.db["users"]
        self.gambling_col = self.db["gambling"]
        self.globals_col = self.db["globals"]
        self.logs_col = self.db["gambling_logs"]

    async def get_or_create_jackpot(self):
        """Fetches the current global jackpot or creates it if it doesn't exist."""
        data = await self.globals_col.find_one({"_id": "casino_jackpot"})
        if not data:
            await self.globals_col.insert_one({"_id": "casino_jackpot", "amount": BASE_JACKPOT})
            return BASE_JACKPOT
        return data.get("amount", BASE_JACKPOT)

    async def add_to_jackpot(self, amount: int) -> int:
        """Atomically adds a portion of lost bets to the global jackpot and returns the new total."""
        result = await self.globals_col.find_one_and_update(
            {"_id": "casino_jackpot"},
            {"$inc": {"amount": amount}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return result.get("amount", BASE_JACKPOT) if result else BASE_JACKPOT

    async def update_gambling_stats(self, user_id: int, spent: int, won: int, final_string: str):
        """Updates lifetime stats, tracks extreme highs/lows, and logs history."""
        net = won - spent
        now = datetime.utcnow()
        stats = await self.gambling_col.find_one({"discordId": user_id}) or {}
        
        biggest_win = stats.get("biggest_win", 0)
        biggest_loss = stats.get("biggest_loss", 0)
        
        if won > biggest_win:
            biggest_win = won
        if net < biggest_loss:
            biggest_loss = net 

        update_data = {
            "$inc": {
                "total_spent": spent,
                "total_won": won,
                "net_profit": net,
                "total_spins": 1
            },
            "$set": {
                "biggest_win": biggest_win,
                "biggest_loss": biggest_loss
            }
        }

        if net > 0:
            update_data["$set"]["last_win"] = {"amount": net, "symbols": final_string, "timestamp": now}
        elif net < 0:
            update_data["$set"]["last_loss"] = {"amount": net, "symbols": final_string, "timestamp": now}

        await self.gambling_col.update_one({"discordId": user_id}, update_data, upsert=True)
        await self.logs_col.insert_one({
            "discordId": user_id, "spent": spent, "won": won, "net": net, 
            "symbols": final_string, "timestamp": now, "game": "roulette"
        })

    def roll_wheel(self) -> str:
        """Rolls the roulette wheel and returns the winning color."""
        colors = list(WHEEL_WEIGHTS.keys())
        weights = list(WHEEL_WEIGHTS.values())
        return random.choices(colors, weights=weights, k=1)[0]

    def generate_sliding_frames(self, final_color: str, num_frames: int = 4) -> list:
        """Generates a list of strings simulating a sliding roulette wheel."""
        frames = []
        
        # Standard alternating pattern for the blur effect
        pattern = ["red", "black", "red", "black", "red", "black"]
        
        for i in range(num_frames - 1):
            # Pick a random 5-color slice to simulate fast spinning
            start = random.randint(0, 1)
            slice_colors = pattern[start:start+5]
            
            # Occasionally inject a green for realism during the spin
            if random.random() < 0.2:
                slice_colors[random.randint(0, 4)] = "green"
                
            frame_str = " | ".join([COLOR_EMOJIS[c] for c in slice_colors])
            frames.append(f"**[** {frame_str} **]**")

        # The final frame locks the winning color in the exact center (index 2)
        final_slice = [
            random.choice(["red", "black"]),
            random.choice(["red", "black"]),
            final_color,
            random.choice(["red", "black"]),
            random.choice(["red", "black"])
        ]
        
        final_frame_str = " | ".join([COLOR_EMOJIS[c] for c in final_slice])
        frames.append(f"**[** {final_frame_str} **]**")
        
        return frames

    def build_embed(self, user, bet_amount, bet_color, status, frame_text, payout=0):
        color = discord.Color.blurple()
        
        # Displaying the pointer arrow below the center slot
        pointer = "         ⬆️" 
        
        if status == "spinning":
            title = "🎡 Roulette | Spinning..."
            desc = (
                f"You bet **{bet_amount:,} <:leaf:1524758896659660831>** on {COLOR_EMOJIS[bet_color]} **{bet_color.title()}**\n\n"
                f"{frame_text}\n"
                f"{pointer}"
            )
        else:
            net = payout - bet_amount
            if net > 0:
                color = discord.Color.green()
                title = "🎡 Roulette | Winner!"
                result_text = f"{EMOTE_YES} The ball landed on {COLOR_EMOJIS[status]} **{status.title()}**!"
            else:
                color = discord.Color.red()
                title = "🎡 Roulette | Loss"
                result_text = f"❌ The ball landed on {COLOR_EMOJIS[status]} **{status.title()}**."

            desc = (
                f"{frame_text}\n"
                f"{pointer}\n\n"
                f"{result_text}"
            )

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        if status != "spinning":
            embed.add_field(name="Wager", value=f"<:leaf:1524758896659660831> {bet_amount:,}", inline=True)
            embed.add_field(name="Return", value=f"<:leaf:1524758896659660831> {payout:,}", inline=True)
            
            net = payout - bet_amount
            if net > 0:
                net_str = f"{EMOTE_UP} +{net:,}"
            elif net < 0:
                net_str = f"{EMOTE_DOWN} {net:,}"
            else:
                net_str = f"{EMOTE_BLUE_EQUAL} 0"
                
            embed.add_field(name="Earnings", value=net_str, inline=True)
            
        return embed

    @app_commands.command(name="roulette", description="Bet your Leaves on Red, Black, or Green!")
    @app_commands.describe(
        color="Choose a color to bet on",
        bet="Amount to wager (e.g. 25, 'all', 'half')"
    )
    @app_commands.choices(color=[
        app_commands.Choice(name="🟥 Red (2x Payout)", value="red"),
        app_commands.Choice(name="⬛ Black (2x Payout)", value="black"),
        app_commands.Choice(name="🟩 Green (36x Payout)", value="green")
    ])
    async def roulette(self, interaction: discord.Interaction, color: str, bet: str = "25"):
        await interaction.response.defer()
        user_id = interaction.user.id

        user_data = await self.users_col.find_one({"discordId": user_id})
        current_balance = user_data.get("balance", 0) if user_data else 0

        # Parse the wager input
        bet_str = str(bet).lower().strip()
        if bet_str == "all":
            bet_amount = current_balance
        elif bet_str == "half":
            bet_amount = current_balance // 2
        else:
            try:
                bet_amount = int(bet_str)
            except ValueError:
                return await interaction.followup.send("Error: Wager must be a valid number, 'all', or 'half'.", ephemeral=True)

        if bet_amount < MIN_BET:
            return await interaction.followup.send(f"Error: Minimum wager is {MIN_BET} <:leaf:1524758896659660831>.", ephemeral=True)

        if current_balance < bet_amount:
            return await interaction.followup.send(
                f"Error: Insufficient funds. Required: {bet_amount:,} <:leaf:1524758896659660831>. Balance: {current_balance:,} <:leaf:1524758896659660831>", 
                ephemeral=True
            )

        # Deduct initial bet
        await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": -bet_amount}})

        # Determine the outcome immediately
        winning_color = self.roll_wheel()
        frames = self.generate_sliding_frames(winning_color)
        
        # Start the spinning animation
        embed = self.build_embed(interaction.user, bet_amount, color, "spinning", frames[0])
        message = await interaction.followup.send(embed=embed)

        # Animation Loop (3 intermediate frames)
        for i in range(1, len(frames) - 1):
            await asyncio.sleep(1.2) # Discord safe limit
            embed = self.build_embed(interaction.user, bet_amount, color, "spinning", frames[i])
            try:
                await interaction.edit_original_response(embed=embed)
            except discord.errors.HTTPException:
                pass

        # Final Result Resolution
        await asyncio.sleep(1.5) # Slight suspense pause before the final frame
        
        payout = 0
        jackpot_contribution = 0
        
        if color == winning_color:
            payout = int(bet_amount * PAYOUTS[winning_color])
            await self.users_col.update_one({"discordId": user_id}, {"$inc": {"balance": payout}})
        else:
            jackpot_contribution = int(bet_amount * JACKPOT_CONTRIBUTION)
            if jackpot_contribution > 0:
                await self.add_to_jackpot(jackpot_contribution)

        # Update stats
        log_string = f"Roulette: Bet {COLOR_EMOJIS[color]} | Landed {COLOR_EMOJIS[winning_color]}"
        await self.update_gambling_stats(user_id, bet_amount, payout, log_string)
        
        # Final Embed
        final_embed = self.build_embed(interaction.user, bet_amount, color, winning_color, frames[-1], payout)
        
        # Append jackpot footer to the final embed
        current_jackpot = await self.get_or_create_jackpot()
        final_embed.set_footer(text=f"Global Jackpot: {current_jackpot:,} Leaves")

        try:
            await interaction.edit_original_response(embed=final_embed)
        except discord.errors.HTTPException:
            pass

async def setup(bot):
    await bot.add_cog(Roulette(bot))