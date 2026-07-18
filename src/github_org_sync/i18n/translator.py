import contextlib
from collections.abc import Callable
from typing import Any

from github_org_sync.i18n.translations import TRANSLATIONS


class Translator:
    _instance: "Translator | None" = None
    _lang: str
    _listeners: list[Callable[[], None]]

    def __new__(cls, *args: Any, **kwargs: Any) -> "Translator":
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._lang = "pl"
            cls._instance._listeners = []
        return cls._instance

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang in TRANSLATIONS:
            self._lang = lang
            # Notify all registered change listeners
            for listener in self._listeners:
                with contextlib.suppress(Exception):
                    listener()

    def translate(self, key: str, **kwargs: Any) -> str:
        lang_dict = TRANSLATIONS.get(self._lang, TRANSLATIONS["pl"])
        text = lang_dict.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def register_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)


# Singleton global translator instance
translator = Translator()


def _t(key: str, **kwargs: Any) -> str:
    return translator.translate(key, **kwargs)
