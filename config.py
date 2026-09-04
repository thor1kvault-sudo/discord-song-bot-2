import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

EMBED_COLOR = 0xE74C3C
SPOTIFY_ICON_URL = "https://cdn-icons-png.flaticon.com/512/174/174872.png"
YOUTUBE_ICON_URL = "https://cdn-icons-png.flaticon.com/512/1384/1384060.png"
DEFAULT_THUMBNAIL = "https://cdn-icons-png.flaticon.com/512/3844/3844724.png"

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'skip_download': True,
    'cachedir': False,
    'geo_bypass': True,
    'extractor_retries': 3,
    'retries': 5,
    'fragment_retries': 5,
    'http_chunk_size': 10485760,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
