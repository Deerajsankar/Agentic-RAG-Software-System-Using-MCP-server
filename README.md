# Enterprise Agentic RAG for HR and IT Support

## 1) Project Overview and HR Domain Focus

This project delivers an **Agentic Retrieval-Augmented Generation (RAG) software system** built on an internal MCP server for enterprise HR and IT operations.

It functions as a **secure internal employee portal** where authenticated employees can:
- retrieve structured HR data (salary, PTO balances, reporting hierarchy, equipment, performance metadata),
- retrieve unstructured policy and onboarding context (including offer letters and policy knowledge chunks),
- and trigger autonomous internal actions such as IT ticket creation and password reset workflows (based on role clearance).

The system is purpose-built for **HR + IT domain automation**. Instead of an open-ended agent with internet tools, this design enforces a strict enterprise boundary: the LLM can only operate through approved MCP tools backed by local internal data and policy controls.

## 2) Core Architecture and Security

### Zero-Trust JWT Security
- Every sensitive MCP tool call requires a validated JWT token.
- The backend does not trust the AI: for every tool call, it re-verifies the JWT and re-derives the requester identity (from `emp_id`) and requester attributes (department/clearance) from token claims.
- Manager-to-Report (Chain of Command) Enforcement: for record-scoped "target" queries (e.g., salary, PTO, performance), the server performs a chain-of-command (recursive check pattern) authorizing access only when the requested employee's reporting relationship matches the caller: access is granted when `target_emp["manager_employee_id"] == requester_id`. This server-side check is applied per tool invocation so sensitive data is never released based on model assumptions.
- Departmental Overrides (God View): users in `People Ops`, `Human Resources`, or `Executive` are granted elevated visibility that bypasses individual manager checks, allowing them to query any employee record within the scope of each tool.
- Clearance thresholds remain in place for specific privileged actions (e.g., `update_clearance_level`, `trigger_password_reset`, `get_department_budget`), complementing the chain-of-command model with explicit operational guardrails.
- The unified portal uses an upgraded reasoning-agent system prompt to orchestrate the correct authorization inputs (not the authorization decision): Name (user input) -> `get_coworker_contact` (ID retrieval) -> data tools (`get_salary_details`, `get_pto_balance`, `search_performance_reviews`) using the retrieved `target_employee_id` as the required parameter.

### Internal Database RAG
- The agent retrieves real-time context from local, simulated enterprise sources, especially `data/mock_hris_db.json`.
- Structured internal records are used for operational responses (PTO, employee profile, team data, salary, equipment).
- Unstructured HR policy retrieval is supported via LanceDB-backed semantic search for grounded policy responses.

### Multimodal Verification for Onboarding
- During onboarding, the unified portal verifies employee documents by sending offer letter files (TXT/PDF-compatible via Gemini file upload) to Gemini for semantic validation.
- This creates a practical MFA-style onboarding step that combines identity checks with document intelligence.

### Explicit Schema Translation Layer
- The project includes a custom schema translation routine that converts FastMCP/Pydantic tool schemas into a clean Gemini-compatible function schema.
- Security-sensitive fields (like `token`) are intentionally stripped before tool declaration exposure to the model.
- This explicit translation prevents schema incompatibilities and enables reliable function calling with Google Gemini.

## 3) The 20 Internal HR and IT MCP Tools

All tools are extracted from `mcp_server/server.py` and exposed through FastMCP.

### Security and Authentication

1. **`get_my_profile`**  
   Validates JWT and returns the authenticated employee's full HRIS profile. This is the base identity tool for personalized HR and support interactions.

2. **`update_clearance_level`**  
   Allows only top-clearance users to modify another employee's clearance level. This governs the security posture of role-based tool access across the portal.

### HR Policy and Knowledge Retrieval (RAG)

3. **`search_hr_policies`**  
   Performs semantic search over internal HR policy chunks stored in LanceDB and returns top matches. This grounds agent responses in enterprise policy text.

### Employee Directory and Workforce Data

4. **`get_coworker_contact`**  
   Finds coworkers by name and returns directory-level contact details. Used for internal collaboration and routing.

5. **`get_team_roster`**  
   Returns direct reports for the authenticated manager based on reporting hierarchy. Supports manager workflows and people operations tasks.

6. **`get_company_holidays`**  
   Returns the official company-observed holiday schedule. Helps answer time-off planning and scheduling requests.

### Payroll, PTO, and Employee Self-Service

7. **`get_pto_balance`**  
   Returns PTO balance, accrual rate, and policy metadata with hierarchical zero-trust RBAC:
   - Self-service when `target_employee_id` is omitted or matches the caller.
   - Direct-report access when the target’s `manager_employee_id` equals the caller’s `employee_id`.
   - Departmental override (God View) for `People Ops`, `Human Resources`, and `Executive`.

8. **`submit_pto_request`**  
   Submits a PTO request by deducting approved hours from available balance. Enforces balance checks before approval.

9. **`update_preferred_name`**  
   Updates the employee's preferred name in the HRIS dataset. Supports profile maintenance and identity preferences.

10. **`get_salary_details`**  
    Returns salary information with the same manager-to-report + departmental override enforcement:
    - Self-service when `target_employee_id` is omitted or matches the caller.
    - Direct-report access when `target_emp["manager_employee_id"] == requester_id`.
    - `People Ops`/`Human Resources`/`Executive` override to view any employee record within tool scope.

11. **`get_direct_report_salary`**  
    Compatibility endpoint for direct-report salary queries:
    - Managers can view salary for their direct reports via `manager_employee_id`.
    - Non-managers require a sufficient `clearance_level` (in this demo, clearance-level gating is enforced by the backend).

### Talent Lifecycle and Performance

12. **`generate_offer_letter`**  
    Creates a mock offer letter file for a candidate with role and salary details. Supports HR hiring lifecycle simulations and onboarding artifacts.

13. **`search_performance_reviews`**  
    Retrieves performance review data with hierarchical zero-trust RBAC:
    - Self-service when `target_employee_id` is omitted or matches the caller.
    - Direct-report access when `target_emp["manager_employee_id"] == requester_id`.
    - `People Ops`/`Human Resources`/`Executive` override (God View) to retrieve reviews for any employee record within tool scope.

14. **`submit_performance_review`**  
    Lets a manager submit a structured review for a direct report with rating and commentary. Enforces manager-only authorization.

### IT Ticketing and End-User Support

15. **`log_it_ticket`**  
    Creates a new IT support ticket tied to the authenticated employee and stores it in the internal ticket database. Enables autonomous issue escalation from chat.

16. **`check_it_ticket_status`**  
    Looks up the status of an existing IT ticket by ticket ID. Supports employee self-service tracking of support progress.

17. **`request_new_equipment`**  
    Converts an equipment request into a standardized IT ticket workflow. Bridges HR employee records with IT provisioning operations.

18. **`trigger_password_reset`**  
    Triggers a password reset action for a target email, restricted to clearance-authorized users. Models controlled identity support operations.

19. **`get_equipment_assigned`**  
    Returns equipment currently assigned with hierarchical zero-trust RBAC:
    - Self-service when `target_employee_id` is omitted or matches the caller.
    - Direct-report access when the target’s `manager_employee_id` equals the caller’s `employee_id`.
    - Departmental override (God View) for `People Ops`, `Human Resources`, and `Executive`.

20. **`get_department_budget`**  
    Returns department budget information for authorized users with elevated clearance. Demonstrates finance-adjacent data controls in the same secure MCP layer.

## 4) Installation and Setup

### Prerequisites
- Python 3.10+ (recommended)
- A Google Gemini API key

### Clone and install

```bash
git clone <your-repository-url>
cd hr_agent_project
python -m venv .venv
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_google_gemini_api_key_here
```

## 5) Usage: The Unified Portal

Run the end-to-end enterprise flow:

```bash
python scripts/05_unified_portal.py
```

### Runtime flow
1. **Simulated OTP MFA**: validates employee identity with an OTP prompt.
2. **Password Creation**: securely creates account credentials and stores hashed password metadata.
3. **Document Verification**: uploads offer letter content and verifies identity-role alignment via Gemini multimodal processing.
4. **Secure Agentic Chat**: issues JWT, exposes MCP tools to Gemini, and enables autonomous HR/IT actions under clearance controls.

### Example Agentic Prompt

`What is my PTO balance and can you log an IT ticket for my broken laptop?`

The agent will retrieve real HR context from internal systems and can execute approved IT actions (ticket creation) through MCP tools, while respecting JWT and clearance restrictions.


## Technology Stack

- Python
- FastMCP (`mcp`)
- Google Gemini API (`google-genai`)
- JWT Security (`pyjwt`)
- Cryptography and password hashing (`werkzeug` + secure token workflows)
- LanceDB + sentence-transformers for policy retrieval

## Enterprise Positioning

This repository is a practical blueprint for secure internal copilots in enterprises: domain-scoped, tool-restricted, identity-aware, and operationally useful for cross-functional HR and IT support at employee-portal scale.
