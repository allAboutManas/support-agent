from google.genai import types

from app.agent.policies import requires_refund_approval
from app.agent.prompts import SYSTEM_INSTRUCTION, user_prompt
from app.config import GEMINI_MODEL, client
from app.tools.registry import TOOL_FUNCTIONS
from app.tools.refunds import issue_refund


def _continue_agent(contents: list):
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=TOOL_FUNCTIONS,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    while True:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )

        if not response.function_calls:
            contents.append(response.candidates[0].content)
            return {"reply": response.text or "", "pending_approval": None}

        function_call = response.function_calls[0]
        function_name = function_call.name
        arguments = function_call.args

        if function_name == "issue_refund":
            amount = float(arguments.get("amount", 0))
            if requires_refund_approval(amount):
                contents.append(response.candidates[0].content)
                return {
                    "reply": "Your refund request was sent to an admin for review.",
                    "pending_approval": {
                        "order_id": arguments["order_id"],
                        "amount": amount,
                    },
                }
            tool_result = issue_refund(**arguments)
        else:
            tool = next(
                (tool for tool in TOOL_FUNCTIONS if tool.__name__ == function_name),
                None,
            )
            if tool is None:
                tool_result = f"Error: Unknown function {function_name}"
            else:
                tool_result = tool(**arguments)

        contents.append(response.candidates[0].content)
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_function_response(
                    name=function_name,
                    response={"result": tool_result},
                )],
            )
        )


def run_gemini_agent(user_text: str, contents: list):
    contents.append(user_prompt(user_text))
    return _continue_agent(contents)


def resolve_refund(contents: list, order_id: str, amount: float, approved: bool):
    if approved:
        result = issue_refund(order_id=order_id, amount=amount)
    else:
        result = "Error: Refund rejected by admin"

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_function_response(
                name="issue_refund",
                response={"result": result},
            )],
        )
    )
    return _continue_agent(contents)