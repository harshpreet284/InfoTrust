from unittest import TestCase

from analysis.preprocessing import (
    MAX_CLAIM_LENGTH,
    MIN_CLAIM_LENGTH,
    ClaimPreprocessingError,
    preprocess_claim_text,
)


class JoinerSanitizationTests(TestCase):
    """
    Tests for context-aware deterministic sanitization of Zero-Width Joiner (ZWJ)
    and Zero-Width Non-Joiner (ZWNJ).
    """

    def test_preserve_compound_zwj_emojis(self):
        """Verify compound emoji sequences using ZWJ are preserved."""
        raw = "Healthcare workers 👩\u200d⚕️ and scientists 👨\u200d🔬 agree."
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(cleaned, "Healthcare workers 👩‍⚕️ and scientists 👨‍🔬 agree.")

    def test_preserve_emoji_followed_by_ascii_text(self):
        """Verify compound emoji ZWJ is preserved even when immediately followed by ASCII letters."""
        raw = "The doctor 👩\u200d⚕️says it is safe."
        self.assertEqual(preprocess_claim_text(raw), "The doctor 👩‍⚕️says it is safe.")

    def test_preserve_emoji_preceded_by_ascii_text(self):
        """Verify compound emoji ZWJ is preserved even when immediately preceded by ASCII letters."""
        raw = "Report by Dr👩\u200d⚕️ is available now."
        self.assertEqual(preprocess_claim_text(raw), "Report by Dr👩‍⚕️ is available now.")

    def test_preserve_emoji_preceded_and_followed_by_ascii(self):
        """Verify compound emoji ZWJ is preserved when touched by ASCII on both sides."""
        raw = "Status: A👩\u200d⚕️B is confirmed."
        self.assertEqual(preprocess_claim_text(raw), "Status: A👩‍⚕️B is confirmed.")

    def test_normalize_consecutive_zwj_in_emoji(self):
        """Verify consecutive repeated ZWJs between valid emoji components are normalized to single ZWJ."""
        raw = "The doctor 👩\u200d\u200d\u200d⚕️ is ready."
        self.assertEqual(preprocess_claim_text(raw), "The doctor 👩‍⚕️ is ready.")

    def test_preserve_zwnj_in_non_latin_script(self):
        """Verify orthographically valid ZWNJ in Persian text is preserved."""
        raw = "این یک ادعای معتبر در مورد واکسن است که می‌خواهم بررسی کنم."
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(
            cleaned,
            "این یک ادعای معتبر در مورد واکسن است که می‌خواهم بررسی کنم.",
        )

    def test_normalize_consecutive_zwnj_in_non_latin(self):
        """Verify consecutive repeated ZWNJs in non-Latin script are normalized to single ZWNJ."""
        raw = "این ادعا می\u200c\u200cخواهم بررسی شود."
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(cleaned, "این ادعا می‌خواهم بررسی شود.")

    def test_remove_zwj_injected_between_ascii_alnum(self):
        """Verify ZWJ injected inside an ASCII word is removed to defeat evasion."""
        raw = "The v\u200daccine was tested in clinical trials."
        self.assertEqual(
            preprocess_claim_text(raw),
            "The vaccine was tested in clinical trials.",
        )

    def test_remove_zwnj_injected_between_ascii_alnum(self):
        """Verify ZWNJ injected inside an ASCII word is removed to defeat evasion."""
        raw = "The p\u200cfizer vaccine received approval."
        self.assertEqual(
            preprocess_claim_text(raw),
            "The pfizer vaccine received approval.",
        )

    def test_remove_repeated_joiners_in_ascii(self):
        """Verify repeated joiners inside an ASCII word are completely removed."""
        raw = "The c\u200d\u200dovid vaccine was authorized."
        self.assertEqual(
            preprocess_claim_text(raw),
            "The covid vaccine was authorized.",
        )

    def test_remove_joiners_at_string_boundaries(self):
        """Verify joiners at text boundaries are removed."""
        leading = "\u200DHello world test claim."
        self.assertEqual(preprocess_claim_text(leading), "Hello world test claim.")

        trailing = "Hello world test claim.\u200C"
        self.assertEqual(preprocess_claim_text(trailing), "Hello world test claim.")

    def test_remove_isolated_joiners_in_whitespace(self):
        """Verify isolated joiners surrounded by whitespace are removed."""
        raw = "Hello \u200d world test claim."
        self.assertEqual(preprocess_claim_text(raw), "Hello world test claim.")

    def test_remove_joiners_in_mixed_script_adjacency(self):
        """Verify joiners adjacent to ASCII characters in mixed-script text are dropped."""
        raw = "The COVID\u200cواکسن is effective."
        self.assertEqual(preprocess_claim_text(raw), "The COVIDواکسن is effective.")

    def test_remove_joiners_adjacent_to_punctuation(self):
        """Verify joiners adjacent to punctuation are dropped."""
        raw = "Claim (with\u200d punctuation!) inside text."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Claim (with punctuation!) inside text.",
        )

    def test_drop_malformed_mixed_joiners_in_emoji(self):
        """Verify malformed mixed ZWJ/ZWNJ runs in emoji context are completely dropped."""
        raw = "The doctor 👩\u200c\u200d⚕️ is ready."
        self.assertEqual(preprocess_claim_text(raw), "The doctor 👩⚕️ is ready.")

    def test_drop_malformed_mixed_joiners_in_multilingual_text(self):
        """Verify malformed mixed ZWJ/ZWNJ runs in multilingual text are completely dropped."""
        raw = "این یک ادعای معتبر است که می\u200c\u200dخواهم بررسی کنم."
        self.assertEqual(
            preprocess_claim_text(raw),
            "این یک ادعای معتبر است که میخواهم بررسی کنم.",
        )

    def test_preserve_rainbow_flag_emoji_with_attached_variation_selector(self):
        """Verify ZWJ is preserved in rainbow flag emoji where variation selector is attached to base emoji."""
        raw = "Human rights rally with 🏳️\u200d🌈 flag in city."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Human rights rally with 🏳️‍🌈 flag in city.",
        )

    def test_drop_detached_variation_selector_adjacent_to_zwj(self):
        """Verify detached variation selector adjacent to ZWJ drops the malformed joiner."""
        # 1. Detached VS-16 preceded by ASCII text
        raw_ascii_vs = "Report notice\ufe0f\u200d🔬 microscope claim."
        self.assertEqual(
            preprocess_claim_text(raw_ascii_vs),
            "Report notice️🔬 microscope claim.",
        )

        # 2. Detached VS-16 following ZWJ
        raw_trailing_vs = "Scientist 👨\u200d\ufe0f report is published."
        self.assertEqual(
            preprocess_claim_text(raw_trailing_vs),
            "Scientist 👨️ report is published.",
        )

        # 3. Detached VS-16 on both sides of ZWJ
        raw_both_vs = "Notice with \ufe0f\u200d\ufe0f detached symbols."
        self.assertEqual(
            preprocess_claim_text(raw_both_vs),
            "Notice with ️️ detached symbols.",
        )



class TargetedCharacterFilteringTests(TestCase):
    """
    Tests for removal of invisible formatting, dangerous control characters,
    lone surrogates, and preservation of PUA/variation selectors.
    """

    def test_remove_zero_width_space(self):
        raw = "Con\u200bspiracy theory about 5G towers."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Conspiracy theory about 5G towers.",
        )

    def test_remove_word_joiner(self):
        raw = "Scientific\u2060consensus on climate."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Scientificconsensus on climate.",
        )

    def test_remove_byte_order_mark(self):
        raw = "\ufeffThe government announced new policy."
        self.assertEqual(
            preprocess_claim_text(raw),
            "The government announced new policy.",
        )

    def test_remove_soft_hyphen(self):
        raw = "In\u00adcredible claims about the election."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Incredible claims about the election.",
        )

    def test_remove_bidi_formatting_controls(self):
        raw = "Claim with \u202esneaky\u202c override and \u200emark."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Claim with sneaky override and mark.",
        )

    def test_remove_dangerous_controls(self):
        raw = "Claim with null\x00 and bell\x07 and esc\x1b inside."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Claim with null and bell and esc inside.",
        )

    def test_remove_lone_high_surrogate(self):
        raw = "Valid claim text\ud800here."
        self.assertEqual(preprocess_claim_text(raw), "Valid claim texthere.")

    def test_remove_lone_low_surrogate(self):
        raw = "Valid claim text\udc00here."
        self.assertEqual(preprocess_claim_text(raw), "Valid claim texthere.")

    def test_preserve_private_use_characters(self):
        raw = "Claim with private-use \uE000 symbol."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Claim with private-use \uE000 symbol.",
        )

    def test_preserve_emoji_variation_selectors(self):
        raw = "Warning ⚠️ and medical ⚕️ advisory."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Warning ⚠️ and medical ⚕️ advisory.",
        )


class UnicodeNormalizationAndIdempotencyTests(TestCase):
    """
    Tests for NFKC normalization, compatibility trade-offs, and idempotency.
    """

    def test_unicode_nfkc_compatibility_tradeoffs(self):
        """
        Verify NFKC compatibility trade-offs:
        - Superscript digits decompose to standard digits (e.g. m² -> m2).
        - Ligatures decompose to standard ASCII letters (e.g. ﬁ -> fi).
        - Full-width characters normalize to ASCII (e.g. Ａ -> A).
        """
        raw = "Area is 50 m², \ufb01rst report from \uff21\uff22\uff23."
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(cleaned, "Area is 50 m2, first report from ABC.")

    def test_unicode_nfkc_decomposed_accents(self):
        """Verify decomposed characters (e + combining acute) compose to precomposed é."""
        raw = "Caf\u0065\u0301 is open for business."
        self.assertEqual(preprocess_claim_text(raw), "Café is open for business.")

    def test_unicode_idempotency_representative_cases(self):
        """Verify preprocess_claim_text(preprocess_claim_text(t)) == preprocess_claim_text(t)."""
        samples = [
            "The WHO announced new COVID-19 guidelines today.",
            "Healthcare workers 👩‍⚕️ and scientists 👨‍🔬 agree: 🏳️‍🌈 flag.",
            "این یک ادعای معتبر در مورد واکسن است که می‌خواهم بررسی کنم.",
            "Area is 50 m², \ufb01rst report from \uff21\uff22\uff23.",
            "Caf\u0065\u0301 is open for business with 50% discount!",
        ]
        for sample in samples:
            cleaned_once = preprocess_claim_text(sample)
            cleaned_twice = preprocess_claim_text(cleaned_once)
            self.assertEqual(cleaned_once, cleaned_twice)


class WhitespaceNormalizationTests(TestCase):
    """
    Tests for whitespace collapsing and trimming.
    """

    def test_collapse_tabs_and_newlines(self):
        raw = "First sentence.\n\n\nSecond\tsentence."
        self.assertEqual(
            preprocess_claim_text(raw),
            "First sentence. Second sentence.",
        )

    def test_trim_leading_trailing_whitespace(self):
        raw = "\t\r\n A valid claim text statement. \r\n\t"
        self.assertEqual(
            preprocess_claim_text(raw),
            "A valid claim text statement.",
        )

    def test_normalize_unicode_category_z_spaces(self):
        raw = "Claim\u00a0with\u2003non-breaking\u2002spaces."
        self.assertEqual(
            preprocess_claim_text(raw),
            "Claim with non-breaking spaces.",
        )


class LengthAndBoundaryTests(TestCase):
    """
    Tests for minimum/maximum length constraints and boundary conditions.
    """

    def test_exact_minimum_length_10_chars(self):
        raw = "1234567890"
        self.assertEqual(preprocess_claim_text(raw), "1234567890")

    def test_exact_maximum_length_2000_chars(self):
        raw = "A" * MAX_CLAIM_LENGTH
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(len(cleaned), MAX_CLAIM_LENGTH)

    def test_below_minimum_length_rejected(self):
        raw = "123456789"  # 9 chars
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text(raw)
        self.assertIn("too short", str(ctx.exception))

    def test_above_maximum_length_rejected(self):
        raw = "A" * (MAX_CLAIM_LENGTH + 1)  # 2001 chars
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text(raw)
        self.assertIn("too long", str(ctx.exception))

    def test_empty_string_rejected(self):
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text("")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text("   \t\n\r   ")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_invisible_only_rejected(self):
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text("\u200b\ufeff\u00ad")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_post_cleaning_underflow_rejected(self):
        # 10 raw chars, but 5 invisible chars -> only 5 clean chars
        raw = "Short\u200b\u200b\u200b\u200b\u200b"
        with self.assertRaises(ClaimPreprocessingError) as ctx:
            preprocess_claim_text(raw)
        self.assertIn("too short", str(ctx.exception))

    def test_code_point_length_semantics_with_emojis(self):
        # Demonstrates that len() measures Python string code points
        # 👩‍⚕️ consists of 4 code points: \U0001F469 + \u200D + \u2695 + \uFE0F
        emoji = "👩‍⚕️"
        self.assertEqual(len(emoji), 4)

        raw = f"Claim {emoji} text"  # "Claim " (6) + emoji (4) + " text" (5) = 15 code points
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(len(cleaned), 15)


class ContractAndTypeTests(TestCase):
    """
    Tests for exception inheritance, type checking, and semantics preservation.
    """

    def test_non_string_types_raise_type_error(self):
        for invalid_input in [None, 123, 45.6, [], {}, True]:
            with self.assertRaises(TypeError):
                preprocess_claim_text(invalid_input)  # type: ignore

    def test_claim_preprocessing_error_is_subclass_of_value_error(self):
        self.assertTrue(issubclass(ClaimPreprocessingError, ValueError))

    def test_can_catch_as_value_error(self):
        with self.assertRaises(ValueError):
            preprocess_claim_text("too short")

    def test_preserve_casing_and_punctuation(self):
        raw = "BREAKING: $1,000,000 was paid; 50% loss! (5 > 2)"
        cleaned = preprocess_claim_text(raw)
        self.assertEqual(cleaned, "BREAKING: $1,000,000 was paid; 50% loss! (5 > 2)")
