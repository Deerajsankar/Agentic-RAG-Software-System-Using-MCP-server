from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
from mcp.server.fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

from .security import validate_token

mcp = FastMCP("HR_Secure_Server")


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _hris_path() -> Path:
    return _root_dir() / "data" / "mock_hris_db.json"


def _performance_path() -> Path:
    return _root_dir() / "data" / "mock_performance.json"


def _tickets_path() -> Path:
    return _root_dir() / "data" / "it_tickets.json"


def _load_hris() -> dict[str, Any]:
    path = _hris_path()
    if not path.exists():
        raise FileNotFoundError(f"Missing HRIS DB: {path}")
    return _read_json(path, default={"meta": {}, "employees": []})


def _save_hris(hris: dict[str, Any]) -> None:
    _write_json(_hris_path(), hris)


def _find_employee_by_id(hris: dict[str, Any], emp_id: str) -> dict[str, Any] | None:
    employees = hris.get("employees") or []
    return next((e for e in employees if e.get("employee_id") == emp_id), None)


def _find_employee_by_email(hris: dict[str, Any], email: str) -> dict[str, Any] | None:
    email_key = (email or "").strip().lower()
    employees = hris.get("employees") or []
    return next((e for e in employees if str(e.get("email", "")).strip().lower() == email_key), None)


def _infer_requesting_employee(hris: dict[str, Any], claims: dict[str, Any]) -> dict[str, Any]:
    emp_id = claims.get("emp_id")
    if not emp_id:
        raise ValueError("Token missing emp_id.")
    emp = _find_employee_by_id(hris, emp_id)
    if not emp:
        raise ValueError("Profile not found.")
    return emp


@mcp.tool()
def get_my_profile(token: str) -> dict[str, Any]:
    """
    Validate JWT and return the user's HRIS profile.
    """
    user_data = validate_token(token)
    emp_id = user_data.get("emp_id")
    hris = _load_hris()
    employees = hris.get("employees") or []
    profile = next((e for e in employees if e.get("employee_id") == emp_id), None)
    if not profile:
        raise ValueError("Profile not found.")
    return profile


_EMBED_MODEL: SentenceTransformer | None = None


def _embed_model() -> SentenceTransformer:
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL


@mcp.tool()
def search_hr_policies(query: str, token: str) -> list[dict[str, Any]]:
    """
    Validate JWT, embed query, and return top 3 policy chunks from LanceDB.
    """
    user_data = validate_token(token)
    if not query or not query.strip():
        raise ValueError("Query is required.")

    root = _root_dir()
    db_dir = root / "databases" / ".lancedb"
    if not db_dir.exists():
        raise FileNotFoundError(f"Missing LanceDB directory: {db_dir}. Run scripts/02_ingest_rag.py first.")

    db = lancedb.connect(str(db_dir))
    tbl = db.open_table("hr_policies")

    model = _embed_model()
    q_vec = model.encode([query], normalize_embeddings=True)
    q_vec = np.asarray(q_vec, dtype=np.float32)[0].tolist()

    results = tbl.search(q_vec).limit(3).to_list()
    # Keep response payload compact and RAG-friendly
    out: list[dict[str, Any]] = []
    for r in results:
        out.append(
            {
                "id": r.get("id"),
                "source_file": r.get("source_file"),
                "chunk_index": r.get("chunk_index"),
                "text": r.get("text"),
                "score": r.get("_distance") if "_distance" in r else r.get("_score"),
            }
        )
    return out


# -----------------------------
# Group 1: HR & Employee Data
# -----------------------------


@mcp.tool()
def get_pto_balance(token: str, target_employee_id: str = "") -> dict[str, Any]:
    """
    Retrieves the PTO balance. 
    If target_employee_id is provided, it attempts to fetch that employee's PTO (Requires HR or Manager clearance).
    If target_employee_id is left empty, it fetches the logged-in user's PTO.
    """
    user_data = validate_token(token)
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    
    # 1. Self-Service: If no target ID is requested, or they requested themselves
    if not target_employee_id or target_employee_id == me.get("employee_id"):
        return {
            "employee_id": me.get("employee_id"),
            "pto_hours_balance": float(me.get("pto_hours_balance", 0.0)),
            "pto_hours_accrual_per_pay_period": float(me.get("pto_hours_accrual_per_pay_period", 0.0)),
            "pto_policy": me.get("pto_policy"),
        }
        
    # 2. Find the target employee using your built-in helper function
    target_emp = _find_employee_by_id(hris, target_employee_id)
    
    if not target_emp:
        return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}
        
    # 3. RBAC SECURITY CHECK (The Bouncer)
    my_department = me.get("department", "")
    is_hr = my_department in ["People Ops", "Human Resources", "Executive"]
    is_manager = target_emp.get("manager_employee_id") == me.get("employee_id")
    
    if is_hr or is_manager:
        # Access Granted!
        return {
            "employee_id": target_emp.get("employee_id"),
            "pto_hours_balance": float(target_emp.get("pto_hours_balance", 0.0)),
            "pto_hours_accrual_per_pay_period": float(target_emp.get("pto_hours_accrual_per_pay_period", 0.0)),
            "pto_policy": target_emp.get("pto_policy"),
        }
    else:
        # Access Denied!
        return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}

@mcp.tool()
def get_coworker_contact(target_name: str, token: str) -> list[dict[str, Any]]:
    user_data = validate_token(token)
    _ = user_data
    if not target_name or not target_name.strip():
        raise ValueError("target_name is required.")
    needle = target_name.strip().lower()
    hris = _load_hris()
    employees = hris.get("employees") or []
    matches: list[dict[str, Any]] = []
    for e in employees:
        name = str(e.get("full_name") or "").strip()
        preferred = str(e.get("preferred_name") or "").strip()
        hay = f"{name} {preferred}".lower()
        if needle in hay:
            matches.append(
                {
                    "employee_id": e.get("employee_id"),
                    "full_name": e.get("full_name"),
                    "preferred_name": e.get("preferred_name"),
                    "email": e.get("email"),
                    "phone": e.get("phone"),
                }
            )
        if len(matches) >= 5:
            break
    return matches


@mcp.tool()
def get_team_roster(token: str) -> list[dict[str, Any]]:
    user_data = validate_token(token)
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    my_id = me.get("employee_id")
    employees = hris.get("employees") or []
    roster: list[dict[str, Any]] = []
    for e in employees:
        if e.get("manager_employee_id") == my_id:
            roster.append(
                {
                    "employee_id": e.get("employee_id"),
                    "full_name": e.get("full_name"),
                    "preferred_name": e.get("preferred_name"),
                    "job_title": e.get("job_title"),
                    "department": e.get("department"),
                    "email": e.get("email"),
                }
            )
    return roster


@mcp.tool()
def get_equipment_assigned(token: str, target_employee_id: str = "") -> dict[str, Any]:
    """
    Retrieves assigned equipment with RBAC enforcement using the same pattern as `get_pto_balance`.
    """
    user_data = validate_token(token)
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)

    allowed_departments = ["People Ops", "Human Resources", "Executive"]

    # 1. Self-Service
    if not target_employee_id or target_employee_id == me.get("employee_id"):
        return {"employee_id": me.get("employee_id"), "equipment": me.get("equipment") or {}}

    # 2. Find the target employee
    target_emp = _find_employee_by_id(hris, target_employee_id)
    if not target_emp:
        return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}

    # 3. RBAC SECURITY CHECK (The Bouncer)
    my_department = me.get("department", "")
    is_hr = my_department in allowed_departments
    is_manager = target_emp.get("manager_employee_id") == me.get("employee_id")

    if is_hr or is_manager:
        return {"employee_id": target_emp.get("employee_id"), "equipment": target_emp.get("equipment") or {}}

    return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}


@mcp.tool()
def get_company_holidays(token: str) -> list[dict[str, str]]:
    user_data = validate_token(token)
    _ = user_data
    return [
        {"date": "2026-01-01", "name": "New Year's Day"},
        {"date": "2026-01-26", "name": "Republic Day (Company Observed)"},
        {"date": "2026-05-01", "name": "Labor Day (Company Observed)"},
        {"date": "2026-07-04", "name": "Independence Day (Company Observed)"},
        {"date": "2026-11-26", "name": "Thanksgiving Day (Company Observed)"},
        {"date": "2026-12-25", "name": "Christmas Day"},
    ]


# -----------------------------
# Group 2: HR Actions
# -----------------------------


@mcp.tool()
def submit_pto_request(hours: float, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if hours is None or float(hours) <= 0:
        raise ValueError("hours must be > 0.")
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    current = float(me.get("pto_hours_balance", 0.0))
    hours_f = float(hours)
    if hours_f > current:
        raise ValueError("Insufficient PTO balance.")
    me["pto_hours_balance"] = round(current - hours_f, 2)
    _save_hris(hris)
    return {"status": "approved", "employee_id": me.get("employee_id"), "new_pto_hours_balance": me["pto_hours_balance"]}


@mcp.tool()
def update_preferred_name(new_name: str, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if not new_name or not new_name.strip():
        raise ValueError("new_name is required.")
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    me["preferred_name"] = new_name.strip()
    _save_hris(hris)
    return {"status": "ok", "employee_id": me.get("employee_id"), "preferred_name": me.get("preferred_name")}


@mcp.tool()
def generate_offer_letter(candidate_name: str, role: str, salary: int, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    _ = user_data
    if not candidate_name or not candidate_name.strip():
        raise ValueError("candidate_name is required.")
    if not role or not role.strip():
        raise ValueError("role is required.")
    if salary is None or int(salary) <= 0:
        raise ValueError("salary must be a positive integer.")

    raw_dir = _root_dir() / "data" / "raw_policies"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "_".join(candidate_name.strip().lower().split())
    filename = f"offer_letter_{safe_name}_{uuid.uuid4().hex[:8]}.txt"
    path = raw_dir / filename

    text = (
        f"# ExampleCorp Offer Letter (Mock)\n\n"
        f"**Candidate:** {candidate_name.strip()}\n\n"
        f"## Role and compensation\n"
        f"- **Role:** {role.strip()}\n"
        f"- **Base salary (USD):** {int(salary)}\n"
        f"- **Start date:** TBD (contingent on background verification)\n\n"
        f"## Compliance and conditions\n"
        f"1. This offer is contingent upon satisfactory verification, eligibility to work, and policy acknowledgements.\n"
        f"2. Compensation information is confidential and may be disclosed only to authorized stakeholders.\n"
        f"3. Work location must be approved in HRIS; cross-border work requires Mobility approval.\n\n"
        f"## Acceptance\n"
        f"Please reply to confirm acceptance and complete onboarding steps in the HR portal.\n"
    )

    path.write_text(text, encoding="utf-8")
    return {"status": "created", "path": str(path), "filename": filename}


# -----------------------------------------
# Group 3: Performance & Finance (Clearance)
# -----------------------------------------


@mcp.tool()
def get_salary_details(token: str, target_employee_id: str = "") -> dict[str, Any]:
    """
    Retrieves salary details with RBAC enforcement using the same pattern as `get_pto_balance`.
    """
    user_data = validate_token(token)
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)

    allowed_departments = ["People Ops", "Human Resources", "Executive"]

    # 1. Self-Service
    if not target_employee_id or target_employee_id == me.get("employee_id"):
        return {"employee_id": me.get("employee_id"), "salary_usd": int(me.get("salary_usd", 0))}

    # 2. Find the target employee
    target_emp = _find_employee_by_id(hris, target_employee_id)
    if not target_emp:
        return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}

    # 3. RBAC SECURITY CHECK (The Bouncer)
    my_department = me.get("department", "")
    is_hr = my_department in allowed_departments
    is_manager = target_emp.get("manager_employee_id") == me.get("employee_id")

    if is_hr or is_manager:
        return {"employee_id": target_emp.get("employee_id"), "salary_usd": int(target_emp.get("salary_usd", 0))}

    return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}


@mcp.tool()
def get_direct_report_salary(report_emp_id: str, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if not report_emp_id or not report_emp_id.strip():
        raise ValueError("report_emp_id is required.")

    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    target = _find_employee_by_id(hris, report_emp_id.strip())
    if not target:
        raise ValueError("Employee not found.")

    my_clearance = int(user_data.get("clearance_level", 1))
    is_manager = target.get("manager_employee_id") == me.get("employee_id")
    if not is_manager and my_clearance < 4:
        raise ValueError("Not authorized to view this salary.")

    return {"employee_id": target.get("employee_id"), "full_name": target.get("full_name"), "salary_usd": int(target.get("salary_usd", 0))}


@mcp.tool()
def search_performance_reviews(token: str, target_employee_id: str = "") -> dict[str, Any]:
    user_data = validate_token(token)
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)

    allowed_departments = ["People Ops", "Human Resources", "Executive"]

    # 1. Self-Service
    if not target_employee_id or target_employee_id == me.get("employee_id"):
        emp_id = me.get("employee_id")
    else:
        # 2. Find the target employee
        target_emp = _find_employee_by_id(hris, target_employee_id)
        if not target_emp:
            return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}

        # 3. RBAC SECURITY CHECK (The Bouncer)
        my_department = me.get("department", "")
        is_hr = my_department in allowed_departments
        is_manager = target_emp.get("manager_employee_id") == me.get("employee_id")

        if not (is_hr or is_manager):
            return {"error": "ACCESS DENIED: You do not have HR or Manager clearance for this employee."}

        emp_id = target_emp.get("employee_id")

    perf_path = _performance_path()
    if not perf_path.exists():
        raise FileNotFoundError(f"Missing performance DB: {perf_path}")
    perf = _read_json(perf_path, default={})
    reviews = (perf.get("performance_reviews") or {})
    my_review = reviews.get(emp_id)
    if not my_review:
        return {"employee_id": emp_id, "review": None}
    return {
        "employee_id": emp_id,
        "cycle": my_review.get("cycle"),
        "overall_rating_numeric": my_review.get("overall_rating_numeric"),
        "overall_rating_label": my_review.get("overall_rating_label"),
        "competencies": my_review.get("competencies"),
        "goals": my_review.get("goals"),
    }


@mcp.tool()
def submit_performance_review(report_emp_id: str, review_text: str, rating: int, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if not report_emp_id or not report_emp_id.strip():
        raise ValueError("report_emp_id is required.")
    if not review_text or not review_text.strip():
        raise ValueError("review_text is required.")
    rating_i = int(rating)
    if rating_i < 1 or rating_i > 5:
        raise ValueError("rating must be between 1 and 5.")

    # Manager-only check
    hris = _load_hris()
    me = _infer_requesting_employee(hris, user_data)
    target = _find_employee_by_id(hris, report_emp_id.strip())
    if not target:
        raise ValueError("Employee not found.")
    if target.get("manager_employee_id") != me.get("employee_id"):
        raise ValueError("Not authorized. Only the employee's manager may submit a review.")

    perf_path = _performance_path()
    if not perf_path.exists():
        raise FileNotFoundError(f"Missing performance DB: {perf_path}")
    perf = _read_json(perf_path, default={"meta": {}, "performance_reviews": {}})
    perf.setdefault("performance_reviews", {})

    emp_key = target.get("employee_id")
    if emp_key not in perf["performance_reviews"]:
        perf["performance_reviews"][emp_key] = {"employee_id": emp_key, "cycle": perf.get("meta", {}).get("cycle"), "submitted_reviews": []}

    perf["performance_reviews"][emp_key].setdefault("submitted_reviews", [])
    perf["performance_reviews"][emp_key]["submitted_reviews"].append(
        {
            "submitted_at": "2026-03-17T00:00:00Z",
            "manager_emp_id": me.get("employee_id"),
            "review_text": review_text.strip(),
            "rating": rating_i,
        }
    )

    _write_json(perf_path, perf)
    return {"status": "ok", "report_emp_id": emp_key, "appended": True}


@mcp.tool()
def update_clearance_level(target_emp_id: str, new_level: int, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if int(user_data.get("clearance_level", 1)) != 5:
        raise ValueError("Not authorized. Requires clearance level 5.")
    if not target_emp_id or not target_emp_id.strip():
        raise ValueError("target_emp_id is required.")
    lvl = int(new_level)
    if lvl < 1 or lvl > 5:
        raise ValueError("new_level must be between 1 and 5.")

    hris = _load_hris()
    target = _find_employee_by_id(hris, target_emp_id.strip())
    if not target:
        raise ValueError("Employee not found.")
    target["clearance_level"] = lvl
    _save_hris(hris)
    return {"status": "ok", "employee_id": target.get("employee_id"), "clearance_level": target.get("clearance_level")}


# -----------------------------
# Group 4: IT Support
# -----------------------------


def _ensure_it_tickets_file() -> None:
    path = _tickets_path()
    if not path.exists():
        _write_json(path, [])


@mcp.tool()
def log_it_ticket(issue_desc: str, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if not issue_desc or not issue_desc.strip():
        raise ValueError("issue_desc is required.")

    _ensure_it_tickets_file()
    path = _tickets_path()
    tickets = _read_json(path, default=[])
    if not isinstance(tickets, list):
        tickets = []

    ticket_id = f"TCKT-{uuid.uuid4().hex[:8].upper()}"
    ticket = {
        "ticket_id": ticket_id,
        "emp_id": user_data.get("emp_id"),
        "status": "Open",
        "description": issue_desc.strip(),
        "priority": random.choice(["P3", "P2", "P4"]),
    }
    tickets.append(ticket)
    _write_json(path, tickets)
    return {"status": "ok", "ticket": ticket}


@mcp.tool()
def check_it_ticket_status(ticket_id: str, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    _ = user_data
    if not ticket_id or not ticket_id.strip():
        raise ValueError("ticket_id is required.")

    _ensure_it_tickets_file()
    tickets = _read_json(_tickets_path(), default=[])
    if not isinstance(tickets, list):
        tickets = []
    t = next((x for x in tickets if str(x.get("ticket_id", "")).strip() == ticket_id.strip()), None)
    if not t:
        raise ValueError("Ticket not found.")
    return {"ticket_id": t.get("ticket_id"), "status": t.get("status")}


@mcp.tool()
def request_new_equipment(item_type: str, token: str) -> dict[str, Any]:
    user_data = validate_token(token)
    if not item_type or not item_type.strip():
        raise ValueError("item_type is required.")
    issue = f"Hardware request: {item_type.strip()} — please provision/approve per equipment policy."
    # Reuse ticket logic
    return log_it_ticket(issue_desc=issue, token=token)


@mcp.tool()
def trigger_password_reset(target_email: str, token: str) -> str:
    user_data = validate_token(token)
    if int(user_data.get("clearance_level", 1)) < 3:
        raise ValueError("Not authorized. Requires clearance level 3+.")
    if not target_email or not target_email.strip():
        raise ValueError("target_email is required.")
    email_key = target_email.strip().lower()
    return f"Password reset link sent to {email_key}"


@mcp.tool()
def get_department_budget(department: str, token: str) -> str:
    user_data = validate_token(token)
    if int(user_data.get("clearance_level", 1)) < 4:
        raise ValueError("Not authorized. Requires clearance level 4+.")
    if not department or not department.strip():
        raise ValueError("department is required.")
    dept = department.strip()
    # Hardcoded placeholder budget strings
    budgets = {
        "Engineering": "$12,500,000 (FY2026 OpEx + CapEx)",
        "People Ops": "$2,100,000 (FY2026)",
        "Sales": "$8,750,000 (FY2026)",
        "IT": "$1,600,000 (FY2026)",
        "Executive": "$950,000 (FY2026 Discretionary)",
    }
    return budgets.get(dept, f"$500,000 (FY2026 baseline budget for {dept})")

