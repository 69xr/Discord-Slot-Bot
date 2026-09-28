import asyncio
import logging
import sys
import discord
from discord import app_commands
from discord.ext import commands

from config import config
from db import init_db, get_all_slots
from views import SlotView

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("slotbot")

class SlotBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            help_command=None,
        )

    async def setup_hook(self):
        log.info("Initializing database...")
        init_db()

        # Load Cog
        await self.load_extension("cogs")
        log.info("Loaded cogs module.")

        # Register persistent UI views for database slots across restarts
        from views import SlotView, RenewalDMView
        slots = get_all_slots()
        for row in slots:
            self.add_view(SlotView(dict(row)))
            self.add_view(RenewalDMView(row["id"]))
        log.info(f"Registered {len(slots)} persistent slot & renewal views.")

        # Command Tree Sync
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Synced commands to guild ID: {config.GUILD_ID}")
        else:
            await self.tree.sync()
            log.info("Synced global slash commands.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="slots & pings ✨",
            )
        )

bot = SlotBot()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You do not have permission to execute this command."
    elif isinstance(error, app_commands.BotMissingPermissions):
        msg = "❌ Bot lacks required channel/guild permissions."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s."
    else:
        log.error(f"App command error: {error}")
        msg = "❌ An error occurred processing this command."

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

def main():
    if not config.TOKEN:
        log.error("DISCORD_TOKEN missing in environment settings.")
        raise SystemExit("❌ DISCORD_TOKEN missing")

    try:
        bot.run(config.TOKEN)
    except KeyboardInterrupt:
        log.info("Bot shutting down gracefully.")

if __name__ == "__main__":
    main()
