import asyncio
import random
import logging
import gc
import discord
import yt_dlp
from typing import List, Optional, Dict
from config import EMBED_COLOR, SPOTIFY_ICON_URL, YOUTUBE_ICON_URL, DEFAULT_THUMBNAIL, YTDL_OPTIONS, FFMPEG_OPTIONS
from spotify_helper import SpotifyHelper, SpotifyTrackInfo

logger = logging.getLogger("MusicPlayer")
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

fallback_ytdl = yt_dlp.YoutubeDL({
    'format': 'best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
        }
    },
})

def safe_extract_info(target: str) -> dict:
    try:
        return ytdl.extract_info(target, download=False)
    except Exception as e:
        logger.warning(f"Primary extraction failed for '{target}' ({e}), trying fallback...")
        try:
            return fallback_ytdl.extract_info(target, download=False)
        except Exception as ex:
            logger.error(f"Fallback extraction also failed for '{target}': {ex}")
            raise ex

def format_duration(duration_seconds: int) -> str:
    if not duration_seconds or duration_seconds <= 0:
        return "Live Stream"
    minutes, seconds = divmod(int(duration_seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes:02d}m {seconds:02d}s"


class SongTrack:
    def __init__(self, title: str, webpage_url: str, stream_url: str, duration: int, 
                 thumbnail: str, requester: discord.Member, is_spotify: bool = False, 
                 spotify_artist: str = ""):
        self.title = title
        self.webpage_url = webpage_url
        self.stream_url = stream_url
        self.duration = duration
        self.formatted_duration = format_duration(duration)
        self.thumbnail = thumbnail or DEFAULT_THUMBNAIL
        self.requester = requester
        self.is_spotify = is_spotify
        self.spotify_artist = spotify_artist

    @property
    def display_title(self) -> str:
        if self.is_spotify and self.spotify_artist:
            return f"{self.title} - {self.spotify_artist}"
        return self.title


class MusicControlView(discord.ui.View):
    def __init__(self, guild_player):
        super().__init__(timeout=None)
        self.player = guild_player

    async def _check_voice_user(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must be in a voice channel to use music controls!", ephemeral=True)
            return False
        if self.player.voice_client and interaction.user.voice.channel != self.player.voice_client.channel:
            await interaction.response.send_message("❌ You must be in the same voice channel as the bot!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.danger, emoji="⏸️", custom_id="music_btn_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice_user(interaction):
            return

        vc = self.player.voice_client
        if vc and vc.is_playing():
            vc.pause()
            button.label = "Resume"
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ **Playback paused.**", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            button.label = "Pause"
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("▶️ **Playback resumed.**", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Nothing is currently playing.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.danger, emoji="⏭️", custom_id="music_btn_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice_user(interaction):
            return

        vc = self.player.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            current_title = self.player.current_track.display_title if self.player.current_track else "Song"
            vc.stop()
            await interaction.response.send_message(f"⏭️ **Skipped:** {current_title}", ephemeral=False)
        else:
            await interaction.response.send_message("⚠️ Nothing is currently playing to skip.", ephemeral=True)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.danger, emoji="🔀", custom_id="music_btn_shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice_user(interaction):
            return

        if not self.player.queue:
            await interaction.response.send_message("⚠️ The queue is empty, cannot shuffle!", ephemeral=True)
            return

        self.player.shuffle_queue()
        await interaction.response.send_message(f"🔀 **Shuffled {len(self.player.queue)} tracks in queue!**", ephemeral=False)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="music_btn_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice_user(interaction):
            return

        await self.player.stop()
        await interaction.response.send_message("⏹️ **Playback stopped and queue cleared.**", ephemeral=False)

    @discord.ui.button(label="Like", style=discord.ButtonStyle.danger, emoji="❤️", custom_id="music_btn_like")
    async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.player.current_track
        if not current:
            await interaction.response.send_message("⚠️ No song is playing right now.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id not in self.player.liked_songs:
            self.player.liked_songs[user_id] = []

        if any(t.webpage_url == current.webpage_url for t in self.player.liked_songs[user_id]):
            await interaction.response.send_message("❤️ This song is already in your Liked list!", ephemeral=True)
            return

        self.player.liked_songs[user_id].append(current)
        
        try:
            embed = discord.Embed(
                title="❤️ Added to your Liked Songs",
                description=f"[{current.display_title}]({current.webpage_url})",
                color=EMBED_COLOR
            )
            embed.set_thumbnail(url=current.thumbnail)
            await interaction.user.send(embed=embed)
        except Exception:
            pass

        await interaction.response.send_message(f"❤️ **Liked!** Saved [{current.display_title}]({current.webpage_url}) to your favorites.", ephemeral=True)


def extract_best_stream_url(entry: dict) -> str:
    if not entry:
        return ""
    if entry.get('url'):
        return entry['url']
    if entry.get('formats'):
        for f in reversed(entry['formats']):
            if f.get('vcodec') == 'none' and f.get('url'):
                return f['url']
        for f in reversed(entry['formats']):
            if f.get('url'):
                return f['url']
    return ""


SONG_CACHE: Dict[str, dict] = {}

def add_to_song_cache(key: str, val: dict):
    if len(SONG_CACHE) > 30:
        first_key = next(iter(SONG_CACHE))
        SONG_CACHE.pop(first_key, None)
    SONG_CACHE[key] = val
    gc.collect()


class GuildMusicPlayer:
    def __init__(self, bot: discord.Client, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: List[SongTrack] = []
        self.current_track: Optional[SongTrack] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.now_playing_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.liked_songs: Dict[int, List[SongTrack]] = {}
        self.loop = asyncio.get_event_loop()

    def shuffle_queue(self):
        random.shuffle(self.queue)

    async def add_track_or_playlist(self, query: str, requester: discord.Member, text_channel: discord.TextChannel) -> List[SongTrack]:
        self.text_channel = text_channel
        added_tracks: List[SongTrack] = []

        if SpotifyHelper.is_spotify_url(query):
            if "playlist" in query or "album" in query:
                sp_tracks = SpotifyHelper.get_spotify_playlist_or_album_tracks(query)
                if sp_tracks:
                    first_track = await self._resolve_search_to_track(sp_tracks[0].query, requester, is_spotify=True, sp_info=sp_tracks[0])
                    if first_track:
                        self.queue.append(first_track)
                        added_tracks.append(first_track)
                    
                    for sp_t in sp_tracks[1:]:
                        lazy_track = SongTrack(
                            title=sp_t.title,
                            webpage_url=sp_t.url or "",
                            stream_url="",
                            duration=0,
                            thumbnail=sp_t.thumbnail or DEFAULT_THUMBNAIL,
                            requester=requester,
                            is_spotify=True,
                            spotify_artist=sp_t.artist
                        )
                        self.queue.append(lazy_track)
                        added_tracks.append(lazy_track)
            else:
                sp_t = SpotifyHelper.get_spotify_track_info(query)
                if sp_t:
                    track = await self._resolve_search_to_track(sp_t.query, requester, is_spotify=True, sp_info=sp_t)
                    if track:
                        self.queue.append(track)
                        added_tracks.append(track)
        else:
            try:
                tracks = await self._extract_yt_info(query, requester)
                for t in tracks:
                    self.queue.append(t)
                    added_tracks.append(t)
            except Exception as e:
                logger.error(f"Error extracting YouTube info for '{query}': {e}")

        asyncio.create_task(self._prefetch_queue())
        return added_tracks

    async def _resolve_search_to_track(self, search_query: str, requester: discord.Member, 
                                        is_spotify: bool = False, sp_info: Optional[SpotifyTrackInfo] = None) -> Optional[SongTrack]:
        loop = asyncio.get_event_loop()
        cache_key = search_query.strip().lower()

        if cache_key in SONG_CACHE:
            cached = SONG_CACHE[cache_key]
            return SongTrack(
                title=sp_info.title if (is_spotify and sp_info) else cached['title'],
                webpage_url=sp_info.url if (is_spotify and sp_info and sp_info.url) else cached['webpage_url'],
                stream_url=cached['stream_url'],
                duration=cached['duration'],
                thumbnail=sp_info.thumbnail if (is_spotify and sp_info and sp_info.thumbnail) else cached['thumbnail'],
                requester=requester,
                is_spotify=is_spotify,
                spotify_artist=sp_info.artist if (is_spotify and sp_info) else ""
            )

        try:
            search_target = f"ytsearch1:{search_query}"
            data = await loop.run_in_executor(None, lambda: safe_extract_info(search_target))
            
            if not data or ('entries' in data and not data['entries']):
                logger.warning(f"No results found for: {search_query}")
                return None

            first = data['entries'][0] if ('entries' in data and data['entries']) else data
            yt_webpage = first.get('webpage_url', f"https://www.youtube.com/watch?v={first.get('id')}")
            stream_url = extract_best_stream_url(first)

            title = sp_info.title if (is_spotify and sp_info) else first.get('title', 'Unknown Title')
            webpage_url = sp_info.url if (is_spotify and sp_info and sp_info.url) else yt_webpage
            duration = first.get('duration', 0)
            thumbnail = sp_info.thumbnail if (is_spotify and sp_info and sp_info.thumbnail) else first.get('thumbnail', DEFAULT_THUMBNAIL)
            artist = sp_info.artist if (is_spotify and sp_info) else ""

            SONG_CACHE[cache_key] = {
                'title': title,
                'webpage_url': yt_webpage,
                'stream_url': stream_url,
                'duration': duration,
                'thumbnail': thumbnail
            }

            return SongTrack(
                title=title,
                webpage_url=webpage_url,
                stream_url=stream_url or "",
                duration=duration,
                thumbnail=thumbnail,
                requester=requester,
                is_spotify=is_spotify,
                spotify_artist=artist
            )
        except Exception as e:
            logger.error(f"Error in _resolve_search_to_track: {e}")
            return None

    async def _extract_yt_info(self, query: str, requester: discord.Member) -> List[SongTrack]:
        loop = asyncio.get_event_loop()
        
        is_url = query.startswith("http://") or query.startswith("https://")
        search_target = query if is_url else f"ytsearch1:{query}"

        cache_key = query.strip().lower()
        if not is_url and cache_key in SONG_CACHE:
            cached = SONG_CACHE[cache_key]
            return [SongTrack(
                title=cached['title'],
                webpage_url=cached['webpage_url'],
                stream_url=cached['stream_url'],
                duration=cached['duration'],
                thumbnail=cached['thumbnail'],
                requester=requester,
                is_spotify=False
            )]

        data = await loop.run_in_executor(None, lambda: safe_extract_info(search_target))

        tracks = []
        if not data:
            return tracks

        if 'entries' in data and data['entries']:
            for entry in data['entries']:
                if not entry:
                    continue
                stream_url = extract_best_stream_url(entry)
                yt_webpage = entry.get('webpage_url', f"https://www.youtube.com/watch?v={entry.get('id')}")
                t = SongTrack(
                    title=entry.get('title', 'Unknown Title'),
                    webpage_url=yt_webpage,
                    stream_url=stream_url,
                    duration=entry.get('duration', 0),
                    thumbnail=entry.get('thumbnail', DEFAULT_THUMBNAIL),
                    requester=requester,
                    is_spotify=False
                )
                tracks.append(t)
        else:
            yt_webpage = data.get('webpage_url', f"https://www.youtube.com/watch?v={data.get('id')}")
            stream_url = extract_best_stream_url(data)
            t = SongTrack(
                title=data.get('title', 'Unknown Title'),
                webpage_url=yt_webpage,
                stream_url=stream_url,
                duration=data.get('duration', 0),
                thumbnail=data.get('thumbnail', DEFAULT_THUMBNAIL),
                requester=requester,
                is_spotify=False
            )
            tracks.append(t)

        return tracks

    async def _prefetch_queue(self):
        if not self.queue:
            return
        loop = asyncio.get_event_loop()
        for track in self.queue[:3]:
            if not track.stream_url:
                try:
                    target = track.webpage_url if ("youtube.com" in track.webpage_url or "youtu.be" in track.webpage_url) else f"ytsearch1:{track.display_title}"
                    data = await loop.run_in_executor(None, lambda: safe_extract_info(target))
                    if data:
                        entry = data['entries'][0] if ('entries' in data and data['entries']) else data
                        track.stream_url = extract_best_stream_url(entry)
                        if (not track.duration or track.duration == 0) and entry.get('duration'):
                            track.duration = entry.get('duration', 0)
                            track.formatted_duration = format_duration(track.duration)
                        if (not track.thumbnail or track.thumbnail == DEFAULT_THUMBNAIL) and entry.get('thumbnail'):
                            track.thumbnail = entry.get('thumbnail')
                except Exception as ex:
                    logger.debug(f"Prefetch error for {track.display_title}: {ex}")

    async def play_next(self):
        if not self.queue:
            self.current_track = None
            if self.now_playing_message:
                try:
                    await self.now_playing_message.delete()
                except Exception:
                    pass
                self.now_playing_message = None
            return

        self.current_track = self.queue.pop(0)

        loop = asyncio.get_event_loop()
        try:
            target = self.current_track.webpage_url if ("youtube.com" in self.current_track.webpage_url or "youtu.be" in self.current_track.webpage_url) else f"ytsearch1:{self.current_track.display_title}"
            data = await loop.run_in_executor(None, lambda: safe_extract_info(target))
            if data:
                entry = data['entries'][0] if ('entries' in data and data['entries']) else data
                fresh_url = extract_best_stream_url(entry)
                if fresh_url:
                    self.current_track.stream_url = fresh_url
                if (not self.current_track.duration or self.current_track.duration == 0) and entry.get('duration'):
                    self.current_track.duration = entry.get('duration', 0)
                    self.current_track.formatted_duration = format_duration(self.current_track.duration)
                if (not self.current_track.thumbnail or self.current_track.thumbnail == DEFAULT_THUMBNAIL) and entry.get('thumbnail'):
                    self.current_track.thumbnail = entry.get('thumbnail')
        except Exception as ex:
            logger.error(f"Error fetching fresh stream_url in play_next: {ex}")

        if not self.current_track.stream_url:
            logger.error(f"Could not resolve stream URL for track '{self.current_track.display_title}'. Skipping...")
            await self.play_next()
            return

        asyncio.create_task(self._prefetch_queue())

        audio_source = discord.FFmpegPCMAudio(self.current_track.stream_url, **FFMPEG_OPTIONS)
        
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("Voice client is not connected when trying to play next track.")
            return

        def after_playing(error):
            if error:
                logger.error(f"Playback error in after_playing callback: {error}")
            asyncio.run_coroutine_threadsafe(self.play_next(), self.bot.loop)

        self.voice_client.play(audio_source, after=after_playing)
        await self.send_now_playing_embed()

    async def send_now_playing_embed(self):
        if not self.current_track or not self.text_channel:
            return

        track = self.current_track
        icon_url = SPOTIFY_ICON_URL if track.is_spotify else YOUTUBE_ICON_URL

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name="Now Playing", icon_url=icon_url)
        
        description_text = (
            f"• [{track.display_title}]({track.webpage_url})\n\n"
            f"• Duration: `{track.formatted_duration}` - ({track.requester.mention})"
        )
        embed.description = description_text
        
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        view = MusicControlView(self)

        if self.now_playing_message:
            try:
                await self.now_playing_message.delete()
            except Exception:
                pass

        self.now_playing_message = await self.text_channel.send(embed=embed, view=view)

    async def stop(self):
        self.queue.clear()
        self.current_track = None
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            await self.voice_client.disconnect()
            self.voice_client = None

        if self.now_playing_message:
            try:
                await self.now_playing_message.delete()
            except Exception:
                pass
            self.now_playing_message = None
