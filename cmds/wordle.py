import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import random
import os
from datetime import datetime, timedelta
import pytz
from db.database import get_connection

# ==========================================
# CONFIGURATION & WORD LOADING
# ==========================================
LEAF_REWARD = 300
XP_REWARD = 300
MAX_GUESSES = 6
WORDS_FILE = "wordle_words.txt"

# Load words into memory on startup
WORD_LIST = []
try:
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().upper()
                if 4 <= len(w) <= 7:
                    WORD_LIST.append(w)
        print(f"🟩 Loaded {len(WORD_LIST)} valid Wordle words (4-7 letters).")
    else:
        print(f"⚠️ {WORDS_FILE} not found. Using fallback words.")
        WORD_LIST = ["LEAF", "GAMES", "DISCORD", "APPLE", "ORANGE", "GAMER"]
except Exception as e:
    print(f"❌ Error loading Wordle words: {e}")
    WORD_LIST = ["LEAF", "GAMES", "DISCORD"]


# ==========================================
# WORDLE LOGIC EVALUATOR
# ==========================================
def evaluate_guess(guess: str, target: str) -> list[str]:
    """Returns a list of emojis 🟩, 🟨, ⬛ for a guess compared to the target."""
    result = ['⬛'] * len(guess)
    target_letters = list(target)

    # First pass: Exact matches (Green)
    for i in range(len(guess)):
        if guess[i] == target[i]:
            result[i] = '🟩'
            target_letters[i] = None  # Mark letter as used

    # Second pass: Wrong position (Yellow)
    for i in range(len(guess)):
        if result[i] == '⬛' and guess[i] in target_letters:
            result[i] = '🟨'
            target_letters[target_letters.index(guess[i])] = None  # Mark as used

    return result

def generate_board_embed(user: discord.Member, target: str, guesses: list, force_game_over: bool = False) -> discord.Embed:
    """Generates the game board embed based on current DB state."""
    is_win = guesses and guesses[-1] == target
    is_loss = len(guesses) >= MAX_GUESSES and not is_win
    
    # Treat the game as over if they won, naturally lost, OR clicked give up
    is_game_over = is_win or is_loss or force_game_over

    embed = discord.Embed(color=discord.Color.brand_green())
    embed.set_thumbnail(url=user.display_avatar.url)
    
    # Custom Titles & Colors for Game States
    if is_win:
        guess_word = "Guess" if len(guesses) == 1 else "Guesses"
        embed.title = f"🏆 Word Solved in {len(guesses)} {guess_word}"
        embed.color = discord.Color.green()
    elif is_loss or force_game_over:
        embed.title = "💀 Game Over: You Lost"
        embed.color = discord.Color.red()
    else:
        embed.title = "<:leaf:1524758896659660831> Daily Wordle"
    
    desc = ""
    
    # Render past guesses (always visible)
    for guess in guesses:
        spaced_word = " ".join([f":regional_indicator_{c.lower()}:" for c in guess])
        colors = evaluate_guess(guess, target)
        color_str = " ".join(colors)
        desc += f"{spaced_word}\n{color_str}\n\n"
            
    # Only render empty slots and dead letters if the game is actively being played
    if not is_game_over:
        # Render empty slots
        empty_rows = MAX_GUESSES - len(guesses)
        target_len = len(target)
        for _ in range(empty_rows):
            desc += " ".join(["⬛"] * target_len) + "\n\n"

        # Calculate and display dead letters
        if guesses:
            guessed_letters = set("".join(guesses))
            target_letters = set(target)
            wrong_letters = sorted(list(guessed_letters - target_letters))
            
            if wrong_letters:
                desc += f"🔴 **Letters not in word:** {', '.join(wrong_letters)}\n\n"

    embed.description = desc.strip()
    
    # Only show the footer info while the game is actively being played
    if not is_game_over:
        empty_rows = MAX_GUESSES - len(guesses)
        embed.set_footer(text=f"Guesses left: {empty_rows} | Word Length: {len(target)}")
    else:
        embed.set_footer(text=None)
    
    return embed


# ==========================================
# CONFIRMATION VIEW FOR GIVING UP
# ==========================================
class ConfirmGiveUpView(View):
    def __init__(self, db, original_message):
        super().__init__(timeout=60)
        self.db = db
        self.original_message = original_message

    @discord.ui.button(label="Confirm Give Up", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        user_doc = await self.db.wordle.find_one({"discordId": interaction.user.id})
        
        # Extra security check in case they somehow clicked it after game ended
        if not user_doc or not user_doc.get("wordle_active"):
            return await interaction.response.edit_message(content="❌ Your game is already over.", view=None)

        target = user_doc.get("wordle_target")
        guesses = user_doc.get("wordle_guesses", [])
        
        # 1. Update Game State & Set 24hr Timer
        next_ts = int((datetime.now(pytz.utc) + timedelta(hours=24)).timestamp())
        
        await self.db.wordle.update_one(
            {"discordId": interaction.user.id},
            {
                "$set": {
                    "wordle_active": False,
                    "next_wordle_time": next_ts
                }
            }
        )

        # 2. Generate the game over board (passing force_game_over=True to hide blank boxes)
        embed = generate_board_embed(interaction.user, target, guesses, force_game_over=True)
        embed.title = "💀 Game Over: You Gave Up"
        embed.description = f"**The word was: {target}**\n\n⏱️ **Next Wordle:** <t:{next_ts}:R>"

        # 3. Disable all buttons on the original message
        original_view = WordleView()
        for child in original_view.children: 
            child.disabled = True

        # 4. Edit the original message to show they lost
        try:
            await self.original_message.edit(embed=embed, view=original_view)
        except Exception:
            pass # Failsafe just in case the original message was deleted

        # 5. Clear the ephemeral confirmation menu
        await interaction.response.edit_message(content="✅ You surrendered. The game board has been updated.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Give up cancelled. Keep guessing!", view=None)


# ==========================================
# MODAL FOR TYPING GUESSES
# ==========================================
class WordleModal(Modal):
    def __init__(self, target: str, db, guess_count: int):
        current_guess = guess_count + 1
        if current_guess >= MAX_GUESSES:
            modal_title = "LAST GUESS"
        else:
            modal_title = f"Guess #{current_guess} of {MAX_GUESSES}"
            
        super().__init__(title=modal_title)
        
        self.target = target
        self.db = db
        
        target_len = len(target)
        self.guess_input = TextInput(
            label=f"Enter a {target_len}-letter word",
            style=discord.TextStyle.short,
            min_length=target_len,
            max_length=target_len,
            required=True
        )
        self.add_item(self.guess_input)

    async def on_submit(self, interaction: discord.Interaction):
        guess = self.guess_input.value.strip().upper()

        # Input Validation: Must be strictly letters A-Z
        if not guess.isalpha():
            return await interaction.response.send_message("❌ Your guess must only contain letters (A-Z)!", ephemeral=True)

        # 1. Fetch current game state from DB
        user_doc = await self.db.wordle.find_one({"discordId": interaction.user.id})
        if not user_doc or not user_doc.get("wordle_active"):
            return await interaction.response.send_message("❌ Your game is no longer active.", ephemeral=True)

        guesses = user_doc.get("wordle_guesses", [])
        
        # Duplicate Guess Prevention
        if guess in guesses:
            return await interaction.response.send_message(f"❌ You already guessed **{guess}**! Try a different word.", ephemeral=True)
        
        guesses.append(guess)
        
        is_win = (guess == self.target)
        is_loss = (len(guesses) >= MAX_GUESSES and not is_win)

        embed = generate_board_embed(interaction.user, self.target, guesses)
        view = WordleView() # The persistent view

        # 2. Handle Win, Loss, or Continue
        if is_win:
            # Calculate exactly 24 hours from right now
            next_ts = int((datetime.now(pytz.utc) + timedelta(hours=24)).timestamp())
            
            # Append Rewards Summary directly to the clear board
            embed.description = (
                f"**The word was: {self.target}**\n\n"
                f"🎉 **Rewards Summary**\n"
                f"+{LEAF_REWARD} <:leaf:1524758896659660831>\n"
                f"+{XP_REWARD} 🌟\n\n"
                f"⏱️ **Next Wordle:** <t:{next_ts}:R>"
            )
            
            # --- 1. Update Game State & Set 24hr Timer ---
            await self.db.wordle.update_one(
                {"discordId": interaction.user.id},
                {
                    "$set": {
                        "wordle_active": False,
                        "next_wordle_time": next_ts
                    },
                    "$push": {"wordle_guesses": guess}
                }
            )

            # --- 2. Add Leaves securely to the USERS DB ---
            await self.db.users.update_one(
                {"discordId": interaction.user.id},
                {"$inc": {"balance": LEAF_REWARD}},
                upsert=True
            )

            # --- 3. Route XP & Balance exactly through your leveling manager! ---
            if hasattr(interaction.client, "leveling"):
                await interaction.client.leveling.add_xp(
                    member=interaction.user, 
                    xp_gain=XP_REWARD, 
                    balance_gain=LEAF_REWARD
                )
            else:
                await self.db.users.update_one(
                    {"discordId": interaction.user.id},
                    {"$inc": {"xp": XP_REWARD, "totalXp": XP_REWARD}}
                )

            for child in view.children: child.disabled = True
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif is_loss:
            # Set the exact 24hr timer for losing as well
            next_ts = int((datetime.now(pytz.utc) + timedelta(hours=24)).timestamp())
            
            # Append the lost word and timer to the clear board
            embed.description = f"**The word was: {self.target}**\n\n⏱️ **Next Wordle:** <t:{next_ts}:R>"
            
            await self.db.wordle.update_one(
                {"discordId": interaction.user.id},
                {
                    "$set": {
                        "wordle_active": False,
                        "next_wordle_time": next_ts
                    },
                    "$push": {"wordle_guesses": guess}
                }
            )
            
            for child in view.children: child.disabled = True
            await interaction.response.edit_message(embed=embed, view=view)
            
        else:
            # Continue active game
            await self.db.wordle.update_one(
                {"discordId": interaction.user.id},
                {"$push": {"wordle_guesses": guess}}
            )
            await interaction.response.edit_message(embed=embed, view=view)


# ==========================================
# INTERACTIVE VIEW (PERSISTENT)
# ==========================================
class WordleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Make a Guess", style=discord.ButtonStyle.primary, custom_id="wordle_guess_btn_persistent")
    async def guess_button(self, interaction: discord.Interaction, button: Button):
        
        db = get_connection()
        user_doc = await db.wordle.find_one({"discordId": interaction.user.id})

        # --- INVISIBLE SECURITY CHECK ---
        if not user_doc or not user_doc.get("wordle_active") or user_doc.get("message_id") != interaction.message.id:
            return await interaction.response.send_message(
                "❌ This is not your active Wordle board! Run `/wordle` to start or resume your game.", 
                ephemeral=True
            )
        # --------------------------------

        target = user_doc.get("wordle_target")
        guesses = user_doc.get("wordle_guesses", [])
        
        # Pass the current guess count to the modal
        await interaction.response.send_modal(WordleModal(target, db, len(guesses)))

    @discord.ui.button(label="Give Up", style=discord.ButtonStyle.danger, custom_id="wordle_giveup_btn_persistent")
    async def giveup_button(self, interaction: discord.Interaction, button: Button):
        
        db = get_connection()
        user_doc = await db.wordle.find_one({"discordId": interaction.user.id})

        # --- INVISIBLE SECURITY CHECK ---
        if not user_doc or not user_doc.get("wordle_active") or user_doc.get("message_id") != interaction.message.id:
            return await interaction.response.send_message(
                "❌ This is not your active Wordle board! Run `/wordle` to start or resume your game.", 
                ephemeral=True
            )
        # --------------------------------

        # Pop up the ephemeral confirmation menu
        await interaction.response.send_message(
            "⚠️ **Are you sure you want to give up?** This will count as a loss.",
            view=ConfirmGiveUpView(db, interaction.message),
            ephemeral=True
        )


# ==========================================
# COMMAND COG
# ==========================================
class WordleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.bot.add_view(WordleView())

    @app_commands.command(name="wordle", description="Play the Daily Wordle for Leaves and XP!")
    async def wordle(self, interaction: discord.Interaction):
        user_doc = await self.db.wordle.find_one({"discordId": interaction.user.id})
        now_ts = int(datetime.now(pytz.utc).timestamp())

        if not WORD_LIST:
            return await interaction.response.send_message("❌ Wordle is currently unavailable (no words loaded).", ephemeral=True)

        is_active = user_doc.get("wordle_active", False) if user_doc else False
        next_time = user_doc.get("next_wordle_time", 0) if user_doc else 0

        # 1. 24-Hour Cooldown Check
        if not is_active and now_ts < next_time:
            return await interaction.response.send_message(
                f"❌ You have already completed a Wordle recently!\nCome back <t:{next_time}:R> for a new word.", 
                ephemeral=True
            )

        # 2. If they need a new game
        if not is_active:
            daily_word = random.choice(WORD_LIST)

            await self.db.wordle.update_one(
                {"discordId": interaction.user.id},
                {
                    "$set": {
                        "wordle_active": True,
                        "wordle_target": daily_word,
                        "wordle_guesses": [],
                        "message_id": None
                    }
                },
                upsert=True
            )
            target = daily_word
            guesses = []
        else:
            # 3. Resume an active game
            target = user_doc.get("wordle_target")
            guesses = user_doc.get("wordle_guesses", [])

        # Send the game board UI
        embed = generate_board_embed(interaction.user, target, guesses)
        view = WordleView()
        
        await interaction.response.send_message(embed=embed, view=view)
        
        # --- UPDATE MESSAGE ID FOR SECURITY ---
        msg = await interaction.original_response()
        await self.db.wordle.update_one(
            {"discordId": interaction.user.id},
            {"$set": {"message_id": msg.id}}
        )

async def setup(bot):
    await bot.add_cog(WordleCog(bot))