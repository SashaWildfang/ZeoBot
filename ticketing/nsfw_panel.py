import discord
from discord.ext import commands
from db.database import get_connection
from ticketing.ui_buttons import NSFWVerifyButton

NSFW_VERIFY_CHANNEL = 1358485673991999721  # Your NSFW verification channel

class CreateNSFWPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_connection()
        self.config_col = self.db["bot_config"]  # Stores the panel message ID

    @discord.app_commands.command(
        name="create_nsfw_panel",
        description="Create or update the NSFW verification panel."
    )
    async def create_nsfw_panel(self, interaction: discord.Interaction):

        if interaction.channel_id != NSFW_VERIFY_CHANNEL:
            return await interaction.response.send_message(
                f"❌ This command can only be used in <#{NSFW_VERIFY_CHANNEL}>.",
                ephemeral=True
            )

        # Build the updated embed
        embed = discord.Embed(
            title="🔞 NSFW Verification",
            description=(
                "**Please read everything below before requesting access. Failure to follow instructions will result in an immediate ticket close.**\n\n"
                "__**1️⃣ Requirements**__\n"
                "• Must be **18+**\n"
                "• Must be **verified** in the server\n"
                "• Must agree to follow all NSFW rules\n\n"
                "__**2️⃣ Important Notes**__\n"
                "• Lying about age = **permanent ban**\n"
                "• NSFW content outside NSFW channels = punishment\n"
                "• Staff may request additional proof\n\n"
                "__**3️⃣ Verification Steps (Strictly Enforced)**__\n"
                "**Step 1:** Photo of your ID (Face + DOB must be visible) next to a piece of paper with your **Discord name**, **current date**, and **Kitty Kingdom** written on it.\n\n"
                "**Step 2:** A clear selfie of you holding that same ID.\n\n"
                "⚠️ **FACE REQUIREMENT:** You **MUST** show your face clearly in the selfie. We do **NOT** accept any alternative forms of verification. No voice clips, no redacted faces, and no exceptions.\n\n"
                "_Everything is deleted immediately after review._\n\n"
                "__**4️⃣ Start Application**__\n"
                "⛔ **STOP:** Ensure you have read and understood the requirements above. If you cannot provide the required photos, do not open a ticket.\n\n"
                "Click **Request NSFW Access** to begin."
            ),
            color=0xE57373  # light red
        )

        await interaction.response.defer(ephemeral=True)

        # Check if there's already a stored panel message
        panel_config = await self.config_col.find_one({"_id": "nsfw_panel"})

        channel = interaction.guild.get_channel(NSFW_VERIFY_CHANNEL)

        if panel_config and "message_id" in panel_config:
            try:
                # Fetch existing panel and update it
                msg = await channel.fetch_message(panel_config["message_id"])
                await msg.edit(embed=embed, view=NSFWVerifyButton())
                return await interaction.followup.send(
                    "🔁 Updated existing NSFW verification panel.",
                    ephemeral=True
                )
            except discord.NotFound:
                pass  # message was deleted — create a new one

        # No existing panel → create new one
        new_msg = await channel.send(embed=embed, view=NSFWVerifyButton())

        # Save the panel message ID
        await self.config_col.update_one(
            {"_id": "nsfw_panel"},
            {"$set": {"message_id": new_msg.id}},
            upsert=True
        )

        await interaction.followup.send(
            "✅ NSFW verification panel created.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(CreateNSFWPanel(bot))