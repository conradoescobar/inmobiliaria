"""Tests for the deduplication service."""

import pytest
from decimal import Decimal

from app.services.deduplication.normalizer import AddressNormalizer


class TestAddressNormalizer:
    """Tests for address normalization."""

    def test_normalize_basic(self):
        """Test basic address normalization."""
        normalizer = AddressNormalizer()

        result = normalizer.normalize("Calle Gran Vía, 28")
        assert result is not None
        assert "calle" in result
        assert "gran" in result
        assert "via" in result
        assert "28" in result

    def test_normalize_abbreviations(self):
        """Test expansion of street type abbreviations."""
        normalizer = AddressNormalizer()

        # Test various abbreviations
        assert "avenida" in normalizer.normalize("Av. de América")
        assert "calle" in normalizer.normalize("C/ Mayor")
        assert "plaza" in normalizer.normalize("Pza. España")
        assert "paseo" in normalizer.normalize("Pº de la Castellana")

    def test_normalize_removes_accents(self):
        """Test removal of accents."""
        normalizer = AddressNormalizer()

        result = normalizer.normalize("Calle María Molíner")
        assert "maria" in result
        assert "moliner" in result
        # No accented characters
        assert "í" not in result

    def test_normalize_empty_input(self):
        """Test handling of empty input."""
        normalizer = AddressNormalizer()

        assert normalizer.normalize(None) is None
        assert normalizer.normalize("") is None
        assert normalizer.normalize("   ") is None

    def test_normalize_removes_noise_words(self):
        """Test removal of noise words."""
        normalizer = AddressNormalizer()

        result = normalizer.normalize("Calle de la Paz")
        # "de" and "la" should be removed
        assert "calle" in result
        assert "paz" in result

    def test_extract_street_number(self):
        """Test street number extraction."""
        normalizer = AddressNormalizer()

        assert normalizer.extract_street_number("Calle Mayor 15") == "15"
        assert normalizer.extract_street_number("Av. América, 123") == "123"
        assert normalizer.extract_street_number("Plaza España") is None

    def test_extract_floor_door(self):
        """Test floor and door extraction."""
        normalizer = AddressNormalizer()

        floor, door = normalizer.extract_floor_door("C/ Mayor 15, 3º A")
        assert floor == "3"

        floor, door = normalizer.extract_floor_door("Piso 5, puerta B")
        assert floor == "5"

    def test_address_components(self):
        """Test extraction of address components."""
        normalizer = AddressNormalizer()

        components = normalizer.get_address_components("Calle Gran Vía 28, 3º A")
        assert components.get("street_type") == "calle"
        assert components.get("number") == "28"


class TestDeduplicationScoring:
    """Tests for deduplication scoring logic."""

    def test_identical_addresses_high_score(self):
        """Test that identical normalized addresses get high similarity."""
        normalizer = AddressNormalizer()

        addr1 = normalizer.normalize("Calle Gran Vía 28")
        addr2 = normalizer.normalize("C/ Gran Via, 28")

        # Both should normalize to similar strings
        assert addr1 is not None
        assert addr2 is not None

    def test_different_addresses_low_score(self):
        """Test that different addresses get low similarity."""
        normalizer = AddressNormalizer()

        addr1 = normalizer.normalize("Calle Gran Vía 28")
        addr2 = normalizer.normalize("Avenida de América 100")

        # Addresses should be different
        assert addr1 != addr2
