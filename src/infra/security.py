"""Optional RBC SSL certificate setup."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import rbc_security

    _RBC_SECURITY_AVAILABLE = True
except ImportError:
    _RBC_SECURITY_AVAILABLE = False


def configure_rbc_security_certs() -> Optional[str]:
    """Enable RBC SSL certificates when the optional rbc_security package exists."""
    if not _RBC_SECURITY_AVAILABLE:
        logger.debug("rbc_security is not installed; skipping SSL certificate setup")
        return None

    logger.info("Enabling RBC SSL certificates via rbc_security")
    rbc_security.enable_certs()
    return "rbc_security"

