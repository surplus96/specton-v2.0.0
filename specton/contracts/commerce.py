"""Explicit, reviewable defaults for a generated wholesale demonstration system."""

from typing import Annotated, Literal

from pydantic import Field

from specton.contracts.base import Contract


class CommercePolicy(Contract):
    profile: Literal["wholesale-demo-v1"] = "wholesale-demo-v1"
    storage: Literal["derived-commerce-v1"] = "derived-commerce-v1"
    source_tables: dict[str, str]
    api_ids: dict[str, str]
    defaults_acknowledged: Literal[True]
    product_note_enabled: Annotated[bool, Field(strict=True)] = False
    timezone: Literal["Asia/Seoul"] = "Asia/Seoul"
    cutoff_hour: Annotated[int, Field(strict=True, ge=0, le=23)] = 17
    expiry_days: Annotated[int, Field(strict=True, ge=1, le=365)] = 30
    return_warning_percent: Annotated[int, Field(strict=True, ge=0, le=100)] = 5
    stock_deduction: Literal["order_acceptance"] = "order_acceptance"
    shortage: Literal["reject_entire_order"] = "reject_entire_order"
    cancellation: Literal["restore_allocations"] = "restore_allocations"
    return_stock: Literal["no_automatic_restock"] = "no_automatic_restock"
    return_zero_purchase: Literal["warn_if_positive_return"] = "warn_if_positive_return"
    notifications: Literal["in_app_on_read"] = "in_app_on_read"
