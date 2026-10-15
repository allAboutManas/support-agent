from dotenv import load_dotenv
import os
from google import genai
from google.genai import types

# load secret from .env
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# define search db tool
def search_database(order_id: str):
    """Database search tool."""
    db = {
        "ORD-001": {"item": "Iphone 18 pro", "price": 180000, "status": "Delievered"},
        "ORD-002": {"item": "Gaming Monitor", "price": 80000, "status": "Damaged"}
    }

    return db.get(order_id, "Order not found")

# defiine mock refund tool
def issue_refund(order_id:str, amount:float):
    """Mock refund tool"""
    return f"Sucess: Your refund of amount ${amount} is issued for ${order_id}."

my_tools = [
    {
        "type" : "function",
        "function": {
            "name": "search_database",
            "description": "Looks up order details by order_id",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "issues refund for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "amount": {"type": "number"}
                    }
                },
                "required": ["order_id", "amount"]
            }
        }
    }
]


# gemini ReAct agent
def run_gemini_agent(user_prmopt: str): 
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_prmopt)])
    ]

    config = types.GenerateContentConfig(
        system_instruction="You are a e-commerce customer support agent",
        tools=my_tools,
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )

    while True:
        try:
            response = client.models.generate_content(
                model="gemini-3.7-flash",
                contents=contents,
                config=config
            )
        except Exception as e:
            print(f"API error: {e}")
            break

        if response.function_calls:
            function_call = response.function_calls[0]
            func_name = function_call.name
            args = function_call.args

            print(f"calling function {func_name}")

            tool_result = ""
            if func_name == "search_database":
                tool_result = search_database(**args)
            elif func_name == "issue_refund":
                amount = float(args.get("amount", 0))

                # Human in loop
                if amount > 50:
                    print(f"Human approval required")
                    approved = input("Approve the refund? (yes/no): ").strip().lower()

                    if approved != "yes":
                        tool_result = "Error: Refund rejected by admin"
                    else:
                        tool_result = issue_refund(**args)
            else: 
                tool_result = issue_refund(**args)


            # Append the tool response back into loop
            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", 
                                        parts=[types.Part.from_function_response(name=func_name,
                                                                                response={"result": tool_result})]))
        else:
            print(f"final response:", response.text)
            break

__name__ == "__main__"
run_gemini_agent("My monitor ORD-002 has arrived damaged, please refund")
                


