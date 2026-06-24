import requests
import pandas as pd
from io import StringIO
import time
import os

BASE_URL = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"

OUTPUT_DIR = "nist_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def build_params(element, low_w="", upp_w=""):
    return {
        "spectra": element,
        "output_type": 0,
        "low_w": low_w,
        "upp_w": upp_w,
        "unit": 1,
        "submit": "Retrieve Data",   # 🔥 IMPORTANT (this fixes 500 issue)
        "de": 0,
        "plot_out": 0,
        "I_scale_type": 1,
        "format": 2,
        "line_out": 0,
        "remove_js": "on",
        "en_unit": 0,
        "output": 0,
        "bibrefs": 1,
        "page_size": 1000 if low_w else 15,
        "show_obs_wl": 1,
        "show_calc_wl": 1,
        "unc_out": 1,
        "order_out": 0,
        "max_low_enrg": "",
        "show_av": 2,
        "max_upp_enrg": "",
        "tsb_value": 0,
        "min_str": "",
        "A_out": 0,
        "intens_out": "on",
        "max_str": "",
        "allowed_out": 1,
        "forbid_out": 1,
        "min_accur": "",
        "min_intens": "",
        "conf_out": 1,
        "term_out": 1,
        "enrg_out": 1,
        "J_out": 1,
    }


def fetch(element, low_w="", upp_w=""):

    params = build_params(element, low_w, upp_w)

    print(f"Downloading {element} (low={low_w}, high={upp_w})")

    r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=300)

    print("HTTP:", r.status_code)

    if r.status_code != 200:
        return None

    text = r.text

    if "<html" in text.lower():
        print("Got HTML instead of CSV (NIST error page)")
        return None

    try:
        text = text.replace('="', '"').replace('"', '')

        df = pd.read_csv(StringIO(text), engine="python", on_bad_lines="skip")
        df["element"] = element
        df["range"] = f"{low_w}-{upp_w}"

        return df

    except Exception as e:
        print("Parse error:", e)
        return None


def run(elements):

    all_data = []

    for el in elements:

        # 🔥 CASE 1: full dataset (like your working link)
        df1 = fetch(el, low_w="", upp_w="")

        # 🔥 CASE 2: wavelength filtered (like your second link)
        df2 = fetch(el, low_w=200, upp_w=900)

        for df in [df1, df2]:
            if df is not None and not df.empty:
                all_data.append(df)

                path = os.path.join(OUTPUT_DIR, f"{el}_{len(df)}.csv")
                df.to_csv(path, index=False)
                print("Saved:", path)

        time.sleep(2)

    if all_data:
        final = pd.concat(all_data, ignore_index=True)
        final.to_csv(os.path.join(OUTPUT_DIR, "ALL.csv"), index=False)
        print("\nDONE -> ALL.csv created")


# RUN
elements = ["Fe", "Na", "Ca", "Mg"]

run(elements)

