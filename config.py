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

# yt-dlp config — uses android + web clients (confirmed working)
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    'extractor_retries': 5,
    'retries': 10,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
        }
    },
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 10000000',
    'options': '-vn -bufsize 512k',
}
