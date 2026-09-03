import asyncio
import logging
import re
import os
import sys
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_TOKEN, BOT_PREFIX, EMBED_COLOR
from spotify_helper import SpotifyHelper
from music_player import GuildMusicPlayer, MusicControlView

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("UgineSongBot")

# Enable required intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

# Dictionary mapping Guild ID -> GuildMusicPlayer
guild_players = {}

def get_player(guild: discord.Guild) -> GuildMusicPlayer:
    if guild.id not in guild_players:
        guild_players[guild.id] = GuildMusicPlayer(bot, guild)
    return guild_players[guild.id]


from aiohttp import web

async def start_web_health_server():
    """Start HTTP health check server so cloud hosting (Render Web Services, Koyeb, etc.) pass port binding checks."""
    try:
        app = web.Application()
        app.router.add_get('/', lambda r: web.Response(text="🟢 Ugine Song Bot is Online!"))
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"🌐 Web Health Check server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start web health server: {e}")


@bot.event
async def on_ready():
    logger.info(f"🟢 Bot logged in successfully as {bot.user} (ID: {bot.user.id})")
    
    # Start Web Health Server for Render Web Service Port Binding
    asyncio.create_task(start_web_health_server())

    # Set bot activity presence
    activity = discord.Activity(type=discord.ActivityType.listening, name="🎵 Spotify & YouTube | /play")
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Register persistent view for music control buttons
    for player in guild_players.values():
        bot.add_view(MusicControlView(player))

    # Sync slash commands globally
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Synced {len(synced)} Slash Commands globally.")
    except Exception as e:
        logger.error(f"❌ Failed to sync slash commands: {e}")


# Helper to join voice channel
async def ensure_voice_connection(interaction_or_ctx, player: GuildMusicPlayer) -> bool:
    user = interaction_or_ctx.user if hasattr(interaction_or_ctx, 'user') else interaction_or_ctx.author
    guild = interaction_or_ctx.guild
    
    if not user.voice or not user.voice.channel:
        msg = "❌ You must be connected to a Voice Channel first!"
        if isinstance(interaction_or_ctx, discord.Interaction):
            if interaction_or_ctx.response.is_done():
                await interaction_or_ctx.followup.send(msg, ephemeral=True)
            else:
                await interaction_or_ctx.response.send_message(msg, ephemeral=True)
        else:
            await interaction_or_ctx.send(msg)
        return False

    voice_channel = user.voice.channel
    
    # Check guild voice client from discord's state
    voice_client = guild.voice_client
    if voice_client is None or not voice_client.is_connected():
        try:
            player.voice_client = await voice_channel.connect(timeout=15.0, reconnect=True)
        except discord.ClientException:
            player.voice_client = guild.voice_client
        except Exception as e:
            logger.error(f"Failed to connect to voice channel: {e}")
            msg = f"❌ Failed to join voice channel: {e}"
            if isinstance(interaction_or_ctx, discord.Interaction):
                await interaction_or_ctx.followup.send(msg, ephemeral=True)
            else:
                await interaction_or_ctx.send(msg)
            return False
    else:
        player.voice_client = voice_client
        if voice_client.channel != voice_channel:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                logger.error(f"Failed to move voice channel: {e}")

    return True


# ==========================================
# 🎵 SLASH COMMANDS
# ==========================================

@bot.tree.command(name="play", description="Play a song or playlist from YouTube or Spotify link / title query.")
@app_commands.describe(query="Song title, YouTube link, or Spotify track/playlist link")
async def slash_play(interaction: discord.Interaction, query: str):
    # Defer IMMEDIATELY with safety check for interaction token expiration
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
    except discord.NotFound:
        logger.warning("Interaction token expired before deferral could complete.")
    except Exception as defer_err:
        logger.error(f"Error deferring interaction: {defer_err}")
    
    player = get_player(interaction.guild)

    if not await ensure_voice_connection(interaction, player):
        return

    try:
        added_tracks = await player.add_track_or_playlist(query, interaction.user, interaction.channel)
        
        if not added_tracks:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Could not find or process audio for that query/link.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Could not find or process audio for that query/link.", ephemeral=True)
            return

        if len(added_tracks) == 1:
            track = added_tracks[0]
            if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
                embed = discord.Embed(
                    title="🎶 Added to Queue",
                    description=f"[{track.display_title}]({track.webpage_url})\nDuration: `{track.formatted_duration}`",
                    color=EMBED_COLOR
                )
                embed.set_thumbnail(url=track.thumbnail)
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.response.send_message(embed=embed)
            else:
                if interaction.response.is_done():
                    await interaction.followup.send(f"🔍 **Loading and playing:** [{track.display_title}]({track.webpage_url})...")
                else:
                    await interaction.response.send_message(f"🔍 **Loading and playing:** [{track.display_title}]({track.webpage_url})...")
                await player.play_next()
        else:
            if interaction.response.is_done():
                await interaction.followup.send(f"📚 **Queued {len(added_tracks)} tracks** from playlist/album!")
            else:
                await interaction.response.send_message(f"📚 **Queued {len(added_tracks)} tracks** from playlist/album!")
            if player.voice_client and not player.voice_client.is_playing() and not player.voice_client.is_paused():
                await player.play_next()

    except Exception as e:
        logger.error(f"Error in slash_play: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        except Exception:
            pass




@bot.tree.command(name="pause", description="Pause the currently playing song.")
async def slash_pause(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    if player.voice_client and player.voice_client.is_playing():
        player.voice_client.pause()
        await interaction.response.send_message("⏸️ **Playback paused.**")
    else:
        await interaction.response.send_message("⚠️ Nothing is playing to pause.", ephemeral=True)


@bot.tree.command(name="resume", description="Resume playback if paused.")
async def slash_resume(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    if player.voice_client and player.voice_client.is_paused():
        player.voice_client.resume()
        await interaction.response.send_message("▶️ **Playback resumed.**")
    else:
        await interaction.response.send_message("⚠️ Playback is not paused.", ephemeral=True)


@bot.tree.command(name="skip", description="Skip the current song.")
async def slash_skip(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
        track_title = player.current_track.display_title if player.current_track else "Song"
        player.voice_client.stop()
        await interaction.response.send_message(f"⏭️ **Skipped:** {track_title}")
    else:
        await interaction.response.send_message("⚠️ Nothing is playing to skip.", ephemeral=True)


@bot.tree.command(name="stop", description="Stop playback, clear queue, and leave voice channel.")
async def slash_stop(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    await player.stop()
    await interaction.response.send_message("⏹️ **Stopped playback and cleared the queue.**")


@bot.tree.command(name="shuffle", description="Shuffle the current music queue.")
async def slash_shuffle(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    if not player.queue:
        await interaction.response.send_message("⚠️ Queue is empty!", ephemeral=True)
        return
    player.shuffle_queue()
    await interaction.response.send_message(f"🔀 **Shuffled {len(player.queue)} tracks in queue!**")


@bot.tree.command(name="queue", description="View the current song queue.")
async def slash_queue(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    
    if not player.current_track and not player.queue:
        await interaction.response.send_message("📄 The music queue is currently empty.", ephemeral=True)
        return

    embed = discord.Embed(title="📜 Ugine Song's Queue", color=EMBED_COLOR)
    
    if player.current_track:
        embed.add_field(
            name="Now Playing",
            value=f"▶️ [{player.current_track.display_title}]({player.current_track.webpage_url}) | `{player.current_track.formatted_duration}`",
            inline=False
        )

    if player.queue:
        queue_text = ""
        for idx, track in enumerate(player.queue[:10], start=1):
            queue_text += f"`{idx}.` [{track.display_title}]({track.webpage_url}) - `{track.formatted_duration}`\n"
        if len(player.queue) > 10:
            queue_text += f"\n*...and {len(player.queue) - 10} more tracks.*"
        embed.add_field(name="Up Next", value=queue_text, inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="nowplaying", description="Show details of the currently playing track.")
async def slash_nowplaying(interaction: discord.Interaction):
    player = get_player(interaction.guild)
    if not player.current_track:
        await interaction.response.send_message("⚠️ Nothing is currently playing.", ephemeral=True)
        return
    
    await player.send_now_playing_embed()
    await interaction.response.send_message("📌 Sent Now Playing interface!", ephemeral=True)


# ==========================================
# 💬 PREFIX COMMANDS & AUTO-LINK DETECTOR
# ==========================================

@bot.command(name="play", aliases=["p"])
async def prefix_play(ctx: commands.Context, *, query: str):
    player = get_player(ctx.guild)

    if not await ensure_voice_connection(ctx, player):
        return

    msg = await ctx.send("🔍 Resolving song details...")
    added_tracks = await player.add_track_or_playlist(query, ctx.author, ctx.channel)

    if not added_tracks:
        await msg.edit(content="❌ Could not find or process audio for that query/link.")
        return

    if len(added_tracks) == 1:
        track = added_tracks[0]
        if player.voice_client.is_playing() or player.voice_client.is_paused():
            embed = discord.Embed(
                title="🎶 Added to Queue",
                description=f"[{track.display_title}]({track.webpage_url})\nDuration: `{track.formatted_duration}`",
                color=EMBED_COLOR
            )
            embed.set_thumbnail(url=track.thumbnail)
            await ctx.send(embed=embed)
            await msg.delete()
        else:
            await msg.delete()
            await player.play_next()
    else:
        await msg.edit(content=f"📚 **Queued {len(added_tracks)} tracks** from playlist/album!")
        if not player.voice_client.is_playing() and not player.voice_client.is_paused():
            await player.play_next()


@bot.command(name="skip", aliases=["s"])
async def prefix_skip(ctx: commands.Context):
    player = get_player(ctx.guild)
    if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
        track_title = player.current_track.display_title if player.current_track else "Song"
        player.voice_client.stop()
        await ctx.send(f"⏭️ **Skipped:** {track_title}")


@bot.command(name="stop", aliases=["leave", "disconnect"])
async def prefix_stop(ctx: commands.Context):
    player = get_player(ctx.guild)
    await player.stop()
    await ctx.send("⏹️ **Playback stopped and queue cleared.**")


@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Auto link playback detector when pasting YouTube or Spotify links directly
    content = message.content.strip()
    url_pattern = re.compile(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be|open\.spotify\.com)/\S+')
    match = url_pattern.search(content)

    # Check if message starts with prefix or is a plain URL and user is in a voice channel
    if match and message.author.voice and message.author.voice.channel:
        # Avoid double handling if user typed prefix !play <url>
        if not content.startswith(BOT_PREFIX):
            url = match.group(0)
            ctx = await bot.get_context(message)
            player = get_player(message.guild)
            if await ensure_voice_connection(ctx, player):
                added_tracks = await player.add_track_or_playlist(url, message.author, message.channel)
                if added_tracks and not player.voice_client.is_playing() and not player.voice_client.is_paused():
                    await player.play_next()

    # Process standard commands
    await bot.process_commands(message)


# Entry Point
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n" + "="*70)
        print("❌ ERROR: DISCORD_BOT_TOKEN is missing or not configured!")
        print("Please edit the '.env' file and set your token:")
        print("DISCORD_BOT_TOKEN=your_actual_bot_token_here")
        print("="*70 + "\n")
        sys.exit(1)

    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()
