from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

SECRET_KEY = "enterprise_super_secret"


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    d = _root_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_user(email: str, password: str) -> dict[str, Any]:
    """
    Create/update a user credential record in data/auth_db.json.
    """
    email_key = email.strip().lower()
    if not email_key or "@" not in email_key:
        raise ValueError("Invalid email.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    auth_path = _data_dir() / "auth_db.json"
    db = _read_json(auth_path, default={"users": {}})

    db.setdefault("users", {})
    db["users"][email_key] = {
        "email": email_key,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(auth_path, db)
    return {"status": "ok", "email": email_key}


def _infer_clearance_and_title(letter_text: str) -> tuple[int, str, str]:
    """
    Extremely simple 'AI extraction' simulation based on keyword rules.
    Returns: (clearance_level, department, job_title)
    """
    t = (letter_text or "").lower()

    # Highest precedence keywords first.
    if "ceo" in t or "chief executive" in t:
        return 5, "Executive", "CEO"
    if "vp" in t or "vice president" in t:
        return 4, "Executive", "VP"
    if "director" in t:
        return 4, "Executive", "Director"
    if "security" in t or "infosec" in t:
        return 3, "IT", "Security Specialist"
    if "hr" in t or "people ops" in t or "human resources" in t:
        return 2, "People Ops", "HR Generalist"
    if "engineer" in t or "developer" in t:
        return 2, "Engineering", "Engineer"
    if "manager" in t:
        return 3, "Product", "Manager"

    return 1, "General", "Associate"


def _next_employee_id(employees: list[dict[str, Any]]) -> str:
    max_id = 999
    for e in employees:
        eid = str(e.get("employee_id", ""))
        if eid.startswith("E"):
            try:
                max_id = max(max_id, int(eid[1:]))
            except ValueError:
                continue
    return f"E{max_id + 1}"


def _name_from_email(email: str) -> tuple[str, str | None]:
    local = email.split("@", 1)[0].strip()
    local = local.replace("_", ".").replace("-", ".")
    parts = [p for p in local.split(".") if p]
    if not parts:
        return "New Hire", "New"
    full = " ".join(p.capitalize() for p in parts)
    preferred = parts[0].capitalize()
    return full, preferred


def process_offer_letter(email: str, letter_text: str) -> dict[str, Any]:
    """
    Simulates AI extraction from an offer letter and creates a profile in data/mock_hris_db.json.
    Keyword rules:
      - 'Director' -> clearance 4
      - 'Engineer' -> clearance 2
      - (additional rules included for realism)
    """
    email_key = email.strip().lower()
    if not email_key or "@" not in email_key:
        raise ValueError("Invalid email.")

    clearance_level, department, job_title = _infer_clearance_and_title(letter_text)
    full_name, preferred_name = _name_from_email(email_key)

    hris_path = _data_dir() / "mock_hris_db.json"
    hris = _read_json(hris_path, default={"meta": {}, "employees": []})
    hris.setdefault("employees", [])
    employees: list[dict[str, Any]] = hris["employees"]

    existing = next((e for e in employees if str(e.get("email", "")).lower() == email_key), None)
    if existing is not None:
        existing["clearance_level"] = clearance_level
        existing["department"] = department
        existing["job_title"] = job_title
        existing["full_name"] = existing.get("full_name") or full_name
        existing["preferred_name"] = existing.get("preferred_name") or preferred_name
        _write_json(hris_path, hris)
        return {"status": "updated", "employee_id": existing.get("employee_id"), "clearance_level": clearance_level}

    emp_id = _next_employee_id(employees)
    now_iso = datetime.now(timezone.utc).date().isoformat()

    new_employee = {
        "employee_id": emp_id,
        "full_name": full_name,
        "preferred_name": preferred_name,
        "email": email_key,
        "phone": "N/A",
        "job_title": job_title,
        "department": department,
        "manager_employee_id": None,
        "office_location": "Remote - TBD",
        "hire_date": now_iso,
        "employment_status": "Onboarding",
        "clearance_level": clearance_level,
        "salary_usd": 0,
        "salary_grade": "TBD",
        "pay_type": "Salary",
        "pto_hours_balance": 0.0,
        "pto_hours_accrual_per_pay_period": 0.0,
        "pto_policy": "TBD",
        "equipment": {"laptop": {"model": "TBD", "serial": None, "assigned": False}, "phone": {"model": "TBD", "serial": None, "assigned": False}, "accessories": []},
    }

    employees.append(new_employee)
    hris["meta"] = {
        **(hris.get("meta") or {}),
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "employee_count": len(employees),
    }
    _write_json(hris_path, hris)
    return {"status": "created", "employee_id": emp_id, "clearance_level": clearance_level}


def login_and_get_token(email: str, password: str) -> str:
    email_key = email.strip().lower()
    auth_path = _data_dir() / "auth_db.json"
    db = _read_json(auth_path, default={"users": {}})
    user = (db.get("users") or {}).get(email_key)
    if not user:
        raise ValueError("Invalid credentials.")
    if not check_password_hash(user.get("password_hash", ""), password):
        raise ValueError("Invalid credentials.")

    hris_path = _data_dir() / "mock_hris_db.json"
    hris = _read_json(hris_path, default={"meta": {}, "employees": []})
    employees: list[dict[str, Any]] = hris.get("employees") or []
    profile = next((e for e in employees if str(e.get("email", "")).lower() == email_key), None)
    if not profile:
        raise ValueError("No HRIS profile found for this user. Process an offer letter first.")

    payload = {
        "emp_id": profile.get("employee_id"),
        "name": profile.get("preferred_name") or profile.get("full_name"),
        "clearance_level": int(profile.get("clearance_level", 1)),
        "email": email_key,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=8)).timestamp()),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token


def validate_token(token: str) -> dict[str, Any]:
    if not token or not isinstance(token, str):
        raise ValueError("Missing token.")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise ValueError("Token expired.") from e
    except jwt.InvalidTokenError as e:
        raise ValueError("Invalid token.") from e

