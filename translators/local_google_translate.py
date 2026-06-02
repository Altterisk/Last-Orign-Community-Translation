"""
Google Translate HTML API Module
A lightweight async translator using Google's internal translateHtml API
"""

import asyncio
import json
import urllib.parse
import html
from typing import Optional

try:
    import aiohttp
except ImportError:
    class aiohttp:
        @staticmethod
        def ClientSession():
            raise RuntimeError("aiohttp not installed; please install aiohttp to use this translator")

        class ClientSession:
            pass

class GoogleTranslateHTML:
    """
    Async Google Translate client using the translateHtml API

    Usage:
        from google_translate import GoogleTranslateHTML

        translator = GoogleTranslateHTML()

        async def translate_text(text: str) -> str:
            result = await translator.translate(text, src="ja", dest="en")
            print(f"Translated: {text} -> {result}")
            return result
    """

    def __init__(self):
        self.base_url = "https://translate-pa.googleapis.com/v1/translateHtml"
        self.api_key = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"
        self.session = None
        self._session_owner = False

    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._session_owner = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and self._session_owner:
            await self.session.close()
            self.session = None
            self._session_owner = False

    def _process_response(self, response_data, original_text: str):
        """
        Process the response from Google's translateHtml API
        """
        try:
            # The response format is usually nested arrays
            # Navigate through the structure to find the translated text
            if isinstance(response_data, list) and len(response_data) > 0:
                # Look for the translation in various possible locations
                first_item = response_data[0]
                if isinstance(first_item, list) and len(first_item) > 0:
                    # Check if it's directly in the first nested array
                    if isinstance(first_item[0], str):
                        return first_item[0]
                    # Or if it's nested deeper
                    elif isinstance(first_item[0], list) and len(first_item[0]) > 0:
                        if isinstance(first_item[0][0], str):
                            return first_item[0][0]
                        elif isinstance(first_item[0][0], list) and len(first_item[0][0]) > 0:
                            return first_item[0][0][0]

            # If we can't find it in the expected structure, search recursively
            def find_translation(obj, original_text):
                if isinstance(obj, str) and obj != original_text and len(obj.strip()) > 0:
                    return obj
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_translation(item, original_text)
                        if result:
                            return result
                elif isinstance(obj, dict):
                    for value in obj.values():
                        result = find_translation(value, original_text)
                        if result:
                            return result
                return None

            return find_translation(response_data, original_text)

        except Exception:
            return None

    async def translate(self, text: str, src: str = "ko", dest: str = "en") -> str:
        """
        Translate text using Google's translateHtml API

        Args:
            text: Text to translate
            src: Source language code (default: "ko" for Korean)
            dest: Destination language code (default: "en" for English)

        Returns:
            Translated text or original text if translation fails
        """
        # Handle session management
        session_created = False
        if self.session is None:
            self.session = aiohttp.ClientSession()
            session_created = True

        try:
            # Prepare the text (replace newlines with <br>)
            formatted_text = text.replace("\n", "<br>")

            # Create the raw content in the exact format required
            raw_content = [[[formatted_text], src, dest], "wt_lib"]

            # Convert to JSON
            content = json.dumps(raw_content)

            headers = {
                "Accept": "*/*",
                "X-Goog-API-Key": self.api_key,
                "Content-Type": "application/json+protobuf",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            # Make the request with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with self.session.post(self.base_url, data=content, headers=headers) as response:
                        if response.status == 200:
                            response_data = await response.json()

                            # Process the response
                            translation = self._process_response(response_data, text)

                            if translation:
                                # Replace <br> back to newlines and decode HTML entities
                                translation = translation.replace("<br>", "\n")
                                translation = html.unescape(translation)
                                return translation

                    # If we get here without success, break the retry loop
                    break

                except asyncio.TimeoutError:
                    if attempt == max_retries - 1:
                        break
                    continue
                except Exception:
                    if attempt == max_retries - 1:
                        break
                    continue

            return text

        except Exception:
            return text

        finally:
            # Clean up session if we created it
            if session_created and self.session:
                await self.session.close()
                self.session = None


# Alternative API endpoint (fallback)
class GoogleTranslateAPI:
    """
    Alternative Google Translate client using the translate_a/single endpoint
    """

    def __init__(self):
        self.base_url = "https://translate.googleapis.com/translate_a/single"
        self.session = None
        self._session_owner = False

    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._session_owner = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session and self._session_owner:
            await self.session.close()
            self.session = None
            self._session_owner = False

    async def translate(self, text: str, src: str = "ko", dest: str = "en") -> str:
        """
        Translate using Google's internal API endpoint (fallback method)
        """
        # Handle session management
        session_created = False
        if self.session is None:
            self.session = aiohttp.ClientSession()
            session_created = True

        try:
            params = {
                'client': 'gtx',
                'sl': src,
                'tl': dest,
                'dt': 't',
                'q': text
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            async with self.session.get(self.base_url, params=params, headers=headers) as response:
                if response.status == 200:
                    result = await response.text()

                    try:
                        # Clean up the response to make it valid JSON
                        result = result.replace(',,', ',null,').replace('[,', '[null,')
                        data = json.loads(result)

                        if data and len(data) > 0 and data[0] and len(data[0]) > 0:
                            translation = data[0][0][0]
                            if translation and translation != text:
                                # Decode HTML entities
                                translation = html.unescape(translation)
                                return translation
                    except (json.JSONDecodeError, IndexError, TypeError):
                        pass

                return text

        except Exception:
            return text

        finally:
            # Clean up session if we created it
            if session_created and self.session:
                await self.session.close()
                self.session = None


# Main translator class (recommended)
GoogleTranslateV2 = GoogleTranslateHTML
