#!/usr/bin/env python3
"""
Test runner for Ported 14_micro_pluggy (pluggy plugin engine in PythonSharp).
Builds the project with `psc` and validates hookspecs, hook implementations, plugin discovery,
multi-result accumulation, firstresult mode, and dynamic unregistration.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroPluggy via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir), "-o", str(dist_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir), "-o", str(dist_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported Pluggy Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_pluggy import PluginManager
    except ImportError as e:
        print(f"Failed to import micro_pluggy: {e}", file=sys.stderr)
        return 1

    # 1. Define Hook Specifications
    class CoreSpecs:
        def on_user_signup(self, username: str, email: str):
            """Invoked after user creates an account."""
            pass

        def get_auth_token(self, user_id: int):
            """First-result-wins auth strategy."""
            pass

    # Mark firstresult on get_auth_token
    CoreSpecs.get_auth_token._firstresult = True  # type: ignore[attr-defined]

    pm = PluginManager("test_auth_system")
    pm.add_hookspecs(CoreSpecs)
    assert pm.has_hook("on_user_signup") is True
    assert pm.has_hook("get_auth_token") is True
    assert pm.has_hook("non_existent_hook") is False
    print("[PASS] Hook specifications (multi-result & firstresult) registered successfully")

    # 2. Register Plugin Implementations
    class EmailNotificationPlugin:
        def on_user_signup(self, username: str, email: str) -> str:
            return f"Welcome email queued for {email}"

    class AuditLoggerPlugin:
        def on_user_signup(self, username: str, email: str) -> str:
            return f"Audit: user {username} registered in db"

    email_plugin = EmailNotificationPlugin()
    audit_plugin = AuditLoggerPlugin()
    pm.register(email_plugin)
    pm.register(audit_plugin)
    assert len(pm.get_plugins()) == 2
    print("[PASS] Plugin registration and automatic method discovery verified")

    # 3. Call Hook and Accumulate Results
    signup_results = pm.call("on_user_signup", ["Ada", "ada@example.com"])
    assert len(signup_results) == 2
    assert signup_results[0] == "Welcome email queued for ada@example.com"
    assert signup_results[1] == "Audit: user Ada registered in db"
    print(f"[PASS] Multi-result hook execution: {signup_results}")

    # 4. FirstResult Execution Strategy
    class CustomAuthPlugin:
        def get_auth_token(self, user_id: int) -> str:
            return f"TOKEN-CUSTOM-{user_id}"

    class FallbackAuthPlugin:
        def get_auth_token(self, user_id: int) -> str:
            return f"TOKEN-FALLBACK-{user_id}"

    pm.register(CustomAuthPlugin())
    pm.register(FallbackAuthPlugin())

    token_results = pm.call("get_auth_token", [90210])
    assert len(token_results) == 1
    assert token_results[0] == "TOKEN-CUSTOM-90210"
    print(f"[PASS] FirstResult strategy returned first non-null token: {token_results[0]}")

    # 5. Dynamic Unregistration
    pm.unregister(email_plugin)
    assert len(pm.get_plugins()) == 3  # audit, custom, fallback
    remaining_results = pm.call("on_user_signup", ["Grace", "grace@example.com"])
    assert len(remaining_results) == 1
    assert remaining_results[0] == "Audit: user Grace registered in db"
    print("[PASS] Dynamic unregistration verified")

    print("\nAll micro-pluggy verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

