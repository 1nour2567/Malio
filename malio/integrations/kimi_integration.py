import requests
import json
import traceback
from typing import Dict, Any, Optional, List
from config.config import settings


class KimiIntegration:
    """Integration with Kimi-k2.6 API"""

    def __init__(self):
        """Initialize Kimi integration"""
        self.api_key = settings.kimi_api_key
        self.model = settings.kimi_model
        self.api_base = settings.kimi_api_base

        print(f"Kimi API Key: {'Set' if self.api_key else 'Not set'}")
        print(f"Kimi Model: {self.model}")
        print(f"Kimi API Base: {self.api_base}")

    def generate_music_recommendation(self, user_input: str, context: Dict[str, Any],
                                      recommendations: List[Dict[str, Any]]) -> str:
        """Generate music recommendation response"""
        if not self.api_key or self.api_key == "your_kimi_api_key_here":
            return "您好！我是 Malio，您的音乐智能助手。为了为您提供个性化的音乐推荐和聊天服务，我需要配置 Kimi API 密钥。请在 .env 文件中设置您的 Kimi API 密钥，然后重启服务。"

        context_str = f"时间：{context.get('time', {}).get('time_of_day', '未知')}\n"
        context_str += f"星期：{context.get('time', {}).get('day_of_week', '未知')}\n"
        context_str += f"天气：{context.get('weather', {}).get('condition', '未知')}，温度：{context.get('weather', {}).get('temperature', '未知')}度\n"
        context_str += f"情绪：{context.get('mood', '未知')}\n"

        songs_str = "\n".join([
            f"- {song['title']} - {', '.join(song['artist'])}"
            for song in recommendations[:3]
        ]) if recommendations else "暂无推荐"

        prompt = f"""你是Malio，一款能够理解用户偏好并提供个性化音乐推荐的智能音乐助手。

当前上下文：
{context_str}

当前推荐歌曲：
{songs_str}

用户输入：
{user_input}

请用友好的、自然的中文回复。回复要求：
1. 回应用户的输入
2. 根据上下文简短解释为什么推荐这些歌曲
3. 清晰展示推荐歌曲（最多3首），不要显示相似度分数
4. 不要使用任何 Markdown 格式标记（如 **、*、#、` 等），纯文本回复
5. 询问用户是否想要更多推荐或有其他需求

请始终使用中文回复。"""

        response = self._call_kimi_api(prompt)
        return response

    def understand_user_intent(self, user_input: str) -> Dict[str, Any]:
        """Understand user intent from input"""
        if not self.api_key or self.api_key == "your_kimi_api_key_here":
            return {
                "intent": "general_chat",
                "parameters": {}
            }

        prompt = f"""你是一个音乐助手，分析用户输入以理解其意图。

用户输入：
{user_input}

请将意图分类为以下类别之一：
- music_recommendation: 用户想要音乐推荐
- mood_change: 用户想要改变音乐情绪
- playlist_management: 用户想要管理播放列表
- music_info: 用户询问音乐信息
- device_control: 用户想要控制音乐设备
- general_chat: 关于音乐的闲聊

同时提供从输入中提取的相关参数，例如：
- mood: 用户想要的情绪
- genre: 用户喜欢的风格
- artist: 提到的特定艺术家
- song: 提到的特定歌曲
- time_of_day: 与时间相关的偏好
- activity: 与活动相关的偏好

请用中文理解用户意图。

返回包含 'intent' 和 'parameters' 字段的 JSON 对象。"""

        response = self._call_kimi_api(prompt)

        try:
            result = json.loads(response)
            return result
        except json.JSONDecodeError:
            return {
                "intent": "general_chat",
                "parameters": {}
            }

    def generate_playlist_name(self, songs: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        """Generate a playlist name based on songs and context"""
        if not self.api_key or self.api_key == "your_kimi_api_key_here":
            return "我的音乐收藏"

        song_list = "\n".join([f"- {song['title']} - {', '.join(song['artist'])}" for song in songs[:5]])

        prompt = f"""根据以下歌曲和上下文生成一个创意且有描述性的播放列表名称：

歌曲：
{song_list}

上下文：
时间：{context.get('time_of_day', '未知')}
情绪：{context.get('mood', '未知')}
活动：{context.get('activity', '未知')}

播放列表名称应该：
1. 朗朗上口且令人难忘
2. 反映歌曲的情绪和风格
3. 考虑当前上下文
4. 字数在2-4个字之间
5. 不要包含"播放列表"这个词

请用中文回复，只返回播放列表名称，不要其他内容。"""

        response = self._call_kimi_api(prompt)
        return response.strip()

    def _call_kimi_api(self, prompt: str) -> str:
        """Call Kimi API"""
        if not self.api_key or self.api_key == "your_kimi_api_key_here":
            print("Error: KIMI_API_KEY is not set or is still the placeholder value")
            return "抱歉遇到了错误。请检查您的 API 密钥配置。"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 4096,
            "temperature": 1,
        }

        try:
            print(f"Calling Kimi API with model: {self.model}")
            print(f"API Base URL: {self.api_base}")

            response = requests.post(
                f"{self.api_base}chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )

            print(f"Response status code: {response.status_code}")
            print(f"Response content: {response.text[:500]}...")

            response.raise_for_status()

            result = response.json()

            # Handle API-level errors (non-200 disguised as 200 by some proxies)
            if "error" in result:
                err = result["error"]
                print(f"Kimi API returned error: {err}")
                return f"API 错误：{err.get('message', str(err))}"

            choices = result.get("choices", [])
            if not choices:
                print(f"Kimi API returned empty choices. Full response: {json.dumps(result, ensure_ascii=False)[:500]}")
                return "抱歉，AI 没有返回有效内容，请重试。"

            msg = choices[0].get("message", {})
            content = msg.get("content", "")

            # kimi-k2.5 reasoning model may put answer in reasoning_content when content is empty
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"]

            if not content:
                finish = choices[0].get("finish_reason", "unknown")
                print(f"Empty content from Kimi. finish_reason={finish}, reasoning_len={len(msg.get('reasoning_content', ''))}")
                return "抱歉，我思考了很久但没能组织好回复，请再说一次？"

            return content

        except requests.exceptions.Timeout:
            print("Kimi API timeout after 60s")
            return "抱歉，AI 响应超时，请稍后重试。"
        except requests.exceptions.RequestException as e:
            print(f"Kimi API request error: {e}")
            return "抱歉，网络连接失败，请检查网络后重试。"
        except (KeyError, IndexError, TypeError) as e:
            print(f"Kimi API response parse error: {e}")
            print(f"Full traceback:\n{traceback.format_exc()}")
            return "抱歉，AI 返回了意外的数据格式，请稍后重试。"
        except Exception as e:
            print(f"Unexpected error in Kimi API call: {e}")
            print(f"Full traceback:\n{traceback.format_exc()}")
            return "抱歉遇到了错误。请稍后重试。"


if __name__ == "__main__":
    kimi = KimiIntegration()

    context = {
        "time": {
            "time_of_day": "早上",
            "day_of_week": "周一"
        },
        "weather": {
            "condition": "晴天",
            "temperature": 22
        }
    }

    recommendations = [
        {
            "id": "song_001",
            "title": "颜色",
            "artist": ["许美静"],
            "album": "都是夜归人",
            "genre": ["华语流行", "抒情"],
            "score": 0.85
        }
    ]

    response = kimi.generate_music_recommendation(
        "我需要一些早上听的华语歌",
        context,
        recommendations
    )
    print("Kimi response:")
    print(response)

    intent = kimi.understand_user_intent("我现在心情有点低落，想听一些温暖的音乐")
    print("\nIntent understanding:")
    print(intent)
