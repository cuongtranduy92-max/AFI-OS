from fastapi import APIRouter

from afi_os.api import (
    ad_intelligence,
    appraisal,
    automation,
    compliance,
    dashboard,
    economics,
    exposure,
    finance,
    health,
    operations,
    portfolio,
    programs,
    system,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(appraisal.router)
api_router.include_router(operations.router)
api_router.include_router(automation.router)
api_router.include_router(portfolio.router)
api_router.include_router(dashboard.router)
api_router.include_router(ad_intelligence.router)
api_router.include_router(economics.router)
api_router.include_router(compliance.router)
api_router.include_router(exposure.router)
api_router.include_router(programs.router)
api_router.include_router(finance.router)
api_router.include_router(system.router)
