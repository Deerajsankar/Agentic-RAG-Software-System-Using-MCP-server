from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp_server.security import (
    login_and_get_token,
    process_offer_letter,
    register_user,
    validate_token,
)
from mcp_server.server import get_my_profile, search_hr_policies


def main() -> None:
    print(f"Project root: {ROOT}")

    email = "demo.engineer@examplecorp.com"
    password = "DemoPassword123!"
    offer_letter = """
    ExampleCorp Offer Letter

    Congratulations! We are pleased to offer you the position of Software Engineer.
    This role will be part of the Engineering organization. Start date is contingent
    upon verification and completion of required onboarding steps.
    """

    print("\n1) Registering user credentials...")
    print(register_user(email, password))

    print("\n2) Processing offer letter (simulated AI extraction)...")
    print(process_offer_letter(email, offer_letter))

    print("\n3) Logging in and generating JWT...")
    token = login_and_get_token(email, password)
    print(f"JWT (prefix): {token[:32]}...")

    print("\n4) Validating token claims...")
    claims = validate_token(token)
    print(json.dumps(claims, indent=2))

    print("\n5) MCP tool call: get_my_profile(token)")
    profile = get_my_profile(token)
    print(json.dumps(profile, indent=2))

    print("\n6) MCP tool call: search_hr_policies(query, token)")
    query = "What are the rules for cross-border remote work and approvals?"
    hits = search_hr_policies(query=query, token=token)
    print(json.dumps(hits, indent=2))

    print("\nDone.")


if __name__ == "__main__":
    main()

