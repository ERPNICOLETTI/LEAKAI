from adapters.base import CanonicalEvent, DetectionResult
from adapters.shopify import ShopifyAdapter
from adapters.paypal import PayPalAdapter
from adapters.registry import registry, AdapterRegistry

__all__ = [
    "CanonicalEvent",
    "DetectionResult",
    "ShopifyAdapter",
    "PayPalAdapter",
    "registry",
    "AdapterRegistry"
]
