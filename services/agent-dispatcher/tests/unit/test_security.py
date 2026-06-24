"""Security tests — skipped: src.core.security was removed in Keycloak migration (T063).

Service tokens are now obtained via KeycloakServiceClient (keycloak_client.py).
See test_keycloak_client.py for the replacement coverage.
"""

import pytest

pytestmark = pytest.mark.skip(reason="src.core.security removed in Keycloak IAM migration")
