import requests
from typing import Dict, Any, Optional, List
from config.config import settings


class NeteaseIntegration:
    """Integration with NetEase Cloud Music API"""

    def __init__(self):
        """Initialize NetEase integration"""
        self.api_base = settings.netease_api_url.rstrip("/")
        self.cookies = self._parse_cookie(settings.ncm_cookie)
        self.session = requests.Session()
        self.session.trust_env = False  # bypass system proxy for localhost
        print(f"NetEase API Base: {self.api_base}")
        print(f"Cookie loaded: {'Yes' if self.cookies else 'No'}")

    def _parse_cookie(self, cookie_str: str) -> Dict[str, str]:
        """Parse cookie string to dict"""
        cookies = {}
        if cookie_str:
            for item in cookie_str.split("; "):
                if "=" in item:
                    key, value = item.split("=", 1)
                    cookies[key] = value
        return cookies

    def _debug_response(self, response: requests.Response):
        """Debug response details"""
        print(f"请求URL: {response.url}")
        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers) if len(response.headers) < 10 else {k: v for k, v in list(response.headers.items())[:10]}}")
        print(f"响应编码: {response.encoding}")
        content_length = len(response.content) if response.content else 0
        print(f"响应长度: {content_length} 字节")
        if content_length > 0:
            preview = response.text[:500] if response.text else str(response.content[:500])
            print(f"响应预览: {preview}...")

    def search_tracks(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search for tracks on NetEase Cloud Music"""
        base_url = self.api_base
        endpoint = "/search"
        params = {
            "keywords": query,
            "limit": limit
        }

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return self._get_sample_tracks()

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return self._get_sample_tracks()

            print(f"API返回数据: {str(result)[:300]}...")

            tracks = []
            if result.get("code") == 200:
                for item in result.get("result", {}).get("songs", []):
                    track = self._convert_netease_track(item)
                    tracks.append(track)

            return tracks

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return self._get_sample_tracks()

    def get_track_url(self, track_id: str) -> Optional[str]:
        """Get playable URL for a track with Cookie support"""
        base_url = self.api_base
        endpoint = "/song/url"
        params = {"id": track_id, "br": 320000}

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                cookies=self.cookies,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return None

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return None

            print(f"API返回数据: {str(result)[:300]}...")

            if result.get("code") == 200 and result.get("data"):
                url = result["data"][0].get("url")
                if url:
                    print(f"获取到完整音频URL: {url[:50]}...")
                else:
                    print("警告：获取到的URL为空，可能需要登录Cookie")
                return url

            return None

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return None

    def get_track_details(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get track details from NetEase"""
        base_url = self.api_base
        endpoint = "/song/detail"
        params = {"ids": track_id}

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                cookies=self.cookies,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return None

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return None

            if result.get("code") == 200 and result.get("songs"):
                return self._convert_netease_track(result["songs"][0])

            return None

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return None

    def get_track_with_url(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get track details with playable URL"""
        track = self.get_track_details(track_id)
        if not track:
            return None

        track_url = self.get_track_url(track_id)
        if track_url:
            track["preview_url"] = track_url
            track["audio_path"] = ""

        return track

    def get_album_tracks(self, album_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get tracks from an album"""
        base_url = self.api_base
        endpoint = "/album"
        params = {"id": album_id, "limit": limit}

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                cookies=self.cookies,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return []

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return []

            tracks = []
            if result.get("code") == 200 and result.get("album"):
                for item in result["album"].get("songs", []):
                    track = self._convert_netease_track(item)
                    track["album"] = result["album"].get("name", "")
                    track["album_art"] = result["album"].get("picUrl", "")
                    tracks.append(track)

            return tracks

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return []

    def get_top_songs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top popular songs"""
        base_url = self.api_base
        endpoint = "/toplist"
        params = {"idx": 0}

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                cookies=self.cookies,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return self._get_sample_tracks()

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return self._get_sample_tracks()

            tracks = []
            if result.get("code") == 200 and result.get("playlist"):
                for item in result["playlist"].get("tracks", [])[:limit]:
                    track = self._convert_netease_track(item)
                    tracks.append(track)

            return tracks

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return self._get_sample_tracks()

    def get_new_songs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get new released songs"""
        base_url = self.api_base
        endpoint = "/top/album"
        params = {"limit": limit, "offset": 0}

        try:
            response = self.session.get(
                f"{base_url}{endpoint}",
                params=params,
                cookies=self.cookies,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )

            self._debug_response(response)
            response.raise_for_status()

            if not response.content:
                print("错误：响应体为空！")
                return self._get_sample_tracks()

            try:
                result = response.json()
            except ValueError as e:
                print(f"JSON解析失败: {e}")
                print(f"原始响应内容: {response.text[:1000]}")
                return self._get_sample_tracks()

            tracks = []
            if result.get("code") == 200 and result.get("albums"):
                tracks_collected = 0
                for album in result["albums"]:
                    if tracks_collected >= limit:
                        break
                    album_tracks = self.get_album_tracks(str(album.get("id")), limit - tracks_collected)
                    tracks.extend(album_tracks)
                    tracks_collected += len(album_tracks)

            return tracks[:limit] if tracks else self._get_sample_tracks()

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            return self._get_sample_tracks()

    def get_full_track_details(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get complete track details including URL and lyrics"""
        track = self.get_track_with_url(track_id)
        if not track:
            return None
        return track

    def add_to_library(self, track_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Add a single track to the local SQLite database"""
        from models.music import Song, Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from config.config import settings

        engine = create_engine(settings.database_url)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            track_id = str(track_data.get("id"))
            existing = session.query(Song).filter_by(id=track_id).first()
            if existing:
                session.close()
                return self._convert_netease_track({"id": track_id})

            song = Song(
                id=track_id,
                title=track_data.get("title", "Unknown"),
                artist=track_data.get("artist", []),
                album=track_data.get("album", "Unknown Album"),
                genre=track_data.get("genre", []),
                duration=track_data.get("duration", 180),
                features={
                    "album_art": track_data.get("album_art", ""),
                    "preview_url": track_data.get("preview_url", ""),
                    "external_url": track_data.get("external_url", "")
                },
                audio_path=track_data.get("audio_path", "")
            )
            session.add(song)
            session.commit()
            return self._convert_netease_track({"id": track_id})
        except Exception as e:
            session.rollback()
            print(f"Error adding track to library: {e}")
            return None
        finally:
            session.close()

    def import_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Import a single track by ID into the local database"""
        track = self.get_track_with_url(track_id)
        if not track:
            return None
        return self.add_to_library(track)

    def search_and_import_tracks(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search tracks and return with playable URLs"""
        tracks = self.search_tracks(query, limit)
        if not tracks:
            return {"tracks": [], "tracks_with_url": 0}

        tracks_with_url = 0
        for track in tracks:
            track_id = track.get("id")
            if track_id:
                track_url = self.get_track_url(str(track_id))
                if track_url:
                    track["preview_url"] = track_url
                    track["audio_path"] = ""
                    tracks_with_url += 1

        return {"tracks": tracks, "tracks_with_url": tracks_with_url}

    def import_tracks_to_database(self, tracks: List[Dict[str, Any]], session) -> Dict[str, Any]:
        """Import tracks to local database"""
        from models.music import Song

        imported = 0
        failed = 0
        duplicates = 0

        for track_data in tracks:
            try:
                track_id = str(track_data.get("id"))
                if not track_id:
                    failed += 1
                    continue

                existing = session.query(Song).filter_by(id=track_id).first()
                if existing:
                    duplicates += 1
                    continue

                song = Song(
                    id=track_id,
                    title=track_data.get("title", "Unknown"),
                    artist=track_data.get("artist", []),
                    album=track_data.get("album", "Unknown Album"),
                    genre=track_data.get("genre", []),
                    release_year=None,
                    duration=track_data.get("duration", 180),
                    features={
                        "album_art": track_data.get("album_art", ""),
                        "preview_url": track_data.get("preview_url", ""),
                        "external_url": track_data.get("external_url", "")
                    },
                    audio_path=track_data.get("audio_path", "")
                )
                session.add(song)
                imported += 1

            except Exception as e:
                print(f"Error importing track {track_data.get('id')}: {e}")
                failed += 1

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error committing transaction: {e}")

        return {
            "imported": imported,
            "duplicates": duplicates,
            "failed": failed,
            "total": len(tracks)
        }

    def _convert_netease_track(self, netease_track: Dict[str, Any]) -> Dict[str, Any]:
        """Convert NetEase track to our format"""
        return {
            "id": str(netease_track.get("id", "")),
            "title": netease_track.get("name", ""),
            "artist": [artist.get("name", "") for artist in netease_track.get("ar", [])],
            "album": netease_track.get("album", {}).get("name", ""),
            "album_art": netease_track.get("album", {}).get("picUrl", ""),
            "duration": netease_track.get("dt", 0) // 1000,
            "preview_url": "",
            "external_url": f"https://music.163.com/song/{netease_track.get('id', '')}/",
            "popularity": netease_track.get("pop", 0),
            "genre": [],
            "audio_path": ""
        }

    def _get_sample_tracks(self) -> List[Dict[str, Any]]:
        """Get sample tracks when NetEase API is not available"""
        return [
            {
                "id": "1389527957",
                "title": "晴天",
                "artist": ["周杰伦"],
                "album": "叶惠美",
                "album_art": "https://p2.music.126.net/T5xJ0T1aJb8yJb8yJb8yJb/12345678901234567.jpg",
                "duration": 269,
                "preview_url": "",
                "external_url": "https://music.163.com/song/1389527957/",
                "popularity": 95,
                "genre": ["华语流行"],
                "audio_path": ""
            },
            {
                "id": "4889223",
                "title": "平凡之路",
                "artist": ["朴树"],
                "album": "猎户星座",
                "album_art": "https://p2.music.126.net/T6xJ0T1aJb8yJb8yJb8yJb/12345678901234568.jpg",
                "duration": 302,
                "preview_url": "",
                "external_url": "https://music.163.com/song/4889223/",
                "popularity": 90,
                "genre": ["华语摇滚"],
                "audio_path": ""
            },
            {
                "id": "18291895",
                "title": "孤勇者",
                "artist": ["陈奕迅"],
                "album": "孤勇者",
                "album_art": "https://p2.music.126.net/T7xJ0T1aJb8yJb8yJb8yJb/12345678901234569.jpg",
                "duration": 262,
                "preview_url": "",
                "external_url": "https://music.163.com/song/18291895/",
                "popularity": 98,
                "genre": ["华语流行"],
                "audio_path": ""
            }
        ]


if __name__ == "__main__":
    netease = NeteaseIntegration()

    print("Searching for tracks...")
    tracks = netease.search_tracks("周杰伦", limit=5)
    for i, track in enumerate(tracks, 1):
        print(f"{i}. {track['title']} by {', '.join(track['artist'])}")
