"""Persistent user pronunciation overrides for desktop testing."""
from __future__ import annotations
import json
from pathlib import Path
from ..runtime import local_app_data
from .nepali_text import LEXICON, syllabify_line

def user_lexicon_path()->Path:return local_app_data()/"lexicon.json"
def load_user_lexicon(path:Path|None=None)->dict[str,list[str]]:
    p=path or user_lexicon_path()
    if not p.exists():return LEXICON
    try:data=json.loads(p.read_text(encoding="utf-8"))
    except Exception:return LEXICON
    for word,parts in data.items():
        if isinstance(word,str) and isinstance(parts,list) and all(isinstance(x,str) and x for x in parts):LEXICON[word]=parts
    return LEXICON
def save_user_lexicon(entries:dict[str,list[str]],path:Path|None=None)->Path:
    p=path or user_lexicon_path();p.parent.mkdir(parents=True,exist_ok=True);clean={str(k).strip():[str(x).strip() for x in v if str(x).strip()] for k,v in entries.items() if str(k).strip()};p.write_text(json.dumps(clean,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");LEXICON.update(clean);return p
def tts_text_for_line(line:str)->str:
    words={}
    for syl in syllabify_line(line):words.setdefault(syl.word_index,[]).append(syl.text)
    return " ".join("".join(parts) for _,parts in sorted(words.items()))
load_user_lexicon()
