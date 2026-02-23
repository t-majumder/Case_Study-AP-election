import pandas as pd
from pathlib import Path
from config import DATA_PATH


class ElectionData:
    def __init__(self):
        path = Path(DATA_PATH)
        if not path.exists():
            raise FileNotFoundError(f"Excel file not found at: {DATA_PATH}")

        raw = pd.read_excel(path, sheet_name=None)
        self.data = {}

        for year, df in raw.items():
            df.columns = [c.strip().upper() for c in df.columns]
            df["AC_NO"] = df["AC_NO"].astype(int)
            self.data[str(year).strip()] = df

    def get_years(self):
        return list(self.data.keys())

    def get_year_df(self, year: str):
        return self.data.get(str(year))

    def find_ac(self, year: str, ac_no: int):
        df = self.get_year_df(year)
        if df is None:
            return None
        row = df[df["AC_NO"] == int(ac_no)]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def search_by_name(self, name_fragment: str):
        """Return list of {ac_no, ac_name, year} matching the name fragment."""
        results = []
        name_fragment = name_fragment.strip().upper()
        for year, df in self.data.items():
            matches = df[df["AC_NAME"].str.upper().str.contains(name_fragment, na=False)]
            for _, row in matches.iterrows():
                results.append({
                    "ac_no": int(row["AC_NO"]),
                    "ac_name": row["AC_NAME"],
                    "year": year
                })
                
        seen = set()
        unique = []
        for r in results:
            if r["ac_no"] not in seen:
                seen.add(r["ac_no"])
                unique.append(r)
        return unique

    def get_parties(self, year: str):
        df = self.get_year_df(year)
        if df is None:
            return []
        skip = {"AC_NO", "AC_NAME", "TOTAL_VOTES"}
        return [c for c in df.columns if c not in skip]


election_data = ElectionData()