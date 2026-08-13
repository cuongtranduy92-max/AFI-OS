from afi_os.services.ad_intelligence import AdvertiserScoreInput, independent_advertiser_score


def test_score_penalizes_concentration() -> None:
    diverse = independent_advertiser_score(
        AdvertiserScoreInput(10, 8, 0.20, 3)
    )
    concentrated = independent_advertiser_score(
        AdvertiserScoreInput(10, 8, 0.90, 3)
    )
    assert diverse.score > concentrated.score
    assert diverse.label in {"MULTIPLE_ADVERTISERS", "HIGH_DIVERSITY"}


def test_one_advertiser_is_insufficient_evidence() -> None:
    result = independent_advertiser_score(AdvertiserScoreInput(1, 1, 1.0, 0))
    assert result.label == "INSUFFICIENT_EVIDENCE"
