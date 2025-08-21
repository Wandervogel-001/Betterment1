import discord
from discord.ext import commands
import sys
import logging
from database import TeamDatabaseManager
import webserver
from config import DISCORD_TOKEN, MONGO_URI, DB_NAME
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(stream=sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

if not DISCORD_TOKEN or not MONGO_URI:
    logger.error("Missing DISCORD_TOKEN or MONGO_URI in environment variables!")
    sys.exit(1)

# Configure intents
intents = discord.Intents.default()
intents.members = True  # Required for team management
intents.message_content = True  # Required for command processing
intents.guilds = True  # Required for guild events

# Initialize bot
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Initialize database with TeamDatabaseManager
bot.db = TeamDatabaseManager(MONGO_URI, db_name=DB_NAME)

async def load_cogs(bot, logger):
    """Load all cogs from the cogs directory, including subdirectories."""
    cogs_dir = "./cogs"
    if not os.path.exists(cogs_dir):
        logger.warning("Cogs directory not found. Creating...")
        os.makedirs(cogs_dir)
        return

    loaded_count = 0
    failed_count = 0

    for item in os.listdir(cogs_dir):
        path = os.path.join(cogs_dir, item)
        if os.path.isdir(path):
            # This is a subdirectory, look for a cog.py inside
            cog_file = os.path.join(path, "cog.py")
            if os.path.exists(cog_file):
                cog_name = f"cogs.{item}.cog"
                try:
                    await bot.load_extension(cog_name)
                    logger.info(f"Loaded cog: {cog_name}")
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
                    failed_count += 1
        elif item.endswith(".py") and not item.startswith("_"):
            # This is a regular cog file
            cog_name = f"cogs.{item[:-3]}"
            try:
                await bot.load_extension(cog_name)
                logger.info(f"Loaded cog: {cog_name}")
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
                failed_count += 1

    print(f"Cog loading complete: {loaded_count} loaded, {failed_count} failed")
    print("Loaded cogs:", list(bot.cogs.keys()))


@bot.event
async def on_ready():
    try:
        logger.info(f"Bot logged in as {bot.user.name}#{bot.user.discriminator}")
        logger.info(f"Bot ID: {bot.user.id}")

        await load_cogs(bot, logger)
        logger.info(f"Connected to {len(bot.guilds)} guilds")

        synced_global = await bot.tree.sync()
        logger.info(f"Synced {len(synced_global)} global commands")

        # Restore team panels
        for cog in bot.cogs.values():
            if hasattr(cog, 'restore_team_panels'):
                await cog.restore_team_panels()

        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} servers | /help"
            )
        )

    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)

@bot.event
async def on_guild_join(guild):
    try:
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} servers | /help"
            )
        )
    except Exception as e:
        logger.error(f"Error handling guild join: {e}")

@bot.event
async def on_guild_remove(guild):
    try:
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} servers | /help"
            )
        )
    except Exception as e:
        logger.error(f"Error handling guild leave: {e}")

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Command error in {ctx.guild.name if ctx.guild else 'DM'}: {error}")
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `/help` to see available commands.", delete_after=10)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.", delete_after=10)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have the required permissions to execute this command.", delete_after=10)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏰ Command on cooldown. Try again in {error.retry_after:.1f} seconds.", delete_after=10)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: `{error.param.name}`. Use `/help {ctx.command.name}` for usage.", delete_after=15)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument provided. Use `/help {ctx.command.name}` for usage.", delete_after=15)
    else:
        await ctx.send("❌ An unexpected error occurred. Please try again later.", delete_after=10)
        logger.exception(f"Unexpected error in command {ctx.command}: {error}")

if __name__ == "__main__":
    try:
        webserver.keep_alive()
        bot.run(DISCORD_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
