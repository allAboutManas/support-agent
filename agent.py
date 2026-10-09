from dotenv import load_dotenv
import os
import json
from openai import OpenAI
from gemini import Gemini
from google import genai

# load secret from .env
load_dotenv()
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# LLM integration
response = client_gemini.models.generate_content(model="gemini-3.8-flash", contents="Explain API in simple terms")
print(response.text)

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

tools = [
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
                "reuired": ["order_id", "amount"]
            }
        }
    }
]