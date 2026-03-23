from dotenv import load_dotenv

load_dotenv()

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp_server.security import login_and_get_token


def build_gemini_schema(original_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Explicitly builds a clean, token-free Gemini schema from FastMCP parameters.
    Bypasses recursive Pydantic artifacts completely.
    """
    gemini_schema = {"type": "OBJECT", "properties": {}}

    if "properties" in original_schema:
        for param_name, param_details in original_schema.get("properties", {}).items():
            if param_name == "token":
                continue  # Silently strip the security token!

            # Extract type and ensure it is uppercase for Gemini (e.g., 'STRING', 'INTEGER')
            param_type = str(param_details.get("type", "string")).upper()

            gemini_schema["properties"][param_name] = {
                "type": param_type,
                "description": param_details.get("description", "")
            }

    if "required" in original_schema:
        reqs = [r for r in original_schema["required"] if r != "token"]
        if reqs:
            gemini_schema["required"] = reqs

    return gemini_schema


def _extract_tools_from_fastmcp(mcp_obj: Any) -> tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]:
    """
    Extract tool schemas and callables from FastMCP's internal ToolManager registry.
    """
    tool_manager = getattr(mcp_obj, "_tool_manager", None)
    tools_dict = getattr(tool_manager, "_tools", None) if tool_manager is not None else None
    if not isinstance(tools_dict, dict) or not tools_dict:
        return [], {}

    tools: list[dict[str, Any]] = []
    tool_name_to_function: dict[str, Callable[..., Any]] = {}

    for name in sorted(tools_dict.keys()):
        tool = tools_dict[name]
        fn = getattr(tool, "fn", None)
        params = getattr(tool, "parameters", None)
        desc = getattr(tool, "description", "") or ""
        
        if not callable(fn):
            continue
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}

        # Use our bulletproof explicit schema builder
        safe_schema = build_gemini_schema(params)
        
        tools.append(
            {
                "name": getattr(tool, "name", name),
                "description": desc.strip() or f"Call `{name}`",
                "parameters": safe_schema,
            }
        )
        tool_name_to_function[name] = fn

    return tools, tool_name_to_function


def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Missing GEMINI_API_KEY. Add it to your environment or `.env`.")
        raise SystemExit(1)

    client = genai.Client(api_key=api_key)

    print("Enterprise HR Agent Terminal Chat")
    print("--------------------------------")

    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    try:
        jwt_token = login_and_get_token(email=email, password=password)
    except Exception as e:
        print(f"Login failed: {e}")
        raise SystemExit(1)

    from mcp_server import server as mcp_server_module

    tools, tool_name_to_function = _extract_tools_from_fastmcp(mcp_server_module.mcp)

    if len(tools) != 20:
        raise RuntimeError(f"Expected 20 tools, found {len(tools)}.")

    system_prompt = (
        "You are an Enterprise HR and IT Support Agent. You have access to secure internal tools. "
        "If a user reports an IT issue, offer 1 or 2 instant troubleshooting steps first before "
        "offering to log a ticket. Be professional, concise, and helpful."
    )

    function_declarations: list[types.FunctionDeclaration] = []
    for t in tools:
        function_declarations.append(
            types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters"),  # Now correctly uses the new SDK format
            )
        )
    tool_obj = types.Tool(function_declarations=function_declarations)

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tool_obj],
        ),
    )

    print("\nType your message. Use `/exit` to quit.\n")

    while True:
        user_text = input("> ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"/exit", "exit", "quit"}:
            break

        response = chat.send_message(user_text)

        # Handle Tool Calls natively using the modern SDK structure
        while getattr(response, "function_calls", None):
            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args or {})  # Correct extraction for google-genai
                fn_args["token"] = jwt_token     # Inject the secure JWT!

                fn = tool_name_to_function.get(fn_name)
                if fn is None:
                    function_response = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        result = fn(**fn_args)
                        function_response = {"result": result}
                    except Exception as e:
                        function_response = {"error": f"{type(e).__name__}: {e}"}

                function_response_part = types.Part.from_function_response(
                    name=fn_name,
                    response=function_response,
                )
                
                response = chat.send_message(function_response_part)

        if getattr(response, "text", None):
            print((response.text or "").strip() + "\n")


if __name__ == "__main__":
    main()