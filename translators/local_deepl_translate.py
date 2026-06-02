"""
DeepL Translate Module (DeepLX free endpoint)
A lightweight async translator using the deeplx.owo.network free API.

Same interface as local_google_translate.GoogleTranslateV2 — drop-in compatible.
"""

import asyncio
import html

try:
    import aiohttp
except ImportError:
    class aiohttp:
        class ClientSession:
            def __init__(self, *a, **kw): raise RuntimeError("aiohttp not installed")

# Language code mapping: Google-style short codes → DeepL uppercase codes
_LANG_MAP = {
    "ko": "KO",
    "en": "EN-US",
    "ja": "JA",
    "zh": "ZH-HANS",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
}

_BASE_URL = "https://oneshot-free.www.deepl.com/v1/translate"


def _to_deepl_lang(code: str) -> str:
    return _LANG_MAP.get(code.lower(), code.upper())


class DeepLTranslate:
    """
    Async DeepL client using the deeplx.owo.network free endpoint.

    Usage (identical to GoogleTranslateV2):
        async with DeepLTranslate() as tr:
            result = await tr.translate("안녕하세요", src="ko", dest="en")
    """

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self._session_owner = False

    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._session_owner = True
        return self

    async def __aexit__(self, *_):
        if self.session and self._session_owner:
            await self.session.close()
            self.session = None
            self._session_owner = False

    async def translate_batch(self, texts: list[str], src: str = "ko", dest: str = "en") -> list[str]:
        """
        Translate multiple texts in a single API call.
        Returns a list of translated strings (empty string on failure for that item).
        """
        if not texts:
            return []

        session_created = False
        if self.session is None:
            self.session = aiohttp.ClientSession()
            session_created = True

        try:
            payload = {
                "text":        texts,
                "source_lang": _to_deepl_lang(src),
                "target_lang": _to_deepl_lang(dest),
            }
            headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

            for attempt in range(5):
                try:
                    async with self.session.post(
                        _BASE_URL, json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            translations = data.get("translations", [])
                            return [html.unescape(t.get("text", "")) for t in translations]
                        elif resp.status == 429:
                            wait = 2 ** attempt * 2
                            await asyncio.sleep(wait)
                            continue
                        else:
                            break
                except asyncio.TimeoutError:
                    await asyncio.sleep(2)
                    continue
                except Exception:
                    break
            return [""] * len(texts)
        finally:
            if session_created and self.session:
                await self.session.close()
                self.session = None

    async def translate(self, text: str, src: str = "ko", dest: str = "en") -> str:
        """
        Translate text via DeepLX free endpoint.

        Args:
            text : Text to translate.
            src  : Source language code (e.g. "ko"). Use "auto" for auto-detect.
            dest : Target language code (e.g. "en").

        Returns:
            Translated string, or the original text on failure.
        """
        session_created = False
        if self.session is None:
            self.session = aiohttp.ClientSession()
            session_created = True

        try:
            payload = {
                "text":        [text],
                "source_lang": _to_deepl_lang(src),
                "target_lang": _to_deepl_lang(dest),
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent":   "Mozilla/5.0",
            }

            for attempt in range(5):
                try:
                    async with self.session.post(
                        _BASE_URL, json=payload, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            translations = data.get("translations", [])
                            if translations:
                                translated = translations[0].get("text", "")
                                if translated and translated != text:
                                    return html.unescape(translated)
                            break
                        elif resp.status == 429:
                            # Rate limited — back off exponentially
                            wait = 2 ** attempt
                            await asyncio.sleep(wait)
                            continue
                        else:
                            break
                except asyncio.TimeoutError:
                    await asyncio.sleep(1)
                    continue
                except Exception:
                    break

            return text

        except Exception:
            return text

        finally:
            if session_created and self.session:
                await self.session.close()
                self.session = None


# Alias so callers can do: from local_deepl_translate import DeepLTranslateV2
DeepLTranslateV2 = DeepLTranslate
