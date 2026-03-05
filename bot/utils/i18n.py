import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Translator:
    def __init__(self, locales_dir: str = "locales"):
        self.locales: Dict[str, Dict[str, str]] = {}
        self.locales_dir = locales_dir
        self.load_locales()

    def load_locales(self):
        """Load all .json files from locales directory."""
        if not os.path.exists(self.locales_dir):
            logger.warning(f"Locales directory {self.locales_dir} not found.")
            return

        for filename in os.listdir(self.locales_dir):
            if filename.endswith(".json"):
                lang_code = filename[:-5]
                try:
                    with open(os.path.join(self.locales_dir, filename), "r", encoding="utf-8") as f:
                        self.locales[lang_code] = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load locale {filename}: {e}")

    def get(self, key: str, _lang: str = "uz", **kwargs) -> str:
        """Get translated string for key in specified language."""
        # Fallback to 'uz' if lang not found
        lang_data = self.locales.get(_lang, self.locales.get("uz", {}))
        text = lang_data.get(key, self.locales.get("uz", {}).get(key, key))
        
        try:
            return text.format(**kwargs)
        except Exception as e:
            logger.error(f"Translation formatting error for {key} in {_lang}: {e}")
            return text

translator = Translator()
