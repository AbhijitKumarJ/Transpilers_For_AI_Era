"""Sample 03: Pydantic v2 Schema Models defined in PythonSharp and consumed in Python."""

import importlib.util
import sys
from pathlib import Path

out_dir = Path(__file__).parent / "dist"
sys.path.insert(0, str(out_dir))

has_pydantic = importlib.util.find_spec("pydantic") is not None
if has_pydantic:
    from pydantic import ValidationError  # noqa: E402
    from web_models import AuthSession, UserProfile  # noqa: E402

if __name__ == "__main__":
    generated_file = out_dir / "web_models.py"
    print("--- Transpiled Pydantic Module (`dist/web_models.py`) ---")
    if generated_file.exists():
        print(generated_file.read_text(encoding="utf-8"))

    if not has_pydantic:
        print("Note: 'pydantic' package is not installed in this environment.")
        print("To run active runtime validation and serialization, install it via:")
        print("    pip install pydantic")
        print("\nNotice that PythonSharp generated clean, native Pydantic code without synthetic wrappers!")
        sys.exit(0)

    print("\n--- 1. Validating and Instantiating UserProfile ---")
    raw_payload = {
        "id": 101,
        "username": "ada_lovelace",
        "email": "ada@computing.org",
        "role": "admin",
    }
    user = UserProfile.model_validate(raw_payload)
    print("User instance:", user)
    print("Display badge:", user.display_badge())
    print("Serialized JSON:\n", user.model_dump_json(indent=2))

    print("\n--- 2. Validating Record Schema Model ---")
    session = AuthSession(token="secret-jwt-token-xyz")
    print("Session token:", session.token)
    print("Expires in (default):", session.expires_in)

    print("\n--- 3. Handling Pydantic ValidationError ---")
    try:
        UserProfile.model_validate({"id": "not-an-int", "username": "bad_user"})
    except ValidationError as e:
        print("Caught expected validation error:")
        for err in e.errors():
            print(f"  Field '{err['loc'][0]}': {err['msg']}")
