from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from afi_os.db import Base, SessionLocal, engine
from afi_os.enums import (
    AdvertiserClassification,
    PermissionStatus,
    ProgramStatus,
    WatchStatus,
)
from afi_os.models import (
    AdObservation,
    Advertiser,
    AffiliateNetwork,
    Merchant,
    Program,
    Project,
)


def seed_demo() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.scalar(select(Project.id).limit(1)) is not None:
            print("Demo seed skipped: database already contains projects")
            return

        network = AffiliateNetwork(
            name="Demo Self-Serve Network",
            platform_type="DEMO",
            supports_api=False,
            supports_subid=True,
        )
        merchant = Merchant(name="Pictory Demo", website_domain="pictory.example")
        program = Program(
            merchant=merchant,
            network=network,
            name="Pictory Demo Affiliate",
            status=ProgramStatus.DISCOVERED,
            paid_search_permission=PermissionStatus.AMBIGUOUS,
            brand_keyword_permission=PermissionStatus.AMBIGUOUS,
            non_brand_permission=PermissionStatus.APPROVAL_REQUIRED,
            direct_link_permission=PermissionStatus.NOT_CHECKED,
        )
        project_a = Project(
            domain="pictory.example",
            brand_name="Pictory Demo",
            category="AI video",
            affiliate_program_found=True,
            program=program,
            watch_status=WatchStatus.HIGH_VALUE,
        )
        project_b = Project(
            domain="mubert.example",
            brand_name="Mubert Demo",
            category="AI music",
            affiliate_program_found=True,
            watch_status=WatchStatus.WATCH,
        )
        db.add_all([network, merchant, program, project_a, project_b])
        db.flush()

        now = datetime.now(timezone.utc)
        advertisers = [
            Advertiser(
                verified_name="Northstar Media Demo",
                verified_location="US",
                classification=AdvertiserClassification.AFFILIATE_OR_PUBLISHER,
                confidence=0.78,
                first_seen_at=now - timedelta(days=44),
                last_seen_at=now - timedelta(days=1),
            ),
            Advertiser(
                verified_name="Creator Tools Lab Demo",
                verified_location="GB",
                classification=AdvertiserClassification.AFFILIATE_OR_PUBLISHER,
                confidence=0.71,
                first_seen_at=now - timedelta(days=28),
                last_seen_at=now - timedelta(days=2),
            ),
            Advertiser(
                verified_name="Growth Stack Demo",
                verified_location="SG",
                classification=AdvertiserClassification.AGENCY,
                confidence=0.62,
                first_seen_at=now - timedelta(days=12),
                last_seen_at=now,
            ),
        ]
        db.add_all(advertisers)
        db.flush()

        observations = [
            AdObservation(
                advertiser_id=advertisers[0].id,
                project_id=project_a.id,
                source_url="https://adstransparency.google.com/demo/1",
                headline="AI video workflow demo",
                landing_domain="review.example",
                country="US",
                snapshot_date=date.today(),
                first_seen_at=now - timedelta(days=40),
                last_seen_at=now - timedelta(days=1),
                content_hash="demo-observation-1".ljust(64, "0")[:64],
            ),
            AdObservation(
                advertiser_id=advertisers[1].id,
                project_id=project_a.id,
                source_url="https://adstransparency.google.com/demo/2",
                headline="Create videos faster demo",
                landing_domain="tools.example",
                country="GB",
                snapshot_date=date.today(),
                first_seen_at=now - timedelta(days=25),
                last_seen_at=now - timedelta(days=2),
                content_hash="demo-observation-2".ljust(64, "0")[:64],
            ),
            AdObservation(
                advertiser_id=advertisers[2].id,
                project_id=project_a.id,
                source_url="https://adstransparency.google.com/demo/3",
                headline="AI video comparison demo",
                landing_domain="compare.example",
                country="SG",
                snapshot_date=date.today(),
                first_seen_at=now - timedelta(days=10),
                last_seen_at=now,
                content_hash="demo-observation-3".ljust(64, "0")[:64],
            ),
            AdObservation(
                advertiser_id=advertisers[0].id,
                project_id=project_b.id,
                source_url="https://adstransparency.google.com/demo/4",
                headline="AI music demo",
                landing_domain="review.example",
                country="US",
                snapshot_date=date.today(),
                first_seen_at=now - timedelta(days=8),
                last_seen_at=now - timedelta(days=1),
                content_hash="demo-observation-4".ljust(64, "0")[:64],
            ),
        ]
        db.add_all(observations)
        db.commit()
        print("Demo data inserted")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
