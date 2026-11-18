"""Public capability metadata; customer documents are not accessed here."""

from fastapi import APIRouter

from specton.api.deps import SettingsDep
from specton.packs.catalog import PackEntry, catalog
from specton.specification.capabilities import CAPABILITIES, Capability

router = APIRouter()


@router.get("/api/v1/packs", operation_id="listDomainPacks")
def packs(settings: SettingsDep) -> tuple[PackEntry, ...]:
    return catalog(settings.pack_root)


@router.get("/api/v1/capabilities", operation_id="listImplementationCapabilities")
def capabilities() -> tuple[Capability, ...]:
    return CAPABILITIES
