import io
import re
from typing import Dict

import pandas as pd


def _normalize(text: str) -> str:
    text = str(text).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _find_sheet(xl: pd.ExcelFile, candidates):
    norm_map = {_normalize(name): name for name in xl.sheet_names}
    for c in candidates:
        key = _normalize(c)
        if key in norm_map:
            return norm_map[key]
    for c in candidates:
        key = _normalize(c)
        for norm_name, real_name in norm_map.items():
            if key in norm_name or norm_name in key:
                return real_name
    return None


def _read_sheet(xl: pd.ExcelFile, candidates):
    sheet_name = _find_sheet(xl, candidates)
    if not sheet_name:
        return pd.DataFrame()
    df = pd.read_excel(xl, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_game_data(file_obj) -> Dict[str, pd.DataFrame]:
    xbytes = file_obj.read()
    xl = pd.ExcelFile(io.BytesIO(xbytes))

    data = {
        "Standard": _read_sheet(xl, ["Standard"]),
        "Custom": _read_sheet(xl, ["Custom"]),
        "Inventory": _read_sheet(xl, ["Inventory"]),
        "Financial": _read_sheet(xl, ["Financial", "Finance"]),
        "WorkForce": _read_sheet(xl, ["WorkForce", "Workforce"]),
    }

    for name, df in data.items():
        if not df.empty and "Day" in df.columns:
            df["Day"] = pd.to_numeric(df["Day"], errors="coerce")
            df = df.dropna(subset=["Day"]).copy()
            df["Day"] = df["Day"].astype(int)
            data[name] = df.sort_values("Day").reset_index(drop=True)

    return data