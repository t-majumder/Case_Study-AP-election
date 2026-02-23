import json
import httpx
from pydantic import BaseModel, Field
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_groq import ChatGroq

try:
    from langgraph.prebuilt import create_react_agent
    USE_LANGGRAPH = True
except ImportError:
    USE_LANGGRAPH = False

if not USE_LANGGRAPH:
    try:
        from langchain.agents import create_tool_calling_agent, AgentExecutor
    except ImportError:
        from langchain_core.agents import create_tool_calling_agent
        try:
            from langchain.agents import AgentExecutor
        except ImportError:
            from langchain_core.agents import AgentExecutor

from config import GROQ_API_KEY, MODEL_NAME, TEMPERATURE, MCP_BASE_URL
from prompts import SYSTEM_PROMPT


class MCPClient:
    def call(self, tool_name: str, args: dict):
        try:
            r = httpx.post(
                f"{MCP_BASE_URL}/tools/{tool_name}",
                json=args,
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            return {"error": f"HTTP error calling tool '{tool_name}': {str(e)}"}
        except Exception as e:
            return {"error": str(e)}


def _wrap(mcp: MCPClient, tool_name: str):
    def fn(**kwargs):
        return json.dumps(mcp.call(tool_name, kwargs), indent=2)
    return fn

# Tools definitions with Pydantic schemas for input validation
def _build_tools(mcp: MCPClient):

    class GetACResultsInput(BaseModel):
        ac_list: List[int] = Field(description="List of AC numbers")
        year: str = Field(description="Election year: 2014, 2019, or 2024")

    class GetWinnerInput(BaseModel):
        ac: int = Field(description="AC number")
        year: str = Field(description="Election year: 2014, 2019, or 2024")

    class GetPartyVoteShareInput(BaseModel):
        ac: int = Field(description="AC number")
        year: str = Field(description="Election year")
        party: str = Field(description="Party name (TDP, YSRCP, INC, BJP, JSP)")

    class ComputeVoteSwingInput(BaseModel):
        ac_list: List[int] = Field(description="List of AC numbers")
        party: str = Field(description="Party name")
        year_from: str = Field(description="Start year")
        year_to: str = Field(description="End year")

    class CompareAcrossElectionsInput(BaseModel):
        ac: int = Field(description="AC number to compare across all elections")

    class GetTopConstituenciesInput(BaseModel):
        party: str = Field(description="Party name")
        year: str = Field(description="Election year")
        top_n: Optional[int] = Field(default=10, description="Number of results")
        bottom: Optional[bool] = Field(default=False, description="If True, return bottom N instead")

    class GetStatePartySummaryInput(BaseModel):
        year: str = Field(description="Election year")

    class SearchConstituencyByNameInput(BaseModel):
        name_fragment: str = Field(description="Partial or full AC name to search")

    class BatchQueryInput(BaseModel):
        ac_list: List[int] = Field(description="List of AC numbers")
        parties: List[str] = Field(description="List of party names")
        years: List[str] = Field(description="List of election years")

    return [
        StructuredTool(name="get_ac_results",
            description="Get full election results (all parties) for one or more ACs in a given year.",
            args_schema=GetACResultsInput, func=_wrap(mcp, "get_ac_results")),
        StructuredTool(name="get_winner",
            description="Get the winning party and their votes/share for an AC in a year.",
            args_schema=GetWinnerInput, func=_wrap(mcp, "get_winner")),
        StructuredTool(name="get_party_vote_share",
            description="Get a specific party's vote count and percentage share in an AC for a given year.",
            args_schema=GetPartyVoteShareInput, func=_wrap(mcp, "get_party_vote_share")),
        StructuredTool(name="compute_vote_swing",
            description="Compute vote swing (change in vote share %) for a party across ACs between two years.",
            args_schema=ComputeVoteSwingInput, func=_wrap(mcp, "compute_vote_swing")),
        StructuredTool(name="compare_across_elections",
            description="Compare all election years for a single AC - winner and party results for 2014, 2019, 2024.",
            args_schema=CompareAcrossElectionsInput, func=_wrap(mcp, "compare_across_elections")),
        StructuredTool(name="get_top_constituencies",
            description="Get top (or bottom) N constituencies ranked by a party's vote share in a given year.",
            args_schema=GetTopConstituenciesInput, func=_wrap(mcp, "get_top_constituencies")),
        StructuredTool(name="get_state_party_summary",
            description="Get state-wide total votes, vote share %, and seats won per party for a given year.",
            args_schema=GetStatePartySummaryInput, func=_wrap(mcp, "get_state_party_summary")),
        StructuredTool(name="search_constituency_by_name",
            description="Look up AC number(s) by searching for a partial or full constituency name.",
            args_schema=SearchConstituencyByNameInput, func=_wrap(mcp, "search_constituency_by_name")),
        StructuredTool(name="batch_query",
            description="Query multiple ACs x multiple parties x multiple years in a single call.",
            args_schema=BatchQueryInput, func=_wrap(mcp, "batch_query")),
    ]

class ElectionAgent:
    def __init__(self):
        self.llm = ChatGroq(
            api_key=GROQ_API_KEY,
            model_name=MODEL_NAME,
            temperature=TEMPERATURE
        )
        self.mcp = MCPClient()
        self.tools = _build_tools(self.mcp)

        if USE_LANGGRAPH:
            self.agent = create_react_agent(self.llm, self.tools)
            self._use_langgraph = True
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
            agent = create_tool_calling_agent(self.llm, self.tools, prompt)
            self.agent = AgentExecutor(agent=agent, tools=self.tools,
                                       verbose=False, max_iterations=10)
            self._use_langgraph = False

    def chat(self, query: str) -> str:
        if self._use_langgraph:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query}
            ]
            result = self.agent.invoke({"messages": messages})
            return result["messages"][-1].content
        else:
            result = self.agent.invoke({"input": query})
            return result["output"]