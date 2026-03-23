from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from faker import Faker


@dataclass(frozen=True)
class Employee:
    employee_id: str
    full_name: str
    preferred_name: str | None
    email: str
    phone: str
    job_title: str
    department: str
    manager_employee_id: str | None
    office_location: str
    hire_date: str  # ISO date
    employment_status: str  # e.g. Active
    clearance_level: int  # 1-5

    # Structured HRIS-ish fields
    salary_usd: int
    salary_grade: str
    pay_type: str  # Salary / Hourly

    pto_hours_balance: float
    pto_hours_accrual_per_pay_period: float
    pto_policy: str

    equipment: dict[str, Any]


def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _iso(d: date) -> str:
    return d.isoformat()


def _stable_seed() -> int:
    # Allow override for reproducibility in CI; otherwise deterministic default.
    env = os.getenv("MOCK_DATA_SEED")
    if env is not None and env.strip():
        try:
            return int(env.strip())
        except ValueError:
            pass
    return 1337


def _make_email(first: str, last: str, domain: str = "examplecorp.com") -> str:
    local = f"{first}.{last}".lower().replace(" ", "").replace("'", "")
    return f"{local}@{domain}"


def generate_employees(fake: Faker, rng: random.Random, n: int = 50) -> list[Employee]:
    departments = [
        "Executive",
        "People Ops",
        "Engineering",
        "Product",
        "Sales",
        "Marketing",
        "Finance",
        "Legal",
        "IT",
        "Customer Success",
    ]
    office_locations = ["Bengaluru", "Hyderabad", "Pune", "Remote - India", "Remote - US", "London"]
    pay_types = ["Salary", "Hourly"]
    salary_grades = ["A1", "A2", "B1", "B2", "C1", "C2", "D1"]
    job_titles = [
        "CEO",
        "Chief People Officer",
        "VP Engineering",
        "Engineering Manager",
        "Senior Software Engineer",
        "Software Engineer",
        "Product Manager",
        "Sales Manager",
        "Account Executive",
        "Marketing Manager",
        "Financial Analyst",
        "HR Business Partner",
        "IT Support Specialist",
        "Customer Success Manager",
        "Legal Counsel",
    ]

    # IDs
    employee_ids = [f"E{1000 + i}" for i in range(n)]

    # We'll assign managers later; build base people first.
    people: list[dict[str, Any]] = []
    for i in range(n):
        name = fake.name()
        parts = name.replace(".", "").split()
        first = parts[0]
        last = parts[-1]
        dept = rng.choice(departments)
        title = rng.choice(job_titles)
        loc = rng.choice(office_locations)

        # Hire date between 2014 and today-ish
        hire = fake.date_between(start_date="-12y", end_date="-10d")

        pay_type = rng.choice(pay_types)
        grade = rng.choice(salary_grades)
        base_salary = rng.randint(45_000, 280_000)
        if title == "CEO":
            base_salary = rng.randint(350_000, 750_000)
            grade = "D1"
            pay_type = "Salary"

        pto_policy = rng.choice(["Standard", "Enhanced", "Executive"])
        if dept == "Executive":
            pto_policy = "Executive"
        pto_balance = round(rng.uniform(10.0, 160.0), 1)
        accrual = 6.15 if pto_policy == "Standard" else 7.7 if pto_policy == "Enhanced" else 10.0

        equipment = {
            "laptop": rng.choice(
                [
                    {"model": "Dell Latitude 7440", "serial": fake.bothify("DL-########"), "assigned": True},
                    {"model": "Apple MacBook Pro 14", "serial": fake.bothify("MBP-########"), "assigned": True},
                    {"model": "Lenovo ThinkPad X1 Carbon", "serial": fake.bothify("TP-########"), "assigned": True},
                ]
            ),
            "phone": rng.choice(
                [
                    {"model": "iPhone 15", "serial": fake.bothify("IP-########"), "assigned": True},
                    {"model": "Pixel 9", "serial": fake.bothify("PX-########"), "assigned": True},
                    {"model": "None", "serial": None, "assigned": False},
                ]
            ),
            "accessories": rng.sample(
                ["Dock", "Headset", "External Monitor", "Security Key", "Ergonomic Keyboard", "Mouse"],
                k=rng.randint(1, 3),
            ),
        }

        clearance = rng.choices([1, 2, 3, 4], weights=[55, 25, 15, 5], k=1)[0]
        if dept == "Executive":
            clearance = rng.choices([3, 4], weights=[70, 30], k=1)[0]

        people.append(
            {
                "employee_id": employee_ids[i],
                "full_name": name,
                "preferred_name": None,
                "first": first,
                "last": last,
                "email": _make_email(first, last),
                "phone": fake.phone_number(),
                "job_title": title,
                "department": dept,
                "office_location": loc,
                "hire_date": _iso(hire),
                "employment_status": "Active",
                "clearance_level": int(clearance),
                "salary_usd": int(base_salary),
                "salary_grade": grade,
                "pay_type": pay_type,
                "pto_hours_balance": float(pto_balance),
                "pto_hours_accrual_per_pay_period": float(accrual),
                "pto_policy": pto_policy,
                "equipment": equipment,
            }
        )

    # Force-add the two required test profiles by overriding two slots.
    # CEO
    ceo_idx = 0
    people[ceo_idx].update(
        {
            "full_name": "Aarav Kapoor",
            "preferred_name": "Aarav",
            "first": "Aarav",
            "last": "Kapoor",
            "email": "ceo@examplecorp.com",
            "job_title": "CEO",
            "department": "Executive",
            "clearance_level": 5,
            "salary_usd": 650_000,
            "salary_grade": "D1",
            "pay_type": "Salary",
            "pto_policy": "Executive",
            "pto_hours_accrual_per_pay_period": 10.0,
        }
    )
    # Deeraj
    deeraj_idx = 1
    people[deeraj_idx].update(
        {
            "full_name": "Deeraj",
            "preferred_name": "Deeraj",
            "first": "Deeraj",
            "last": "",
            "email": "deeraj@examplecorp.com",
            "job_title": "HR Business Partner",
            "department": "People Ops",
            "clearance_level": 1,
            "salary_usd": 95_000,
            "salary_grade": "B1",
            "pay_type": "Salary",
            "pto_policy": "Standard",
            "pto_hours_accrual_per_pay_period": 6.15,
        }
    )

    # Manager assignment: pick a small set of managers, ensure CEO has no manager.
    manager_pool = [people[ceo_idx]["employee_id"]]
    # Pick some additional managers from across the org (excluding Deeraj to keep clearance low).
    eligible_manager_ids = [p["employee_id"] for i, p in enumerate(people) if i not in {ceo_idx, deeraj_idx}]
    manager_pool.extend(rng.sample(eligible_manager_ids, k=min(6, len(eligible_manager_ids))))

    for i, p in enumerate(people):
        if i == ceo_idx:
            p["manager_employee_id"] = None
        else:
            # Give executives and people ops a higher chance to report to CEO.
            if p["department"] in {"Executive", "People Ops"} and rng.random() < 0.6:
                p["manager_employee_id"] = people[ceo_idx]["employee_id"]
            else:
                p["manager_employee_id"] = rng.choice(manager_pool)
                if p["manager_employee_id"] == p["employee_id"]:
                    p["manager_employee_id"] = people[ceo_idx]["employee_id"]

    employees: list[Employee] = []
    for p in people:
        employees.append(
            Employee(
                employee_id=p["employee_id"],
                full_name=p["full_name"],
                preferred_name=p["preferred_name"],
                email=p["email"],
                phone=p["phone"],
                job_title=p["job_title"],
                department=p["department"],
                manager_employee_id=p["manager_employee_id"],
                office_location=p["office_location"],
                hire_date=p["hire_date"],
                employment_status=p["employment_status"],
                clearance_level=int(p["clearance_level"]),
                salary_usd=int(p["salary_usd"]),
                salary_grade=p["salary_grade"],
                pay_type=p["pay_type"],
                pto_hours_balance=float(p["pto_hours_balance"]),
                pto_hours_accrual_per_pay_period=float(p["pto_hours_accrual_per_pay_period"]),
                pto_policy=p["pto_policy"],
                equipment=p["equipment"],
            )
        )
    return employees


def generate_performance(fake: Faker, rng: random.Random, employees: list[Employee]) -> dict[str, Any]:
    cycle = "2026-H1"
    competencies = ["Impact", "Execution", "Collaboration", "Leadership", "Communication", "Growth Mindset"]
    rating_scale = ["Needs Improvement", "Meets", "Exceeds", "Outstanding"]

    perf_by_employee: dict[str, Any] = {}
    for e in employees:
        # Keep CEO and Deeraj present but realistic.
        base_rating = rng.choices([1, 2, 3], weights=[10, 65, 25], k=1)[0]
        if e.department == "Executive":
            base_rating = rng.choices([2, 3], weights=[40, 60], k=1)[0]
        if e.full_name == "Deeraj":
            base_rating = 2

        competency_scores: dict[str, int] = {}
        for c in competencies:
            # Create some variance around base
            competency_scores[c] = max(1, min(4, base_rating + rng.choice([-1, 0, 0, 0, 1])))

        overall_numeric = round(sum(competency_scores.values()) / len(competency_scores), 2)
        overall_label = rating_scale[max(0, min(3, int(round(overall_numeric)) - 1))]

        goals = [
            {"goal": fake.sentence(nb_words=6).rstrip("."), "status": rng.choice(["On Track", "At Risk", "Completed"])},
            {"goal": fake.sentence(nb_words=7).rstrip("."), "status": rng.choice(["On Track", "Completed"])},
        ]

        perf_by_employee[e.employee_id] = {
            "cycle": cycle,
            "employee_id": e.employee_id,
            "overall_rating_numeric": overall_numeric,
            "overall_rating_label": overall_label,
            "competencies": competency_scores,
            "goals": goals,
            "manager_summary": fake.paragraph(nb_sentences=3),
            "employee_self_reflection": fake.paragraph(nb_sentences=3),
            "promotion_recommendation": rng.choices(
                ["No", "Consider", "Yes"], weights=[70, 22, 8], k=1
            )[0],
        }

    return {
        "meta": {"cycle": cycle, "generated_at": fake.iso8601(), "record_count": len(employees)},
        "performance_reviews": perf_by_employee,
    }


def generate_policies(fake: Faker) -> dict[str, str]:
    # 5 unstructured policy documents
    today = date.today().isoformat()
    org = "ExampleCorp"

    def header(title: str) -> str:
        return f"{org} — {title}\nEffective: {today}\n\n"

    global_handbook = (
        header("Global Employee Handbook (Mock)")
        + "Welcome to ExampleCorp. This handbook is a mock, unstructured policy document used for testing HR agent tooling.\n\n"
        + "Core principles\n"
        + "- We treat people with respect and assume positive intent.\n"
        + "- We protect confidential information and access it only as needed.\n"
        + "- We comply with local labor laws and company policies.\n\n"
        + "Employment and conduct\n"
        + "ExampleCorp maintains standards of professional conduct, anti-harassment expectations, and reporting channels.\n"
        + "If you have concerns, contact People Ops or use the ethics hotline.\n\n"
        + "Time off\n"
        + "Time off is tracked in the HRIS. Eligibility, accrual, and carryover rules vary by region and policy tier.\n\n"
        + "Acknowledgement\n"
        + "By continuing employment, you acknowledge responsibility to read and follow policies as updated.\n"
    )

    benefits = (
        header("Benefits Overview (Mock)")
        + "This document provides an unstructured overview of common benefit programs. Eligibility depends on region and employment status.\n\n"
        + "Common benefits may include:\n"
        + "- Health coverage (medical, dental, vision)\n"
        + "- Retirement plan / provident fund contributions\n"
        + "- Life and disability insurance\n"
        + "- Wellness reimbursement\n"
        + "- Learning & development stipend\n\n"
        + "Enrollment windows\n"
        + "New hires typically have a limited period to enroll. Changes may be allowed during annual enrollment or qualifying events.\n\n"
        + "Contact\n"
        + f"For questions, contact People Ops: {fake.email()}.\n"
    )

    it_security = (
        header("IT Security Policy (Mock)")
        + "Purpose: reduce risk to company systems and data.\n\n"
        + "Key requirements\n"
        + "- Use company-managed devices for company data when possible.\n"
        + "- Enable disk encryption and strong authentication (MFA where supported).\n"
        + "- Do not share passwords or tokens.\n"
        + "- Report suspected phishing immediately.\n\n"
        + "Access and clearance\n"
        + "Access is granted on least-privilege and may depend on role and clearance level.\n"
        + "HR and executive data is highly restricted.\n\n"
        + "Incident response\n"
        + "If a device is lost or stolen, report within 1 hour to IT and your manager.\n"
    )

    visas = (
        header("Immigration & Visas Guidance (Mock)")
        + "This guidance is for planning purposes and is not legal advice.\n\n"
        + "General approach\n"
        + "- Employees requiring work authorization must coordinate with People Ops.\n"
        + "- Start visa processes early; timelines vary.\n"
        + "- Provide accurate documentation.\n\n"
        + "Travel\n"
        + "International travel may require additional approvals depending on destination, role, and project sensitivity.\n"
        + "Check with People Ops before booking.\n"
    )

    manager_playbook = (
        header("Manager Playbook (Mock)")
        + "Managers are accountable for team health, performance, and compliance.\n\n"
        + "Key responsibilities\n"
        + "- Set clear expectations and measurable goals.\n"
        + "- Run regular 1:1s and provide timely feedback.\n"
        + "- Escalate concerns early (performance, conduct, safety).\n\n"
        + "Compensation & confidentiality\n"
        + "Compensation details are confidential. Share only with authorized stakeholders.\n\n"
        + "Performance cycles\n"
        + "Prepare evidence-based summaries, focusing on outcomes and behaviors.\n"
    )

    return {
        "global_handbook.txt": global_handbook,
        "benefits.txt": benefits,
        "it_security.txt": it_security,
        "visas.txt": visas,
        "manager_playbook.txt": manager_playbook,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    raw_policies_dir = data_dir / "raw_policies"
    _ensure_dirs(root / "scripts", data_dir, raw_policies_dir)

    seed = _stable_seed()
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)

    employees = generate_employees(fake, rng, n=50)

    # Structured "HRIS DB" snapshot
    hris_db = {
        "meta": {"generated_at": fake.iso8601(), "seed": seed, "employee_count": len(employees)},
        "employees": [asdict(e) for e in employees],
    }
    _write_json(data_dir / "mock_hris_db.json", hris_db)

    # Structured performance dataset
    performance = generate_performance(fake, rng, employees)
    _write_json(data_dir / "mock_performance.json", performance)

    # Unstructured policies
    policies = generate_policies(fake)
    for filename, text in policies.items():
        _write_text(raw_policies_dir / filename, text)

    print("Mock data generated:")
    print(f"- {data_dir / 'mock_hris_db.json'}")
    print(f"- {data_dir / 'mock_performance.json'}")
    print(f"- {raw_policies_dir} ({len(policies)} files)")


if __name__ == "__main__":
    main()
