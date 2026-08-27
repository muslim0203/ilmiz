import unittest

from backend.app.services.profile_collector import is_valid_phone


class PhoneValidationTest(unittest.TestCase):
    """`PHONE_RE` raqam ketma-ketligini topadi, xolos. Sana, ISSN va yillar
    ro'yxati ham telefon bo'lib yozilardi — 1 185 tadan 556 tasi."""

    def test_accepts_real_uzbek_numbers(self) -> None:
        for value in (
            "+998 71 244-35-47",
            "+998 (91) 245-46-66",
            "+998974084984",
            "+99890 323 2011",
            "+998 (95) 751-11-15",
            "71 244 35 47",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_valid_phone(value))

    def test_rejects_dates(self) -> None:
        for value in ("2024-07-08 04", "2026-06-11 12", "2025-08-27 12"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_phone(value))

    def test_rejects_issn_with_trailing_numbers(self) -> None:
        for value in ("3093-8805 2025 5", "3093-8635 2025 201", "3060-5539 2025 335"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_phone(value))

    def test_rejects_number_sequences(self) -> None:
        for value in (
            "2021 2022 2023 2024 2025 2026",
            "1 2 3 4 5 6 7 8 9 10 11 12",
            "2025 2026 2027 2028 2029 2022",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_valid_phone(value))

    def test_rejects_account_numbers(self) -> None:
        for value in ("23402000300100001010", "400910860064017094100350004"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_phone(value))

    def test_rejects_too_short(self) -> None:
        self.assertFalse(is_valid_phone("12345"))


if __name__ == "__main__":
    unittest.main()
