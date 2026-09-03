import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

# UI Styling matching the requested design
EMBED_COLOR = 0xE74C3C  # Red primary accent color
SPOTIFY_ICON_URL = "https://cdn-icons-png.flaticon.com/512/174/174872.png"
YOUTUBE_ICON_URL = "https://cdn-icons-png.flaticon.com/512/1384/1384060.png"
DEFAULT_THUMBNAIL = "https://cdn-icons-png.flaticon.com/512/3844/3844724.png"

# Ultra-Fast yt-dlp Configuration
YTDL_OPTIONS = {
    'format': 'ba/b',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
    'youtube_include_dash_manifest': False,
    'youtube_include_hls_manifest': False,
    'player_client': ['android', 'web'],
    'skip_download': True,
    'cachedir': False,
    'geo_bypass': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32768 -analyzeduration 0',
    'options': '-vn -loglevel quiet',
}

