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

my_tools = [search_database, issue_refund]


# 1. Pass `contents` (chat history) into the function  # <-- NEW
def run_gemini_agent(user_prompt: str, contents: list): 
    # 2. Append the new user message to existing history instead of overwriting it  # <-- NEW
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
    )

    config = types.GenerateContentConfig(
        system_instruction="You are an e-commerce customer support agent.",
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

            # Append the model's function call request and the tool result into history
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="user", 
                    parts=[types.Part.from_function_response(
                        name=func_name,
                        response={"result": tool_result}
                    )]
                )
            )
        else:
            # 3. Save the model's final text answer into history before breaking!  # <-- NEW
            contents.append(response.candidates[0].content)
            print(f"\nAgent: {response.text}\n")
            break


# 4. Outer chat loop that keeps `chat_history` alive across turns  # <-- NEW
if __name__ == "__main__":
    chat_history = []
    print("Support Agent Ready! (Type 'exit' to quit)\n")
    
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["exit", "quit"]:
            break
        if not user_input:
            continue
            
        run_gemini_agent(user_input, chat_history)