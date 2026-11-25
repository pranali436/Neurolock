from statistics import median
from fastapi import HTTPException

FEATURE_KEYS = ("mean_dwell", "mean_flight", "std_flight", "count")


def validate_features(features: dict) -> dict:
    """Return a normalized timing-feature vector, or fail closed with HTTP 400.

    A missing, non-numeric or malformed feature vector is insufficient typing
    data. Rejecting it here keeps a bad request from reaching ``distance`` (which
    would otherwise raise an unhandled error and return HTTP 500) and ensures the
    request is never approved.
    """
    if not isinstance(features, dict) or not all(
        isinstance(features.get(k), (int, float)) for k in FEATURE_KEYS
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Not enough typing data was captured. Type the full enrolled "
                "phrase at your normal pace, then capture it again."
            ),
        )
    return {k: float(features[k]) for k in FEATURE_KEYS}


def summarize(samples: list[dict]) -> dict:
    if len(samples) < 2:
        raise HTTPException(status_code=400, detail="Please provide at least Two typing samples.")
    vectors = [validate_features(sample.get("features", {})) for sample in samples]
    return {k: float(median(v[k] for v in vectors)) for k in FEATURE_KEYS}

def distance(a: dict, b: dict) -> float:
    # Prototype only: normalize absolute feature differences. This is not a
    # validated biometric classifier and must not be used as sole security.
    scales = {"mean_dwell": 120.0, "mean_flight": 250.0, "std_flight": 200.0, "count": 20.0}
    values = [min(abs(float(a[k]) - float(b[k])) / scales[k], 1.0) for k in scales]
    return sum(values) / len(values)
