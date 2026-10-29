"""
Unit and regression tests for Rule-based Validation Layer Service (AI-008).
Validates deterministic heuristics, invariants, immutability, scoring formulas,
and privacy guarantees for InfoTrust.
"""

import json
from dataclasses import FrozenInstanceError

from django.test import SimpleTestCase

from analysis.services.rules import (
    DEFAULT_PENALTY_PER_FLAG,
    VALID_RULE_FLAGS,
    RuleConfigError,
    RuleEngineError,
    RuleEngineService,
    RuleInputError,
    RuleValidationResult,
)


class RuleEngineInvariantsAndConfigTests(SimpleTestCase):
    """Tests configuration validation and data contract invariants of RuleValidationResult."""

    def test_default_initialization(self) -> None:
        service = RuleEngineService()
        self.assertEqual(service.penalty_per_flag, DEFAULT_PENALTY_PER_FLAG)
        self.assertAlmostEqual(service.penalty_per_flag, 0.05)

    def test_valid_custom_penalty(self) -> None:
        service_zero = RuleEngineService(penalty_per_flag=0.0)
        self.assertEqual(service_zero.penalty_per_flag, 0.0)

        service_half = RuleEngineService(penalty_per_flag=0.15)
        self.assertEqual(service_half.penalty_per_flag, 0.15)

        service_max = RuleEngineService(penalty_per_flag=1.0)
        self.assertEqual(service_max.penalty_per_flag, 1.0)

    def test_invalid_penalty_types(self) -> None:
        invalid_types = [True, False, "0.05", None, [], {}, (0.05,)]
        for val in invalid_types:
            with self.subTest(val=val):
                with self.assertRaises(TypeError):
                    RuleEngineService(penalty_per_flag=val)

    def test_invalid_penalty_ranges_and_non_finite(self) -> None:
        invalid_values = [
            -0.01,
            -1.0,
            1.01,
            2.0,
            float("nan"),
            float("inf"),
            float("-inf"),
        ]
        for val in invalid_values:
            with self.subTest(val=val):
                with self.assertRaises(RuleConfigError):
                    RuleEngineService(penalty_per_flag=val)

    def test_result_immutability(self) -> None:
        result = RuleValidationResult.empty()
        with self.assertRaises(FrozenInstanceError):
            result.rule_score = 0.5  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            result.credibility_penalty = 0.5  # type: ignore[misc]

        with self.assertRaises(FrozenInstanceError):
            result.flags = {}  # type: ignore[misc]

    def test_result_flags_direct_mutation_raises_type_error(self) -> None:
        result = RuleValidationResult.empty()
        with self.assertRaises(TypeError):
            result.flags["excessive_capitalization"] = True  # type: ignore[index]

        with self.assertRaises(TypeError):
            del result.flags["excessive_capitalization"]  # type: ignore[attr-defined]

    def test_result_defensive_copy_of_flags(self) -> None:
        flags = {k: False for k in VALID_RULE_FLAGS}
        result = RuleValidationResult(
            flags=flags,
            triggered_count=0,
            credibility_penalty=0.0,
            rule_score=1.0,
            observations=(),
        )
        # Mutate the original dictionary passed into constructor
        flags["excessive_capitalization"] = True
        self.assertFalse(result.flags["excessive_capitalization"])

    def test_to_dict_mutability_isolation_and_json_serialization(self) -> None:
        result = RuleValidationResult.empty()
        data = result.to_dict()

        # Mutate dictionary returned by to_dict()
        data["flags"]["excessive_capitalization"] = True
        self.assertFalse(result.flags["excessive_capitalization"])

        # Original result.to_dict() still has False and json.dumps succeeds
        serialized_result = json.dumps(result.to_dict())
        self.assertIn('"excessive_capitalization": false', serialized_result)

        # Mutated copy also serializes cleanly without mappingproxy error
        serialized_data = json.dumps(data)
        self.assertIn('"excessive_capitalization": true', serialized_data)

    def test_result_invariant_flags_structure(self) -> None:
        # Missing keys
        with self.assertRaises(RuleInputError):
            RuleValidationResult(
                flags={"excessive_capitalization": False},
                triggered_count=0,
                credibility_penalty=0.0,
                rule_score=1.0,
                observations=(),
            )

        # Extra keys
        extra_flags = {k: False for k in VALID_RULE_FLAGS}
        extra_flags["unknown_flag"] = False
        with self.assertRaises(RuleInputError):
            RuleValidationResult(
                flags=extra_flags,
                triggered_count=0,
                credibility_penalty=0.0,
                rule_score=1.0,
                observations=(),
            )

        # Non-boolean flag values
        invalid_flag_values = {k: False for k in VALID_RULE_FLAGS}
        invalid_flag_values["excessive_capitalization"] = 1  # integer instead of bool
        with self.assertRaises(TypeError):
            RuleValidationResult(
                flags=invalid_flag_values,
                triggered_count=0,
                credibility_penalty=0.0,
                rule_score=1.0,
                observations=(),
            )

    def test_result_invariant_triggered_count_mismatch(self) -> None:
        flags = {k: False for k in VALID_RULE_FLAGS}
        flags["excessive_capitalization"] = True  # 1 flag is True

        # Claiming triggered_count is 0 when 1 flag is True
        with self.assertRaises(RuleEngineError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=0.05,
                rule_score=0.95,
                observations=(),
            )

    def test_result_invariant_score_and_penalty_mismatch(self) -> None:
        flags = {k: False for k in VALID_RULE_FLAGS}
        # Penalty is 0.10, but score is not 0.90
        with self.assertRaises(RuleEngineError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=0.10,
                rule_score=0.80,
                observations=(),
            )

    def test_result_invariant_non_numeric_or_bool_scores(self) -> None:
        flags = {k: False for k in VALID_RULE_FLAGS}
        with self.assertRaises(TypeError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=False,  # bool rejected
                rule_score=1.0,
                observations=(),
            )

        with self.assertRaises(TypeError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=0.0,
                rule_score=True,  # bool rejected
                observations=(),
            )

    def test_result_invariant_non_finite_scores(self) -> None:
        flags = {k: False for k in VALID_RULE_FLAGS}
        with self.assertRaises(RuleEngineError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=float("nan"),
                rule_score=1.0,
                observations=(),
            )

        with self.assertRaises(RuleEngineError):
            RuleValidationResult(
                flags=flags,
                triggered_count=0,
                credibility_penalty=0.0,
                rule_score=float("inf"),
                observations=(),
            )

    def test_result_to_dict_and_empty_factory(self) -> None:
        empty_res = RuleValidationResult.empty()
        self.assertEqual(empty_res.triggered_count, 0)
        self.assertEqual(empty_res.credibility_penalty, 0.0)
        self.assertEqual(empty_res.rule_score, 1.0)
        self.assertFalse(empty_res.has_flags)
        self.assertEqual(empty_res.credibility_penalty_percentage, 0)
        self.assertEqual(empty_res.rule_score_percentage, 100)

        data = empty_res.to_dict()
        self.assertIn("flags", data)
        self.assertIn("triggered_count", data)
        self.assertIn("credibility_penalty", data)
        self.assertIn("rule_score", data)
        self.assertIn("observations", data)
        self.assertEqual(len(data["flags"]), 6)


class RuleEngineIndividualRulesTests(SimpleTestCase):
    """Tests each of the six individual heuristic rules with positive and negative cases."""

    def setUp(self) -> None:
        self.service = RuleEngineService()

    # 1. excessive_capitalization
    def test_excessive_capitalization_positive_all_caps(self) -> None:
        res = self.service.evaluate("THIS IS A SHOUTING HEADLINE FROM AN UNKNOWN BLOG")
        self.assertTrue(res.flags["excessive_capitalization"])

    def test_excessive_capitalization_positive_consecutive_caps(self) -> None:
        res = self.service.evaluate(
            "According to unverified sources, SECRET GOVERNMENT PLOT was revealed."
        )
        self.assertTrue(res.flags["excessive_capitalization"])

    def test_excessive_capitalization_negative_normal_headline(self) -> None:
        res = self.service.evaluate(
            "The president addressed the nation yesterday evening regarding healthcare reforms."
        )
        self.assertFalse(res.flags["excessive_capitalization"])

    def test_excessive_capitalization_negative_acronyms(self) -> None:
        # Acronyms such as NASA, WHO, and COVID should not trigger false positive shouting
        res = self.service.evaluate(
            "NASA and WHO announce new COVID research guidelines across member states."
        )
        self.assertFalse(res.flags["excessive_capitalization"])

    def test_excessive_capitalization_negative_short_acronym(self) -> None:
        res = self.service.evaluate("NASA launches mission")
        self.assertFalse(res.flags["excessive_capitalization"])

    # 2. duplicate_punctuation
    def test_duplicate_punctuation_positive(self) -> None:
        test_cases = [
            "Stop this right now!!!",
            "Is this really happening????",
            "Unbelievable discovery!?!?",
            "Look at this,, why;;",
            "Hidden documents revealed.....",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["duplicate_punctuation"])

    def test_duplicate_punctuation_negative(self) -> None:
        test_cases = [
            "The study was published in 2024. It showed promising results.",
            "Congratulations on the new achievement!",
            "What are the newly established safety guidelines?",
            "The preliminary findings were inconclusive...",  # Standard 3-dot ellipsis
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertFalse(res.flags["duplicate_punctuation"])

    # 3. clickbait_phrases
    def test_clickbait_phrases_positive(self) -> None:
        test_cases = [
            "You won't believe what happened next in this unbelievable story",
            "Scientists discover this one simple trick to improve battery life",
            "They don't want you to know the secret truth about nutrition",
            "Watch what happens when researchers conduct this test",
            "Number 7 will shock you when you see the final outcome",
            "Urgent disclosure before it gets taken down by authorities",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["clickbait_phrases"])

    def test_clickbait_phrases_negative(self) -> None:
        res = self.service.evaluate(
            "Department of Transportation releases quarterly highway infrastructure budget."
        )
        self.assertFalse(res.flags["clickbait_phrases"])

    # 4. sensational_language
    def test_sensational_language_positive(self) -> None:
        test_cases = [
            "BREAKING: New report reveals unexpected industrial shifts",
            "URGENT: Water authorities confirm temporary maintenance",
            "Underground laboratory develops miracle cure for cancer",
            "Independent investigators uncover shocking truth behind the scandal",
            "Whistleblower provides bombshell testimony to committee members",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["sensational_language"])

    def test_sensational_language_negative(self) -> None:
        res = self.service.evaluate(
            "Clinical trial data indicates statistically significant improvements in recovery."
        )
        self.assertFalse(res.flags["sensational_language"])

    # 5. short_or_vague_claim
    def test_short_or_vague_claim_positive(self) -> None:
        test_cases = [
            "Vaccines",
            "Vaccines bad",
            "Earth is flat",
            "Stop 5G towers now",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["short_or_vague_claim"])

    def test_short_or_vague_claim_negative(self) -> None:
        test_cases = [
            "Earth is not completely flat",  # 5 words
            "The central bank lowered benchmark interest rates by twenty-five basis points.",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertFalse(res.flags["short_or_vague_claim"])

    # 6. spam_patterns
    def test_spam_patterns_positive_urls(self) -> None:
        test_cases = [
            "Check the full report at https://unverified-link.com/report",
            "Details available on http://example-tracker.org",
            "Download free software directly at bit.ly/free-tools-2024",
            "See the official mirror at tinyurl.com/fast-access",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["spam_patterns"])

    def test_spam_patterns_positive_commercial_phrases(self) -> None:
        test_cases = [
            "Click here to claim your guaranteed reward today",
            "Limited time offer: buy now and receive a 100% free gift",
            "Earn cash fast with this brand new method",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                res = self.service.evaluate(text)
                self.assertTrue(res.flags["spam_patterns"])

    def test_spam_patterns_negative(self) -> None:
        res = self.service.evaluate(
            "Meteorologists predict mild temperatures and clear skies over the weekend."
        )
        self.assertFalse(res.flags["spam_patterns"])


class RuleEngineScoringAndArchitectureTests(SimpleTestCase):
    """Tests architecture specifications, penalty formulas, and score clamping."""

    def setUp(self) -> None:
        self.service = RuleEngineService(penalty_per_flag=0.05)

    def test_architecture_specification_example(self) -> None:
        """
        Validates Stage 6 Rule Engine example from ARCHITECTURE.md:
        Input: 'BREAKING!!! GOVERNMENT HIDES SECRET CURE!!!'
        Flags: excessive_capitalization, duplicate_punctuation, sensational_language.
        Output: flags = 3, credibility_penalty = 0.15, rule_score = 0.85.
        """
        claim = "BREAKING!!! GOVERNMENT HIDES SECRET CURE!!!"
        res = self.service.evaluate(claim)

        # Verify exact triggered flags
        self.assertTrue(res.flags["excessive_capitalization"])
        self.assertTrue(res.flags["duplicate_punctuation"])
        self.assertTrue(res.flags["sensational_language"])
        self.assertFalse(res.flags["clickbait_phrases"])
        self.assertFalse(res.flags["short_or_vague_claim"])  # 5 words: not <= 4
        self.assertFalse(res.flags["spam_patterns"])

        # Verify aggregate metrics
        self.assertEqual(res.triggered_count, 3)
        self.assertAlmostEqual(res.credibility_penalty, 0.15, places=4)
        self.assertAlmostEqual(res.rule_score, 0.85, places=4)
        self.assertEqual(len(res.observations), 3)

    def test_clean_claim_scores(self) -> None:
        claim = "NASA and European Space Agency researchers publish collaborative climate dataset."
        res = self.service.evaluate(claim)
        self.assertEqual(res.triggered_count, 0)
        self.assertEqual(res.credibility_penalty, 0.0)
        self.assertEqual(res.rule_score, 1.0)
        self.assertFalse(res.has_flags)
        self.assertEqual(res.observations, ())

    def test_penalty_saturation_and_clamping(self) -> None:
        # High penalty per flag to test capping at 1.0
        aggressive_service = RuleEngineService(penalty_per_flag=0.40)
        claim = (
            "BREAKING!!! GOVERNMENT HIDES SECRET CURE!!!"  # 3 flags -> 3 * 0.40 = 1.20
        )
        res = aggressive_service.evaluate(claim)

        self.assertEqual(res.triggered_count, 3)
        self.assertEqual(res.credibility_penalty, 1.0)  # Clamped at 1.0
        self.assertEqual(res.rule_score, 0.0)  # 1.0 - 1.0 = 0.0


class RuleEngineInputAndPrivacyTests(SimpleTestCase):
    """Tests input validation and privacy constraints."""

    def setUp(self) -> None:
        self.service = RuleEngineService()

    def test_non_string_inputs_raise_type_error(self) -> None:
        invalid_inputs = [None, 123, 45.6, True, ["claim"], {"text": "claim"}]
        for inp in invalid_inputs:
            with self.subTest(inp=inp):
                with self.assertRaises(TypeError):
                    self.service.evaluate(inp)  # type: ignore[arg-type]

    def test_empty_or_whitespace_inputs_raise_rule_input_error(self) -> None:
        invalid_texts = ["", "   ", "\t\t", "\n\n", " \t \r\n "]
        for text in invalid_texts:
            with self.subTest(text=repr(text)):
                with self.assertRaises(RuleInputError):
                    self.service.evaluate(text)

    def test_privacy_guarantees(self) -> None:
        sensitive_claim = "User 98412 submitted secret account 555-1234 on https://bit.ly/confidential"
        res = self.service.evaluate(sensitive_claim)

        # Observations must be generic and never interpolate the raw text
        for obs in res.observations:
            self.assertNotIn("User 98412", obs)
            self.assertNotIn("555-1234", obs)
            self.assertNotIn("bit.ly", obs)

        # Dictionary representation contains no raw claim field
        data = res.to_dict()
        self.assertNotIn("claim_text", data)
        self.assertNotIn("user_id", data)
