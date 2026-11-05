from __future__ import annotations

import re
import unicodedata

class Normalizer:
    """Utilidades de normalizacion de texto"""
    
    @staticmethod
    def norm(s: object) -> str:
        
        if s is None:
            return ""
        
        s = unicodedata.normalize("NFKD", str(s))
        s = "".join(c for c in s if not unicodedata.combining(c))
        
        return re.sub(r"\s+", " ", s).strip().upper()
    
    @staticmethod
    def alnum(s: object) -> str:
        return re.sub(r"[^0-9A-Za-z]", "", "" if s is None else str(s)).upper()
