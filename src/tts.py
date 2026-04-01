import json
import edge_tts
from pathlib import Path
from .models import LANG_MAP_PATH
from .ui import console

def get_voice(lang_code: str, gender: str = "male") -> str:
    if not LANG_MAP_PATH.exists():
        raise FileNotFoundError(f"Language map file not found: {LANG_MAP_PATH}")
    
    with open(LANG_MAP_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if lang_code not in data:
        raise ValueError(f"Language {lang_code} not found in lang_map.json")
    
    voices = data[lang_code]["voices"].get(gender, [])

    if not voices:
        # fallback: choose the other gender if available
        other_gender = "female" if gender == "male" else "male"
        voices = data[lang_code]["voices"].get(other_gender, [])
        if not voices:
            raise ValueError(f"Cannot find any voice for language '{lang_code}'.")
        console.warning(f"No {gender} voice found, switching to {other_gender}.")
        
    return voices[0]
 
async def tts(text: str, voice: str, output: Path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output))