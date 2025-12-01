"""Address normalization utilities for deduplication."""

import re
import unicodedata
from typing import Optional


class AddressNormalizer:
    """
    Normalizes Spanish addresses for comparison and deduplication.

    Handles common variations in street types, abbreviations,
    and formatting to produce consistent address strings.
    """

    # Spanish street type abbreviations and their full forms
    STREET_TYPES = {
        # Standard abbreviations
        "c/": "calle",
        "c.": "calle",
        "cl": "calle",
        "av": "avenida",
        "av.": "avenida",
        "avda": "avenida",
        "avda.": "avenida",
        "pº": "paseo",
        "p.": "paseo",
        "po": "paseo",
        "pza": "plaza",
        "pza.": "plaza",
        "pl": "plaza",
        "pl.": "plaza",
        "plza": "plaza",
        "ctra": "carretera",
        "ctra.": "carretera",
        "crta": "carretera",
        "rda": "ronda",
        "rda.": "ronda",
        "pje": "pasaje",
        "pje.": "pasaje",
        "trav": "travesia",
        "trav.": "travesia",
        "urb": "urbanizacion",
        "urb.": "urbanizacion",
        "pol": "poligono",
        "pol.": "poligono",
        "pque": "parque",
        "pq": "parque",
        "cam": "camino",
        "cam.": "camino",
        "cno": "camino",
        "gta": "glorieta",
        "gta.": "glorieta",
    }

    # Ordinal abbreviations
    ORDINALS = {
        "1º": "primero",
        "2º": "segundo",
        "3º": "tercero",
        "4º": "cuarto",
        "5º": "quinto",
        "6º": "sexto",
        "7º": "septimo",
        "8º": "octavo",
        "9º": "noveno",
        "10º": "decimo",
        "1ª": "primera",
        "2ª": "segunda",
        "3ª": "tercera",
    }

    # Common words to remove
    NOISE_WORDS = {
        "de", "del", "la", "las", "el", "los", "un", "una",
        "y", "e", "o", "u", "en", "con", "sin", "por", "para",
        "san", "santa", "santo",
    }

    @classmethod
    def normalize(cls, address: Optional[str]) -> Optional[str]:
        """
        Normalize an address for comparison.

        Args:
            address: Raw address string

        Returns:
            Normalized address string, or None if input is None/empty
        """
        if not address:
            return None

        # Convert to lowercase
        normalized = address.lower().strip()

        # Remove accents and diacritics
        normalized = cls._remove_accents(normalized)

        # Expand street type abbreviations
        normalized = cls._expand_abbreviations(normalized)

        # Normalize ordinals
        normalized = cls._normalize_ordinals(normalized)

        # Remove punctuation except hyphens and numbers
        normalized = re.sub(r"[^\w\s\-]", " ", normalized)

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Remove common noise words
        words = normalized.split()
        words = [w for w in words if w not in cls.NOISE_WORDS]

        # Remove leading zeros from numbers
        words = [cls._normalize_number(w) for w in words]

        return " ".join(words) if words else None

    @classmethod
    def _remove_accents(cls, text: str) -> str:
        """Remove accents and diacritics from text."""
        # Normalize to NFD form (decomposed)
        nfkd_form = unicodedata.normalize("NFKD", text)
        # Remove diacritical marks
        return "".join(c for c in nfkd_form if not unicodedata.combining(c))

    @classmethod
    def _expand_abbreviations(cls, text: str) -> str:
        """Expand common street type abbreviations."""
        result = text
        for abbr, full in cls.STREET_TYPES.items():
            # Match abbreviation at word boundary
            pattern = rf"\b{re.escape(abbr)}\b"
            result = re.sub(pattern, full, result)
        return result

    @classmethod
    def _normalize_ordinals(cls, text: str) -> str:
        """Normalize ordinal numbers."""
        result = text
        for abbr, full in cls.ORDINALS.items():
            result = result.replace(abbr, full)
        return result

    @classmethod
    def _normalize_number(cls, word: str) -> str:
        """Normalize numbers by removing leading zeros."""
        if word.isdigit():
            return str(int(word))
        return word

    @classmethod
    def extract_street_number(cls, address: Optional[str]) -> Optional[str]:
        """Extract the street number from an address."""
        if not address:
            return None

        # Look for number patterns
        match = re.search(r"\b(\d+)\b", address)
        return match.group(1) if match else None

    @classmethod
    def extract_floor_door(cls, address: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Extract floor and door from an address."""
        if not address:
            return None, None

        floor = None
        door = None

        # Look for floor patterns (1º, piso 1, planta 2, etc.)
        floor_match = re.search(r"(\d+)[ºª]|\bpiso\s*(\d+)|\bplanta\s*(\d+)", address.lower())
        if floor_match:
            floor = floor_match.group(1) or floor_match.group(2) or floor_match.group(3)

        # Look for door patterns (puerta A, pta 2, etc.)
        door_match = re.search(r"\bpta\.?\s*(\w+)|\bpuerta\s*(\w+)|(\d+)[ºª]\s*(\w+)", address.lower())
        if door_match:
            door = door_match.group(1) or door_match.group(2) or door_match.group(4)

        return floor, door

    @classmethod
    def get_address_components(cls, address: Optional[str]) -> dict:
        """
        Extract structured components from an address.

        Returns:
            Dictionary with street_type, street_name, number, floor, door
        """
        if not address:
            return {}

        normalized = address.lower().strip()
        components = {}

        # Extract street type
        for abbr, full in cls.STREET_TYPES.items():
            pattern = rf"\b{re.escape(abbr)}\b|\b{re.escape(full)}\b"
            if re.search(pattern, normalized):
                components["street_type"] = full
                break

        # Extract number
        components["number"] = cls.extract_street_number(address)

        # Extract floor and door
        floor, door = cls.extract_floor_door(address)
        if floor:
            components["floor"] = floor
        if door:
            components["door"] = door

        return components
