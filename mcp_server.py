from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import uvicorn
import json

from data_loader import election_data
from config import MCP_HOST, MCP_PORT

app = FastAPI(title="AP Election MCP Server")

PARTIES_KEY = {"AC_NO", "AC_NAME", "TOTAL_VOTES"}

def _get_parties(row: dict):
    return [k for k in row if k not in PARTIES_KEY]


class GetACResultsRequest(BaseModel):
    ac_list: list[int]
    year: str

class GetWinnerRequest(BaseModel):
    ac: int
    year: str

class GetPartyVoteShareRequest(BaseModel):
    ac: int
    year: str
    party: str

class ComputeVoteSwingRequest(BaseModel):
    ac_list: list[int]
    party: str
    year_from: str
    year_to: str

class CompareAcrossElectionsRequest(BaseModel):
    ac: int

class GetTopConstituenciesRequest(BaseModel):
    party: str
    year: str
    top_n: Optional[int] = 10
    bottom: Optional[bool] = False

class GetStatePartySummaryRequest(BaseModel):
    year: str

class SearchConstituencyByNameRequest(BaseModel):
    name_fragment: str

class BatchQueryRequest(BaseModel):
    ac_list: list[int]
    parties: list[str]
    years: list[str]

# Endpoints
@app.post("/tools/get_ac_results")
def get_ac_results(req: GetACResultsRequest):
    """Full results for one or many ACs in a given year."""
    df = election_data.get_year_df(req.year)
    if df is None:
        return {"error": f"Invalid year '{req.year}'. Valid years: {election_data.get_years()}"}

    result = {}
    for ac in req.ac_list:
        row = election_data.find_ac(req.year, ac)
        result[str(ac)] = row if row else "Not found"
    return result

@app.post("/tools/get_winner")
def get_winner(req: GetWinnerRequest):
    row = election_data.find_ac(req.year, req.ac)
    if not row:
        return {"error": f"AC {req.ac} not found in year {req.year}"}

    parties = _get_parties(row)
    if not parties:
        return {"error": "No party data found"}

    winner = max(parties, key=lambda p: row.get(p, 0))
    total = row.get("TOTAL_VOTES", 0)
    winner_votes = row[winner]
    vote_share = round(winner_votes / total * 100, 2) if total else 0

    return {
        "ac_no": req.ac,
        "ac_name": row["AC_NAME"],
        "year": req.year,
        "winner": winner,
        "votes": winner_votes,
        "vote_share_pct": vote_share,
        "total_votes": total
    }


@app.post("/tools/get_party_vote_share")
def get_party_vote_share(req: GetPartyVoteShareRequest):
    row = election_data.find_ac(req.year, req.ac)
    if not row:
        return {"error": f"AC {req.ac} not found in year {req.year}"}

    party = req.party.upper()
    if party not in row:
        return {"error": f"Party '{party}' not in dataset. Available: {_get_parties(row)}"}

    total = row.get("TOTAL_VOTES", 0)
    votes = row[party]
    share = round(votes / total * 100, 2) if total else 0

    return {
        "ac_no": req.ac,
        "ac_name": row["AC_NAME"],
        "year": req.year,
        "party": party,
        "votes": votes,
        "total_votes": total,
        "vote_share_pct": share
    }


@app.post("/tools/compute_vote_swing")
def compute_vote_swing(req: ComputeVoteSwingRequest):
    party = req.party.upper()
    results = []
    for ac in req.ac_list:
        row_from = election_data.find_ac(req.year_from, ac)
        row_to = election_data.find_ac(req.year_to, ac)

        if not row_from:
            results.append({"ac_no": ac, "error": f"Not found in {req.year_from}"})
            continue
        if not row_to:
            results.append({"ac_no": ac, "error": f"Not found in {req.year_to}"})
            continue

        if party not in row_from or party not in row_to:
            results.append({"ac_no": ac, "error": f"Party '{party}' not in dataset"})
            continue

        total_from = row_from.get("TOTAL_VOTES", 0)
        total_to = row_to.get("TOTAL_VOTES", 0)
        share_from = round(row_from[party] / total_from * 100, 2) if total_from else 0
        share_to = round(row_to[party] / total_to * 100, 2) if total_to else 0
        swing = round(share_to - share_from, 2)

        results.append({
            "ac_no": ac,
            "ac_name": row_from["AC_NAME"],
            "party": party,
            f"vote_share_{req.year_from}_pct": share_from,
            f"vote_share_{req.year_to}_pct": share_to,
            "swing_pct": swing
        })

    return {"swing_results": results, "year_from": req.year_from, "year_to": req.year_to}


@app.post("/tools/compare_across_elections")
def compare_across_elections(req: CompareAcrossElectionsRequest):
    years = election_data.get_years()
    comparison = {}

    for year in sorted(years):
        row = election_data.find_ac(year, req.ac)
        if row:
            parties = _get_parties(row)
            total = row.get("TOTAL_VOTES", 0)
            winner = max(parties, key=lambda p: row.get(p, 0)) if parties else "N/A"
            party_shares = {}
            for p in parties:
                votes = row[p]
                share = round(votes / total * 100, 2) if total else 0
                party_shares[p] = {"votes": votes, "share_pct": share}
            comparison[year] = {
                "ac_name": row["AC_NAME"],
                "winner": winner,
                "total_votes": total,
                "party_results": party_shares
            }
        else:
            comparison[year] = {"error": "Data not found"}

    return {"ac_no": req.ac, "comparison": comparison}

@app.post("/tools/get_top_constituencies")
def get_top_constituencies(req: GetTopConstituenciesRequest):
    party = req.party.upper()
    df = election_data.get_year_df(req.year)
    if df is None:
        return {"error": f"Invalid year '{req.year}'"}
    if party not in df.columns:
        return {"error": f"Party '{party}' not found in {req.year}"}

    df = df.copy()
    df["vote_share_pct"] = (df[party] / df["TOTAL_VOTES"] * 100).round(2)
    df_sorted = df.sort_values("vote_share_pct", ascending=req.bottom)
    top = df_sorted.head(req.top_n)

    return {
        "party": party,
        "year": req.year,
        "order": "bottom" if req.bottom else "top",
        "results": [
            {
                "ac_no": int(row["AC_NO"]),
                "ac_name": row["AC_NAME"],
                "votes": int(row[party]),
                "total_votes": int(row["TOTAL_VOTES"]),
                "vote_share_pct": row["vote_share_pct"]
            }
            for _, row in top.iterrows()
        ]
    }

@app.post("/tools/get_state_party_summary")
def get_state_party_summary(req: GetStatePartySummaryRequest):
    df = election_data.get_year_df(req.year)
    if df is None:
        return {"error": f"Invalid year '{req.year}'"}

    parties = election_data.get_parties(req.year)
    total_votes = int(df["TOTAL_VOTES"].sum())
    summary = {}
    for p in parties:
        p_votes = int(df[p].sum())
        share = round(p_votes / total_votes * 100, 2) if total_votes else 0
        seats_won = int((df[parties].idxmax(axis=1) == p).sum())
        summary[p] = {
            "total_votes": p_votes,
            "vote_share_pct": share,
            "seats_won": seats_won
        }

    return {
        "year": req.year,
        "total_votes_polled": total_votes,
        "total_constituencies": len(df),
        "party_summary": summary
    }

@app.post("/tools/search_constituency_by_name")
def search_constituency_by_name(req: SearchConstituencyByNameRequest):
    results = election_data.search_by_name(req.name_fragment)
    if not results:
        return {"error": f"No constituency found matching '{req.name_fragment}'"}
    return {"matches": results}

@app.post("/tools/batch_query")
def batch_query(req: BatchQueryRequest):
    """Multi-AC × multi-party × multi-year query in one call."""
    output = {}
    for year in req.years:
        output[year] = {}
        for ac in req.ac_list:
            row = election_data.find_ac(year, ac)
            if not row:
                output[year][str(ac)] = "Not found"
                continue
            total = row.get("TOTAL_VOTES", 0)
            ac_data = {"ac_name": row["AC_NAME"], "total_votes": total, "parties": {}}
            for party in req.parties:
                p = party.upper()
                if p in row:
                    votes = row[p]
                    share = round(votes / total * 100, 2) if total else 0
                    ac_data["parties"][p] = {"votes": votes, "vote_share_pct": share}
                else:
                    ac_data["parties"][p] = "Not available"
            output[year][str(ac)] = ac_data

    return output

@app.get("/") # Health check and basic info
def root():
    return {"status": "ok", "message": "AP Election MCP Server running", "years": election_data.get_years()}

if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)