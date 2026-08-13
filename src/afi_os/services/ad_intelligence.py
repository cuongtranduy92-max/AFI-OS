import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AdvertiserScoreInput:
    distinct_advertisers: int
    active_advertisers_30d: int
    top_advertiser_share: float
    new_advertisers_30d: int


@dataclass(frozen=True)
class AdvertiserScoreResult:
    score: int
    label: str
    components: dict[str, float]


def independent_advertiser_score(data: AdvertiserScoreInput) -> AdvertiserScoreResult:
    if data.distinct_advertisers < 0 or data.active_advertisers_30d < 0:
        raise ValueError("advertiser counts must be non-negative")
    if not 0 <= data.top_advertiser_share <= 1:
        raise ValueError("top_advertiser_share must be between 0 and 1")
    if data.new_advertisers_30d < 0:
        raise ValueError("new_advertisers_30d must be non-negative")

    breadth = min(40.0, 12.0 * math.log1p(data.distinct_advertisers))
    active = min(25.0, 7.0 * math.log1p(data.active_advertisers_30d))
    diversity = 25.0 * (1.0 - data.top_advertiser_share)
    momentum = min(10.0, 3.5 * math.log1p(data.new_advertisers_30d))
    score = int(round(min(100.0, breadth + active + diversity + momentum)))

    if data.distinct_advertisers <= 2:
        label = "INSUFFICIENT_EVIDENCE"
    elif score >= 75:
        label = "HIGH_DIVERSITY"
    elif score >= 50:
        label = "MULTIPLE_ADVERTISERS"
    elif score >= 30:
        label = "EMERGING"
    else:
        label = "CONCENTRATED"

    return AdvertiserScoreResult(
        score=score,
        label=label,
        components={
            "breadth": round(breadth, 2),
            "active_30d": round(active, 2),
            "diversity": round(diversity, 2),
            "momentum": round(momentum, 2),
        },
    )
