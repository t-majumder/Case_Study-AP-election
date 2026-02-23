import os
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-120b"
TEMPERATURE = 0

# Data
DATA_PATH = "AP_Election_Data.xlsx"

# MCP Server
MCP_HOST = "0.0.0.0"
MCP_PORT = 8000
MCP_BASE_URL = f"http://localhost:{MCP_PORT}"

PARTIES = ["TDP", "YSRCP", "INC", "BJP", "JSP"]
VALID_YEARS = ["2014", "2019", "2024"]