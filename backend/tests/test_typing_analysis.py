"""Tests for timestamp-based typing analysis and the authenticated API."""

import unittest
from copy import deepcopy
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.typing_analysis import TYPING_SAMPLES, analyze_sample, analyze_test


def _attempt(text, include_timing=True):
    events = []
    timestamp = 0.0
    for key in text if include_timing else "":
        code = "Space" if key == " " else f"Key{key.upper()}"
        events.append({
            "kind": "keydown",
            "key": key,
            "code": code,
            "time_ms": timestamp,
            "repeat": False,
        })
        timestamp += 40
        events.append({
            "kind": "keyup",
            "key": key,
            "code": code,
            "time_ms": timestamp,
            "repeat": False,
        })
        timestamp += 60
    return {"typed_text": text, "events": events}


class _Response:
    def __init__(self, data):
        self.data = data


class _TemplateQuery:
    def __init__(self, vector):
        self.vector = vector

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return _Response(
            {"feature_vector": self.vector} if self.vector is not None else None
        )


class _Admin:
    def __init__(self, vector=None):
        self.vector = vector

    def table(self, name):
        if name != "keystroke_templates":
            raise AssertionError(f"Unexpected table access: {name}")
        return _TemplateQuery(self.vector)


class TypingAnalysisTests(unittest.TestCase):
    def test_completed_samples_include_behavioral_scores_and_separate_speed(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        result = analyze_test(attempts, TYPING_SAMPLES, None)

        self.assertTrue(result["complete"])
        self.assertEqual(len(result["samples"]), 3)
        self.assertAlmostEqual(
            result["average_wpm"],
            sum(sample["wpm"] for sample in result["samples"]) / 3,
            places=2,
        )
        self.assertGreater(result["keystroke_score"], 0)
        self.assertEqual(
            result["samples"][0]["keystroke_score"],
            result["keystroke_score"],
        )
        self.assertEqual(result["samples"][0]["correct_characters"], len(TYPING_SAMPLES[0]))
        self.assertEqual(result["samples"][0]["accuracy_percent"], 100)
        self.assertEqual(
            result["samples"][0]["average_dwell_ms"],
            40,
        )
        self.assertEqual(
            result["samples"][0]["average_inter_key_latency_ms"],
            60,
        )
        self.assertIn("Speed does not affect", result["score_note"])

    def test_incomplete_or_pasted_text_cannot_receive_a_score(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        attempts[1] = _attempt(TYPING_SAMPLES[1], include_timing=False)
        result = analyze_test(attempts, TYPING_SAMPLES, None)

        self.assertFalse(result["complete"])
        self.assertIsNone(result["keystroke_score"])
        self.assertIsNone(result["samples"][1]["keystroke_score"])
        self.assertEqual(result["samples"][1]["average_dwell_ms"], None)
        self.assertIn("Pasted or unsupported input", result["samples"][1]["completion_message"])

    def test_empty_and_incomplete_attempts_report_no_speed_or_score(self):
        empty = {"typed_text": "", "events": []}
        sample = analyze_sample(empty, TYPING_SAMPLES[0], 1)

        self.assertFalse(sample["complete"])
        self.assertIsNone(sample["wpm"])
        self.assertIsNone(sample["total_time_seconds"])
        self.assertEqual(sample["accuracy_percent"], 0)
        self.assertFalse(analyze_test([empty] * 3, TYPING_SAMPLES, None)["complete"])

    def test_corrected_text_counts_final_accuracy_and_backspace_timing(self):
        phrase = TYPING_SAMPLES[0]
        attempt = _attempt(phrase)
        attempt["typed_text"] = phrase[:-1]
        backspace_time = attempt["events"][-1]["time_ms"] + 5
        attempt["events"].extend([
            {
                "kind": "keydown",
                "key": "Backspace",
                "code": "Backspace",
                "time_ms": backspace_time,
                "repeat": False,
            },
            {
                "kind": "keyup",
                "key": "Backspace",
                "code": "Backspace",
                "time_ms": backspace_time + 40,
                "repeat": False,
            },
        ])

        sample = analyze_sample(attempt, phrase, 1)
        self.assertFalse(sample["complete"])
        self.assertEqual(sample["correct_characters"], len(phrase) - 1)
        self.assertEqual(sample["accuracy_percent"], round(100 * (len(phrase) - 1) / len(phrase), 2))
        self.assertEqual(sample["average_dwell_ms"], 40)

    def test_completed_typo_receives_a_score_that_reflects_accuracy(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        phrase = TYPING_SAMPLES[0]
        attempts[0]["typed_text"] = f"{phrase[:-1]}x"
        last_keydown = attempts[0]["events"][-2]
        last_keyup = attempts[0]["events"][-1]
        last_keydown["key"] = "x"
        last_keydown["code"] = "KeyX"
        last_keyup["key"] = "x"
        last_keyup["code"] = "KeyX"

        result = analyze_test(attempts, TYPING_SAMPLES, None)

        self.assertTrue(result["complete"])
        self.assertFalse(result["samples"][0]["text_matches"])
        self.assertLess(result["samples"][0]["accuracy_percent"], 100)
        self.assertLess(result["samples"][0]["keystroke_score"], 100)

    def test_malformed_key_sequences_are_rejected(self):
        attempt = _attempt(TYPING_SAMPLES[0])
        attempt["events"][1]["time_ms"] = -1
        with self.assertRaises(HTTPException) as error:
            analyze_sample(attempt, TYPING_SAMPLES[0], 1)
        self.assertEqual(error.exception.status_code, 400)

    def test_baseline_similarity_is_separate_and_explicitly_nonvalidated(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        first_features = analyze_sample(attempts[0], TYPING_SAMPLES[0], 1)["features"]
        result = analyze_test(attempts, TYPING_SAMPLES, first_features)

        self.assertTrue(result["baseline_available"])
        self.assertIsNotNone(result["baseline_similarity_percent"])
        self.assertIn("not an identity probability", result["baseline_message"])

    def test_missing_baseline_has_no_invented_similarity(self):
        result = analyze_test(
            [_attempt(text) for text in TYPING_SAMPLES],
            TYPING_SAMPLES,
            None,
        )
        self.assertFalse(result["baseline_available"])
        self.assertIsNone(result["baseline_similarity_percent"])
        self.assertIn("Complete typing enrollment", result["baseline_message"])

    def test_uniformly_faster_typing_does_not_change_keystroke_score(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        faster_attempts = deepcopy(attempts)
        for attempt in faster_attempts:
            for event in attempt["events"]:
                event["time_ms"] *= 0.5

        ordinary = analyze_test(attempts, TYPING_SAMPLES, None)
        faster = analyze_test(faster_attempts, TYPING_SAMPLES, None)

        self.assertNotEqual(ordinary["average_wpm"], faster["average_wpm"])
        self.assertEqual(ordinary["keystroke_score"], faster["keystroke_score"])

    def test_repeated_attempts_are_independent_and_return_the_same_metrics(self):
        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        first = analyze_test(attempts, TYPING_SAMPLES, None)
        repeated = analyze_test(attempts, TYPING_SAMPLES, None)
        self.assertEqual(first, repeated)

    def test_authenticated_api_returns_analysis_without_persisting_attempts(self):
        import app.main as main

        attempts = [_attempt(text) for text in TYPING_SAMPLES]
        admin = _Admin()
        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: {
            "id": "user-1",
            "email": "user@example.com",
        }
        try:
            with mock.patch.object(main, "admin", admin):
                response = client.post("/api/typing-analysis", json={"samples": attempts})
        finally:
            main.app.dependency_overrides.pop(main.current_user, None)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["complete"])
        self.assertFalse(response.json()["baseline_available"])

    def test_authenticated_api_requires_three_samples(self):
        import app.main as main

        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: {
            "id": "user-1",
            "email": "user@example.com",
        }
        try:
            response = client.post("/api/typing-analysis", json={"samples": []})
        finally:
            main.app.dependency_overrides.pop(main.current_user, None)
        self.assertEqual(response.status_code, 422)

    def test_upload_requires_a_completed_typing_test(self):
        import app.main as main

        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: {
            "id": "user-1",
            "email": "user@example.com",
        }
        try:
            with mock.patch.object(main, "typing_test_completed", return_value=False):
                response = client.post(
                    "/api/files",
                    files={"file": ("example.txt", b"hello world", "text/plain")},
                )
        finally:
            main.app.dependency_overrides.pop(main.current_user, None)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Complete all three typing samples", response.json()["detail"]["message"])

    def test_completed_typing_test_allows_a_file_upload(self):
        import app.main as main

        class _InsertedResult:
            def __init__(self, payload):
                self.data = [payload]

        class _UploadInsert:
            def __init__(self, payload):
                self.payload = payload

            def execute(self):
                return _InsertedResult(self.payload)

        class _UploadTable:
            def insert(self, payload):
                return _UploadInsert(payload)

        class _FakeStorageBucket:
            def upload(self, *args, **kwargs):
                return {"ok": True}

        class _FakeStorage:
            def from_(self, *_args, **_kwargs):
                return _FakeStorageBucket()

        class _FakeAdmin:
            storage = _FakeStorage()

            def table(self, name):
                if name == "user_files":
                    return _UploadTable()
                raise AssertionError(f"Unexpected table access: {name}")

        client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: {
            "id": "user-1",
            "email": "user@example.com",
        }
        try:
            with mock.patch.object(main, "typing_test_completed", return_value=True):
                with mock.patch.object(main, "admin", _FakeAdmin()):
                    response = client.post(
                        "/api/files",
                        files={"file": ("example.txt", b"hello world", "text/plain")},
                    )
        finally:
            main.app.dependency_overrides.pop(main.current_user, None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["file"]["original_name"], "example.txt")


if __name__ == "__main__":
    unittest.main()
