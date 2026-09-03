import re
import urllib.parse
import urllib.request
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("SpotifyHelper")

class SpotifyTrackInfo:
    def __init__(self, title: str, artist: str, thumbnail: Optional[str] = None, url: Optional[str] = None):
        self.title = title
        self.artist = artist
        self.thumbnail = thumbnail or ""
        self.url = url or ""

    @property
    def query(self) -> str:
        if self.artist:
            return f"{self.title} - {self.artist}"
        return self.title


class SpotifyHelper:
    SPOTIFY_TRACK_REGEX = re.compile(r'https?://open\.spotify\.com(?:/embed)?/track/([a-zA-Z0-9]+)')
    SPOTIFY_ALBUM_REGEX = re.compile(r'https?://open\.spotify\.com(?:/embed)?/album/([a-zA-Z0-9]+)')
    SPOTIFY_PLAYLIST_REGEX = re.compile(r'https?://open\.spotify\.com(?:/embed)?/playlist/([a-zA-Z0-9]+)')

    @classmethod
    def is_spotify_url(cls, url: str) -> bool:
        return bool(
            cls.SPOTIFY_TRACK_REGEX.search(url) or 
            cls.SPOTIFY_ALBUM_REGEX.search(url) or 
            cls.SPOTIFY_PLAYLIST_REGEX.search(url)
        )

    @classmethod
    def get_spotify_track_info(cls, url: str) -> Optional[SpotifyTrackInfo]:
        """Fetch track metadata using Spotify's public oEmbed API."""
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
            req = urllib.request.Request(
                oembed_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                title = data.get('title', 'Unknown Track')
                artist = data.get('author_name', '')
                thumbnail = data.get('thumbnail_url', '')

                # Cleanup title if author name is appended
                if artist and artist in title:
                    title_clean = title.replace(f"by {artist}", "").replace(f"- {artist}", "").strip()
                else:
                    title_clean = title

                return SpotifyTrackInfo(
                    title=title_clean,
                    artist=artist,
                    thumbnail=thumbnail,
                    url=url
                )
        except Exception as e:
            logger.error(f"Error fetching Spotify track oEmbed info: {e}")
            return None

    @classmethod
    def get_spotify_playlist_or_album_tracks(cls, url: str) -> List[SpotifyTrackInfo]:
        """Extract tracks from Spotify playlist or album web page."""
        tracks: List[SpotifyTrackInfo] = []
        try:
            req = urllib.request.Request(
                url, 
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
                # Extract image thumbnail
                img_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                thumbnail = img_match.group(1) if img_match else ""

                # Look for track names embedded in JSON or meta tags
                # Try finding script tag with __NEXT_DATA__ or initial state
                next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', html)
                if next_data:
                    try:
                        raw_json = json.loads(next_data.group(1))
                        # Navigate JSON structure for track items
                        # Different Spotify page schemas contain tracks array
                        items = cls._find_tracks_in_json(raw_json)
                        for item in items:
                            if item.get('name'):
                                artists = ", ".join([a.get('name', '') for a in item.get('artists', []) if a.get('name')])
                                tracks.append(SpotifyTrackInfo(
                                    title=item.get('name'),
                                    artist=artists,
                                    thumbnail=thumbnail,
                                    url=url
                                ))
                    except Exception as json_err:
                        logger.warning(f"Could not parse Spotify JSON data: {json_err}")

                # Fallback: Parse meta tags or music:song elements
                if not tracks:
                    title_matches = re.findall(r'<meta name="music:song" content="([^"]+)"', html)
                    if not title_matches:
                        # Extract titles from fallback list tags
                        titles = re.findall(r'<span class="tracklist-name[^"]*">([^<]+)</span>', html)
                        for title in titles:
                            tracks.append(SpotifyTrackInfo(title=title.strip(), artist="", thumbnail=thumbnail, url=url))

        except Exception as e:
            logger.error(f"Error fetching Spotify playlist/album tracks: {e}")

        # If empty fallback, try single track resolution
        if not tracks:
            single = cls.get_spotify_track_info(url)
            if single:
                tracks.append(single)

        return tracks

    @classmethod
    def _find_tracks_in_json(cls, data: dict) -> list:
        """Recursively search for track objects in nested Spotify JSON."""
        tracks = []
        if isinstance(data, dict):
            if data.get('type') == 'track' and 'name' in data:
                tracks.append(data)
            for key, val in data.items():
                if isinstance(val, (dict, list)):
                    tracks.extend(cls._find_tracks_in_json(val))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    tracks.extend(cls._find_tracks_in_json(item))
        return tracks
