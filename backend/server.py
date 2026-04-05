import json
import os
import re
import pandas as pd
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY in environment or .env")

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------
# 1. LOAD YOUR DATASET INTO THE BACKEND
# ---------------------------------------------------------
try:
    # Adjust this path if your server.py is not in your project root
    yoi_df = pd.read_csv("../data/processed/yoi/yoi_components.csv")
except FileNotFoundError:
    print("Warning: Could not find yoi_components.csv. Data tools will fail.")
    yoi_df = pd.DataFrame()


# ---------------------------------------------------------
# 2. DEFINE THE PYTHON TOOLS FOR GEMINI TO USE
# ---------------------------------------------------------
def get_highest_lowest_tract(metric: str) -> str:
    """Gets the census tract with the highest and lowest score for a specific metric.
    
    Args:
        metric: The exact column name to check (e.g., 'yoi_custom_0_100', 'education_score', 'health_score', 'housing_score').
    """
    if yoi_df.empty or metric not in yoi_df.columns:
        return f"Error: Metric '{metric}' not found. Available metrics include yoi_custom_0_100, education_score, health_score, etc."
    
    # Drop missing values and sort
    sorted_df = yoi_df.dropna(subset=[metric]).sort_values(by=metric, ascending=False)
    if sorted_df.empty:
        return "No data available."
        
    highest = sorted_df.iloc[0]
    lowest = sorted_df.iloc[-1]
    
    return f"Highest: Tract {highest.get('tract_geoid', 'Unknown')} with score {highest[metric]}. Lowest: Tract {lowest.get('tract_geoid', 'Unknown')} with score {lowest[metric]}."

def count_tracts_by_condition(metric: str, operator_str: str, value: float) -> str:
    """Counts how many census tracts meet a specific mathematical condition.
    
    Args:
        metric: The exact column name (e.g., 'yoi_custom_0_100', 'housing_score').
        operator_str: The comparison operator ('<', '>', '<=', '>=', '==').
        value: The numeric value to compare against.
    """
    if yoi_df.empty or metric not in yoi_df.columns:
        return f"Error: Metric '{metric}' not found."
        
    try:
        # Pandas 'query' makes searching data incredibly easy!
        query_str = f"{metric} {operator_str} {value}"
        count = len(yoi_df.query(query_str))
        return f"Result: There are {count} census tracts where {query_str}."
    except Exception as e:
        return f"Error executing query: {str(e)}"


# ---------------------------------------------------------
# 3. CONFIGURE FASTAPI AND CHAT ENDPOINT
# ---------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    context: Dict[str, Any] = {}

class ChatResponse(BaseModel):
    reply: str
    action: Optional[Dict[str, Any]] = None

SYSTEM_PROMPT = """
You are the assistant for the Youth Opportunity Desert Dashboard.

Your job:
1. Help users understand the dashboard.
2. Help users navigate the dashboard.
3. If the user asks a specific data question, FIRST check the DASHBOARD_UI_CONTEXT. If the answer isn't there, USE YOUR PROVIDED TOOLS to query the dataset. Do not guess.
4. If the user asks for a dashboard action, return one structured action.
5. If the user only wants an explanation or data answer, return action = null.

Return STRICT JSON only with this shape:
{
  "reply": "string",
  "action": null
}

OR

{
  "reply": "string",
  "action": {
    "type": "set_panel",
    "panel": "controls" | "overlays" | "location" | "faqs" | "share" | "assistant"
  }
}

OR

{
  "reply": "string",
  "action": {
    "type": "set_primary_view",
    "view": "yoi" | "coi" | "supervisor"
  }
}

OR

{
  "reply": "string",
  "action": {
    "type": "toggle_overlay",
    "overlay": "bounds" | "routes" | "stops" | "services",
    "enabled": true
  }
}
"""

def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"reply": text, "action": None}

    raw = match.group(0)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {"reply": text, "action": None}
        return {
            "reply": parsed.get("reply", "Sorry, I could not parse that request."),
            "action": parsed.get("action"),
        }
    except json.JSONDecodeError:
        return {"reply": text, "action": None}


@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Append the UI context dynamically here so Gemini knows what the user is looking at
    dynamic_system_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"DASHBOARD_UI_CONTEXT:\n{json.dumps(req.context, ensure_ascii=False)}\n"
    )
    
    # Tell Gemini about our Python functions using the 'tools' parameter
    config = types.GenerateContentConfig(
        system_instruction=dynamic_system_prompt,
        tools=[get_highest_lowest_tract, count_tracts_by_condition],
        temperature=0.2
    )

    try:
        # By using client.chats.create, the SDK will automatically run the Python functions 
        # if the LLM requests them, loop back, and generate the final answer for us!
        chat_session = client.chats.create(
            model="gemini-2.5-flash",
            config=config
        )

        response = chat_session.send_message(req.message)
        parsed = extract_json(response.text or "")
        
        return ChatResponse(
            reply=parsed.get("reply", "Sorry, I could not answer that."),
            action=parsed.get("action"),
        )
        
    except Exception as e:
        error_msg = str(e)
        
        # Check if we hit the Google rate limit
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            # Use RegEx to find the exact number of seconds Google wants us to wait
            match = re.search(r"Please retry in ([\d\.]+)s", error_msg)
            
            if match:
                # Convert the messy decimal (26.756...) into a clean whole number (27)
                wait_time = int(float(match.group(1))) + 1
                custom_reply = f"I'm receiving too many requests right now! Please try asking me again in {wait_time} seconds."
            else:
                # Fallback just in case Google changes their error message format
                custom_reply = "I'm receiving too many requests right now! Please wait about a minute and try asking me again."
                
            return ChatResponse(
                reply=custom_reply, 
                action=None
            )
            
        # If anything else breaks, show a generic fallback
        else:
            print(f"Backend Error: {error_msg}")
            return ChatResponse(
                reply="Sorry, my brain is currently offline. Please try again later!", 
                action=None
            )