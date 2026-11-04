#!/usr/bin/env python3
"""Refresh data.json for the Midterm Night Board.

Runs in GitHub Actions on a schedule. Every source is best-effort: a failure
keeps the previous value for that section and records the error, so the page
never goes blank because one feed is down.

Sources
  markets  Kalshi (public trade API), Polymarket (Gamma API), PredictIt (marketdata API)
  early    On Point Politics early-vote tracker (server-rendered HTML), UF Election Lab total
  calls    calls.json in this repo (hand-edited as AP calls races)
"""
import json, re, sys, time, datetime, pathlib
import urllib.request

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "data.json"
UA = {"User-Agent": "midterm-night-board/1.0 (+github pages)"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def getj(url):
    return json.loads(get(url))


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ---------- markets ----------
KAPI = "https://api.elections.kalshi.com/trade-api/v2"

def kprice(m):
    for k in ("last_price_dollars", "yes_bid_dollars", "yes_ask_dollars"):
        v = m.get(k)
        try:
            if v not in (None, "", "0", "0.00", "0.0000"):
                return round(float(v) * 100, 1)
        except Exception:
            pass
    for k in ("last_price", "yes_bid"):
        v = m.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def kevent_dem(event_ticker):
    """Return the Democratic YES price (0-100) for a Kalshi party-winner event, or None."""
    data = getj(f"{KAPI}/markets?event_ticker={event_ticker}&limit=50")
    for m in data.get("markets", []):
        lab = " ".join(str(m.get(k) or "") for k in ("yes_sub_title", "subtitle", "title", "ticker")).lower()
        if "democrat" in lab or lab.endswith("-d") or lab.endswith(" d"):
            p = kprice(m)
            if p is not None:
                return p
    return None


def kalshi():
    out = {"gov": {}, "sen": {}}
    for key, ev in (("senate_d", "CONTROLS-2026"), ("house_d", "CONTROLH-2026")):
        try:
            p = kevent_dem(ev)
            if p is not None:
                out[key] = p
        except Exception as e:
            out.setdefault("errors", []).append(f"{ev}: {e}")
    for st in GOV_STATES:
        try:
            p = kevent_dem(f"GOVPARTY{st}-26")
            if p is not None:
                out["gov"][st] = p
        except Exception:
            pass
    for st in SEN_STATES:
        for ev in (f"SENATE{st}-26", f"KXSENATE{st}-26"):
            try:
                p = kevent_dem(ev)
                if p is not None:
                    out["sen"][st] = p
                    break
            except Exception:
                pass
    if "senate_d" not in out and "house_d" not in out and not out["gov"]:
        raise RuntimeError("no Kalshi prices parsed: " + "; ".join(out.get("errors", [])))
    return out


GOV_STATES = ["AK","AZ","FL","GA","IA","KS","ME","MI","MN","NE","NV","NH","NM","NY","OH","OK","OR","PA","SC","TX","VT","WI"]
SEN_STATES = ["AK","GA","IA","KS","ME","MI","MN","NC","NE","NH","OH","SC","TX","FL"]


def polymarket():
    out = {}
    for slug, key in [("balance-of-power-2026-midterms", "bop"),
                      ("which-party-will-win-the-senate-in-2026", "senate"),
                      ("which-party-will-win-the-house-in-2026", "house")]:
        try:
            ev = getj(f"https://gamma-api.polymarket.com/events?slug={slug}")
            if not ev:
                continue
            for mk in ev[0].get("markets", []):
                q = (mk.get("question") or mk.get("groupItemTitle") or "").lower()
                prices = json.loads(mk.get("outcomePrices") or "[]")
                if not prices:
                    continue
                p = float(prices[0]) * 100
                if key == "bop" and "democrats sweep" in q:
                    out["sweep_d"] = round(p, 1)
                elif key == "senate" and "democrat" in q:
                    out["senate_d"] = round(p, 1)
                elif key == "house" and "democrat" in q:
                    out["house_d"] = round(p, 1)
        except Exception as e:  # noqa
            out.setdefault("errors", []).append(f"{slug}: {e}")
    if not any(k in out for k in ("senate_d", "house_d", "sweep_d")):
        raise RuntimeError("no Polymarket data: " + "; ".join(out.get("errors", [])))
    return out


def predictit():
    out = {}
    data = getj("https://www.predictit.org/api/marketdata/all/")
    for m in data.get("markets", []):
        n = (m.get("name") or "").lower()
        if "senate" in n and "control" in n and "2026" in n:
            for c in m.get("contracts", []):
                if "democrat" in (c.get("name") or "").lower():
                    out["senate_d"] = round((c.get("lastTradePrice") or 0) * 100, 1)
        if "house" in n and "control" in n and "2026" in n:
            for c in m.get("contracts", []):
                if "democrat" in (c.get("name") or "").lower():
                    out["house_d"] = round((c.get("lastTradePrice") or 0) * 100, 1)
    if not out:
        raise RuntimeError("no matching PredictIt markets")
    return out


# ---------- early vote ----------
STATES = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}


def onpoint():
    """Parse the national total and per-state rows from On Point's tracker page."""
    html = get("https://onpointpolitics.us/maps/early-vote")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    out = {"states": {}}
    m = re.search(r"([\d,]{9,}) ballots cast so far", text)
    if m:
        out["total"] = int(m.group(1).replace(",", ""))
    m = re.search(r"registered Democrats cast ([\d.]+) percent of those ballots and registered Republicans ([\d.]+) percent", text)
    if m:
        out["reg_d"], out["reg_r"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"Vs expectations\s*([DR]) \+([\d.]+)", text)
    if m:
        out["vs_expected"] = float(m.group(2)) * (1 if m.group(1) == "D" else -1)
    m = re.search(r"Party model\s*([DR]) \+([\d.]+)", text)
    if m:
        out["party_model"] = float(m.group(2)) * (1 if m.group(1) == "D" else -1)
    # state rows: Name  ballots  mail  inperson  pct%  pace  dem%  rep%
    for name, ab in STATES.items():
        pat = re.escape(name) + r" ([\d,]+) ([\d,]+) ([\d,]+) ([\d.]+)% (?:[+\-][\d.]+%|n/a) ([\d.]+%|n/a) ([\d.]+%|n/a)"
        mm = re.search(pat, text)
        if mm:
            row = {"ballots": int(mm.group(1).replace(",", "")), "mail": int(mm.group(2).replace(",", "")),
                   "inperson": int(mm.group(3).replace(",", "")), "pct2022": float(mm.group(4))}
            if mm.group(5) != "n/a":
                row["dem"] = float(mm.group(5).rstrip("%"))
            if mm.group(6) != "n/a":
                row["rep"] = float(mm.group(6).rstrip("%"))
            out["states"][ab] = row
    if "total" not in out and not out["states"]:
        raise RuntimeError("On Point page parsed nothing")
    return out


def polldesk():
    """Per-state ballots / mail returned / in person / mail requested from polling-desk.com, parsed by table row."""
    html = get("https://polling-desk.com/early-vote")
    out = {"states": {}}
    def num(x):
        x = re.sub(r"<[^>]+>", "", x).replace(",", "").strip()
        return int(x) if x.isdigit() else None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        if len(cells) < 5:
            continue
        name = re.sub(r"<[^>]+>", "", cells[0]).strip()
        ab = STATES.get(name)
        if not ab:
            continue
        ballots, mail, inp, req = (num(c) for c in cells[1:5])
        if ballots is None:
            continue
        out["states"][ab] = {"ballots": ballots, "mail": mail, "inperson": inp, "requested": req}
    if not out["states"]:
        raise RuntimeError("Polling Desk table parsed nothing")
    return out


def forecast():
    """Race margins from On Point's forecast strip (server-rendered on the early-vote page) and
    polling averages from callthemap.com/polls. Returns {races:{ST-SEN:margin,...}, generic:D+x, approval:x}."""
    out = {"races": {}}
    html = get("https://onpointpolitics.us/maps/early-vote")
    text = re.sub(r"<[^>]+>", " ", html); text = re.sub(r"\s+", " ", text)
    for st, office, who, party, num in re.findall(r"\b([A-Z]{2}) (Sen|Gov)\s+([A-Za-z.'\- ]{2,40}?)\s+([DRI]) \+([\d.]+)", text):
        key = st + ("-SEN" if office == "Sen" else "-GOV")
        m = float(num) * (1 if party == "D" else -1 if party == "R" else 0)
        if key not in out["races"]:
            out["races"][key] = {"margin": m, "leader": who.strip(), "party": party, "src": "onpoint"}
    try:
        html = get("https://www.callthemap.com/polls")
        text = re.sub(r"<[^>]+>", " ", html); text = re.sub(r"\s+", " ", text)
        m = re.search(r"Generic ballot\s*([DR])\+([\d.]+)", text)
        if m: out["generic"] = float(m.group(2)) * (1 if m.group(1) == "D" else -1)
        m = re.search(r"Presidential net approval\s*([−-]?[\d.]+)", text)
        if m: out["approval_net"] = float(m.group(1).replace("−", "-"))
        for name, party, num in re.findall(r"([A-Z][a-z]+(?: [A-Z][a-z]+)?) forecast →\s*\w+ \d+\s*([DR])\+([\d.]+)", text):
            ab = STATES.get(name)
            if ab:
                out["races"].setdefault(ab + "-SEN", {})
                out["races"][ab + "-SEN"]["avg"] = float(num) * (1 if party == "D" else -1)
    except Exception as e:
        out["callthemap_error"] = str(e)[:120]
    if not out["races"]:
        raise RuntimeError("forecast strip parsed nothing")
    return out


CIVIC = "https://civicapi.org/api/v2"
RES_SEN = ["AK","AL","AR","CO","DE","FL","GA","IA","ID","IL","KS","KY","LA","MA","ME","MI","MN","MS","MT","NC","NE","NH","NJ","NM","OH","OK","OR","RI","SC","SD","TN","TX","VA","WV","WY"]
RES_GOV = ["AL","AK","AZ","AR","CA","CO","CT","FL","GA","HI","ID","IL","IA","KS","ME","MD","MA","MI","MN","NE","NV","NH","NM","NY","OH","OK","OR","PA","RI","SC","SD","TN","TX","VT","WI","WY"]
RES_HOUSE = ["AK","AL","AZ","AR","CA","CO","FL","IA","IL","IN","KS","KY","ME","MI","MN","MO","MT","NC","NE","NH","NJ","NM","NV","NY","OH","PA","SC","TX","VA","WA","WI"]


def civic_races(payload):
    """Normalise a civicAPI response (single race, list, or wrapped) to a list of race dicts."""
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], (dict, list)):
            payload = payload["data"]
        elif "races" in payload:
            payload = payload["races"]
    if isinstance(payload, dict):
        return [payload]
    return [r for r in payload if isinstance(r, dict)] if isinstance(payload, list) else []


def civic_tally(race):
    d = r = o = 0
    called = None
    for c in race.get("candidates") or []:
        if c.get("dropped_out"):
            continue
        v = c.get("votes") or 0
        try:
            v = int(v)
        except Exception:
            v = 0
        party = str(c.get("party") or "").lower()
        if party.startswith("dem"):
            d += v
            if c.get("winner"): called = "D"
        elif party.startswith("rep"):
            r += v
            if c.get("winner"): called = "R"
        else:
            o += v
            if c.get("winner"): called = "I"
    pct = race.get("percent_reporting")
    try:
        pct = round(float(pct), 1)
    except Exception:
        pct = None
    out = {"d": d, "r": r, "o": o, "pct": pct, "src": "civicapi", "at": race.get("last_updated")}
    if called:
        out["called"] = called
    return out


NAME2AB = {v.lower(): k for k, v in {**{n: a for n, a in STATES.items()}}.items()} if False else {n.lower(): a for n, a in STATES.items()}


def _txt(x):
    if isinstance(x, dict):
        return x.get("en_US") or x.get("en") or next((v for v in x.values() if isinstance(v, str)), "")
    return str(x or "")


def classify(race):
    """Return (state_ab, kind, district) for a civicAPI race, kind in SEN/GOV/HOUSE, or None."""
    name = " ".join(_txt(race.get(k)) for k in ("election_name", "name", "title", "race_name", "office", "election_type", "type"))
    dd = race.get("district_details") or {}
    name += " " + " ".join(_txt(dd.get(k)) for k in ("district_name", "district_country", "state"))
    name += " " + " ".join(_txt(race.get(k)) for k in ("state", "region", "subdivision", "district"))
    low = name.lower()
    if "primary" in low or "runoff" in low and "2026" not in low:
        pass
    ab = None
    for n, a in sorted(NAME2AB.items(), key=lambda x: -len(x[0])):
        if n in low:
            ab = a
            break
    if not ab:
        m = re.search(r"\b(?:US[-_ ])?([A-Z]{2})\b", name)
        if m and m.group(1) in STATES.values():
            ab = m.group(1)
    if not ab:
        return None
    if "senate" in low and "state senate" not in low:
        return ab, "SEN", None
    if "governor" in low or "gubernatorial" in low:
        if "lieutenant" in low:
            return None
        return ab, "GOV", None
    if "house" in low or "congress" in low or "representative" in low:
        if "state house" in low or "house of delegates" in low:
            return None
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)\s+(?:congressional\s+)?district", low) or re.search(r"(?:district|cd|-)\s*(\d{1,2})", low)
        if m:
            return ab, "HOUSE", f"{ab}-{int(m.group(1)):02d}"
        if "at-large" in low or "at large" in low:
            return ab, "HOUSE", f"{ab}-AL"
    return None


def classify2(race):
    typ = str(race.get("type") or "").lower()
    ab = str(race.get("province") or "").upper()
    if ab not in STATES.values():
        return classify(race)
    if any(x in typ for x in ("shadow", "state senate", "state house", "lieutenant", "referendum", "proposition", "question", "judicial", "mayor", "assembly", "delegate")):
        return None
    if "senate" in typ:
        return ab, "SEN", None
    if "governor" in typ:
        return ab, "GOV", None
    if "representative" in typ or "house" in typ or "congress" in typ:
        dist = race.get("district")
        m = re.search(r"(\d{1,2})", str(dist or ""))
        if m:
            return ab, "HOUSE", f"{ab}-{int(m.group(1)):02d}"
        return ab, "HOUSE", f"{ab}-AL"
    return classify(race)


def results_auto():
    """Read the background scraper's latest output (results_auto.json)."""
    p = ROOT / "results_auto.json"
    if not p.exists():
        raise RuntimeError("no civicAPI results yet (background scraper starting)")
    st = json.loads(p.read_text())
    races = {k: v for k, v in (st.get("races") or {}).items() if v.get("d") or v.get("r") or v.get("called")}
    debug = {k: st.get(k) for k in ("mode", "fetched", "total", "updated", "final", "filters", "started")}
    debug["types"] = dict(sorted((st.get("types") or {}).items(), key=lambda x: -x[1])[:25])
    debug["matched"] = len(st.get("races") or {}); debug["matched_keys"] = sorted(st.get("races") or {})[:80]
    return {"races": races, "count": len(races), "matched": debug["matched"], "debug": debug}


def uf_total():
    html = get("https://election.lab.ufl.edu/early-vote/2026-early-voting/")
    text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(r"Total Early Votes:?\s*([\d,]{9,})", text)
    if not m:
        raise RuntimeError("UF total not found")
    return {"total": int(m.group(1).replace(",", ""))}


def main():
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
        except Exception:
            prev = {}
    data = {"generated": now(), "sources": {}, "baseline": prev.get("baseline") or {"senate_d": 76, "house_d": 94.5, "note": "midday Nov 3 open"}}
    for key, fn in [("kalshi", kalshi), ("polymarket", polymarket), ("predictit", predictit),
                    ("onpoint", onpoint), ("polldesk", polldesk), ("forecast", forecast), ("results_auto", results_auto)]:
        try:
            data[key] = fn()
            data["sources"][key] = {"ok": True, "at": now()}
        except Exception as e:
            data[key] = prev.get(key)
            data["sources"][key] = {"ok": False, "at": prev.get("sources", {}).get(key, {}).get("at"), "error": str(e)[:200]}
    results = ROOT / "results.json"
    if results.exists():
        try:
            data["results"] = json.loads(results.read_text())
            data["sources"]["results"] = {"ok": True, "at": now()}
        except Exception as e:
            data["results"] = prev.get("results"); data["sources"]["results"] = {"ok": False, "error": str(e)[:200]}
    auto = (data.get("results_auto") or {}).get("races", {})
    manual = (data.get("results") or {}).get("races", {})
    merged = dict(auto)
    merged.update(manual)
    data["results"] = {"updated": now(), "races": merged, "auto_count": len(auto), "manual_count": len(manual)}
    calls = ROOT / "calls.json"
    if calls.exists():
        try:
            data["calls"] = json.loads(calls.read_text())
        except Exception as e:
            data["calls"] = prev.get("calls"); data["sources"]["calls"] = {"ok": False, "error": str(e)[:200]}
    OUT.write_text(json.dumps(data, indent=1))
    ok = [k for k, v in data["sources"].items() if v.get("ok")]
    print("refreshed", data["generated"], "ok:", ok)


if __name__ == "__main__":
    main()
