from google.genai import types

from app.agent.policies import requires_refund_approval
from app.agent.prompts import SYSTEM_INSTRUCTION, user_prompt
from app.config import GEMINI_MODEL, client
from app.tools.registry import tools_for_user
from app.tools.refunds import issue_refund


MAX_LLM_ITERATIONS = 3
MAX_TOOL_ITERATIONS = 3
ITERATION_LIMIT_REPLY = (
    "This request reached the processing limit before it could be completed. "
    "Please try again or contact support."
)


def _iteration_limit_result(contents: list):
    contents.append(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text=ITERATION_LIMIT_REPLY)],
        )
    )
    return {"reply": ITERATION_LIMIT_REPLY, "pending_approval": None}


def _continue_agent(contents: list, user_id: int):
    tool_functions = tools_for_user(user_id)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tool_functions,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    llm_iterations = 0
    tool_iterations = 0
    while llm_iterations < MAX_LLM_ITERATIONS:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        llm_iterations += 1

        if not response.function_calls:
            contents.append(response.candidates[0].content)
            return {"reply": response.text or "", "pending_approval": None}

        if tool_iterations >= MAX_TOOL_ITERATIONS:
            return _iteration_limit_result(contents)

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
            tool_result = issue_refund(**arguments, user_id=user_id)
        else:
            tool = next(
                (tool for tool in tool_functions if tool.__name__ == function_name),
                None,
            )
            if tool is None:
                tool_result = f"Error: Unknown function {function_name}"
            else:
                tool_result = tool(**arguments)
        tool_iterations += 1

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

    return _iteration_limit_result(contents)


def run_gemini_agent(user_text: str, contents: list, user_id: int):
    contents.append(user_prompt(user_text))
    return _continue_agent(contents, user_id)


def resolve_refund(
    contents: list, order_id: str, amount: float, approved: bool, user_id: int
):
    if approved:
        result = issue_refund(order_id=order_id, amount=amount, user_id=user_id)
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
    return _continue_agent(contents, user_id)