"""Transient typing-analysis calculations; attempts are never persisted."""

import math
from statistics import fmean, pstdev

from fastapi import HTTPException

from .biometrics import distance, summarize, validate_features

MAX_EVENT_TIME_MS = 300_000
MIN_DWELL_SAMPLES = 10
TYPING_SAMPLES = (
    "My typing rhythm protects my files.",
    "Every keystroke follows my natural pace.",
    "My unique rhythm helps keep my files secure.",
)


def _rounded(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _matching_character_count(expected_text: str, typed_text: str) -> int:
    previous = [0] * (len(typed_text) + 1)
    for expected_character in expected_text:
        current = [0]
        for index, typed_character in enumerate(typed_text, start=1):
            if expected_character == typed_character:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[index - 1]))
        previous = current
    return previous[-1]


def analyze_sample(attempt: dict, expected_text: str, sample_number: int) -> dict:
    """Derive speed, accuracy and rhythm from validated browser event timestamps."""
    typed_text = attempt["typed_text"]
    events = attempt["events"]
    active_keys: dict[str, tuple[str, float]] = {}
    dwells: list[float] = []
    flights: list[float] = []
    printable_downs: list[float] = []
    entered_characters: list[str] = []
    last_printable_up: float | None = None
    previous_time = -1.0
    printable_keydowns = 0

    for event in events:
        timestamp = event["time_ms"]
        key = event["key"]
        code = event["code"]
        kind = event["kind"]
        repeat = event["repeat"]
        if (
            not math.isfinite(timestamp)
            or timestamp < previous_time
            or timestamp < 0
            or timestamp > MAX_EVENT_TIME_MS
        ):
            raise HTTPException(status_code=400, detail="Invalid or out-of-order key timestamps.")
        previous_time = timestamp

        if kind == "keydown":
            if key != "Backspace" and len(key) != 1:
                raise HTTPException(status_code=400, detail="Invalid key event in typing sample.")
            if repeat:
                if code not in active_keys:
                    raise HTTPException(status_code=400, detail="Invalid repeated key event.")
            elif code in active_keys:
                raise HTTPException(status_code=400, detail="Unmatched keydown event.")
            else:
                active_keys[code] = (key, timestamp)

            if key == "Backspace":
                if entered_characters:
                    entered_characters.pop()
            else:
                entered_characters.append(key)
                printable_keydowns += 1
                printable_downs.append(timestamp)
                if last_printable_up is not None:
                    flights.append(max(0.0, timestamp - last_printable_up))
        else:
            started = active_keys.pop(code, None)
            if started is None:
                raise HTTPException(status_code=400, detail="Unmatched keyup event.")
            down_key, down_time = started
            if down_key != "Backspace":
                dwells.append(timestamp - down_time)
                last_printable_up = timestamp

    if active_keys:
        raise HTTPException(status_code=400, detail="Typing sample contains an unfinished key press.")

    correct_characters = _matching_character_count(expected_text, typed_text)
    trace_matches_text = typed_text == "".join(entered_characters)
    accuracy = correct_characters / max(len(expected_text), len(typed_text), 1)
    elapsed_ms = (
        events[-1]["time_ms"] - printable_downs[0]
        if printable_downs and events
        else None
    )
    wpm = (
        len(typed_text) / 5 / (elapsed_ms / 60_000)
        if elapsed_ms is not None and elapsed_ms > 0
        else None
    )
    mean_dwell = fmean(dwells) if dwells else None
    mean_flight = fmean(flights) if flights else None
    flight_cv = (
        pstdev(flights) / mean_flight
        if len(flights) > 1 and mean_flight is not None and mean_flight > 0
        else None
    )
    rhythm_consistency = 100 / (1 + flight_cv) if flight_cv is not None else None
    text_complete = len(typed_text) >= len(expected_text)
    enough_timing = len(dwells) >= MIN_DWELL_SAMPLES
    complete = (
        text_complete
        and trace_matches_text
        and enough_timing
        and mean_dwell is not None
        and mean_dwell > 0
        and flight_cv is not None
        and elapsed_ms is not None
        and elapsed_ms > 0
    )
    if not text_complete:
        completion_message = "The phrase was incomplete or did not match exactly."
    elif not trace_matches_text:
        completion_message = (
            "The typed text did not match the recorded keys. Pasted or unsupported "
            "input cannot be scored; type the prompt using a keyboard."
        )
    elif not enough_timing:
        completion_message = "Not enough real key timing was captured; use a keyboard and try again."
    elif mean_dwell is None or mean_dwell <= 0 or flight_cv is None:
        completion_message = "The key timing was too short to analyze reliably; try again."
    elif elapsed_ms is None or elapsed_ms <= 0:
        completion_message = "The sample needs valid key timing; try again."
    elif typed_text != expected_text:
        completion_message = "The phrase contains typing errors; accuracy is reduced accordingly."
    else:
        completion_message = None

    return {
        "sample_number": sample_number,
        "complete": complete,
        "text_matches": typed_text == expected_text,
        "completion_message": completion_message,
        "total_time_seconds": _rounded(elapsed_ms / 1000 if elapsed_ms is not None else None),
        "wpm": _rounded(wpm),
        "correct_characters": correct_characters,
        "typed_characters": len(typed_text),
        "accuracy_percent": _rounded(accuracy * 100),
        "average_dwell_ms": _rounded(mean_dwell),
        "average_inter_key_latency_ms": _rounded(mean_flight),
        "rhythm_consistency_percent": _rounded(rhythm_consistency),
        "features": {
            "mean_dwell": mean_dwell,
            "mean_flight": mean_flight,
            "std_flight": pstdev(flights) if len(flights) > 1 else 0.0,
            "count": float(len(dwells)),
        },
        "accuracy_fraction": accuracy,
        "flight_cv": flight_cv,
        "printable_keydowns": printable_keydowns,
    }


def analyze_test(attempts: list[dict], expected_samples: list[str], baseline: dict | None) -> dict:
    """Summarize exactly three prompt attempts and optionally compare an enrolled baseline."""
    if len(attempts) != 3 or len(expected_samples) != 3:
        raise HTTPException(status_code=400, detail="Exactly three typing samples are required.")

    samples = [
        analyze_sample(attempt, expected_samples[index], index + 1)
        for index, attempt in enumerate(attempts)
    ]
    complete = all(sample["complete"] for sample in samples)
    speeds = [sample["wpm"] for sample in samples if sample["wpm"] is not None]
    average_wpm = fmean(speeds) if speeds else None

    keystroke_score = None
    score_breakdown = None
    consistency_summary = None
    baseline_similarity = None
    baseline_message = "Complete typing enrollment to compare this test with your saved baseline."

    if complete:
        dwell_means = [sample["features"]["mean_dwell"] for sample in samples]
        flight_means = [sample["features"]["mean_flight"] for sample in samples]
        cross_sample_scores = []
        for values in (dwell_means, flight_means):
            mean_value = fmean(values)
            cv = pstdev(values) / mean_value if mean_value else 0.0
            cross_sample_scores.append(100 / (1 + cv))
        cross_sample_consistency = fmean(cross_sample_scores)

        sample_scores = []
        for sample in samples:
            rhythm_score = sample["rhythm_consistency_percent"]
            sample_score = (
                0.40 * sample["accuracy_fraction"] * 100
                + 0.30 * rhythm_score
                + 0.30 * cross_sample_consistency
            )
            sample["keystroke_score"] = _rounded(sample_score)
            sample_scores.append(sample_score)
        keystroke_score = _rounded(fmean(sample_scores))
        score_breakdown = {
            "accuracy_percent": _rounded(
                fmean(sample["accuracy_fraction"] * 100 for sample in samples)
            ),
            "within_sample_rhythm_percent": _rounded(
                fmean(sample["rhythm_consistency_percent"] for sample in samples)
            ),
            "between_sample_consistency_percent": _rounded(cross_sample_consistency),
        }
        consistency_summary = (
            "Very consistent across these three samples."
            if cross_sample_consistency >= 85
            else "Fairly consistent across these three samples."
            if cross_sample_consistency >= 70
            else "Typing rhythm varied across these three samples."
        )

        if baseline is not None:
            current_features = summarize(
                [{"features": sample["features"]} for sample in samples]
            )
            enrolled_features = validate_features(baseline)
            baseline_similarity = _rounded((1 - distance(enrolled_features, current_features)) * 100)
            baseline_message = (
                "Prototype feature similarity only; it is not an identity probability "
                "or a validated accuracy percentage."
            )
    elif baseline is not None:
        baseline_message = (
            "Complete all three prompts with valid key timing to compare your "
            "rhythm with the enrolled baseline."
        )

    for sample in samples:
        sample.pop("accuracy_fraction")
        sample.pop("flight_cv")
        sample.pop("printable_keydowns")
        if not complete:
            sample["keystroke_score"] = None

    return {
        "complete": complete,
        "samples": samples,
        "average_wpm": _rounded(average_wpm),
        "keystroke_score": keystroke_score,
        "score_breakdown": score_breakdown,
        "consistency_summary": consistency_summary,
        "baseline_available": baseline is not None,
        "baseline_similarity_percent": baseline_similarity,
        "baseline_message": baseline_message,
        "score_note": (
            "Each sample score is 40% final-text accuracy, 30% within-sample "
            "inter-key rhythm consistency, and 30% consistency of mean dwell "
            "and inter-key times across all three samples. Speed does not affect "
            "the score."
        ),
    }
