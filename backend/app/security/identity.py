from typing import Dict, Any, Optional


def get_effective_identity(user: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """Return a normalized identity map with numeric `user_id` and `api_key_id`.

    - If the user is a real user (has numeric `id`), `user_id` is that int.
    - If the user is an API key identity, `user_id` will be None and `api_key_id` numeric when available.
    """
    if user is None:
        return {"user_id": None, "api_key_id": None, "identity_type": None}

    # If middleware populated a normalized user, it may already have `identity_type`
    identity_type = user.get("identity_type") if isinstance(user, dict) else None

    # Try to parse numeric user id
    user_id = None
    api_key_id = None
    try:
        if isinstance(user.get("id"), int):
            user_id = int(user.get("id"))
        else:
            # sometimes id is string 'api_key:123' or 'user:45'
            uid = str(user.get("id") or "")
            if uid.startswith("user:") and uid.split(":", 1)[1].isdigit():
                user_id = int(uid.split(":", 1)[1])
            elif uid.isdigit():
                user_id = int(uid)
    except Exception:
        user_id = None

    try:
        if identity_type == "api_key":
            api_key_id = user.get("api_key_id") or user.get("id")
            if isinstance(api_key_id, str) and api_key_id.isdigit():
                api_key_id = int(api_key_id)
    except Exception:
        api_key_id = None

    # Fallback: if no identity_type but `api_key_id` present
    if api_key_id is None:
        try:
            if isinstance(user.get("api_key_id"), int):
                api_key_id = user.get("api_key_id")
        except Exception:
            pass

    return {"user_id": user_id, "api_key_id": api_key_id, "identity_type": identity_type}
