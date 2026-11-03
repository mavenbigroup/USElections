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
def kalshi():
    """Senate / House control and balance of power from Kalshi's public API.
    Event tickers: CONTROLS-2026 (Senate), CONTROLH-2026 (House), KXBALANCEPOWERCOMBO-27FEB (combo)."""
    out = {}
    def scan(url, key, want):
        data = getj(url)
        for m in data.get("markets", []):
            t = " ".join(str(m.get(k) or "") for k in ("title", "subtitle", "yes_sub_title", "ticker")).lower()
            yes = m.get("last_price") or m.get("yes_bid") or 0
            if want(t) and yes:
                out[key] = yes
    try:
        scan("https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=CONTROLS-2026&limit=50", "senate_d", lambda t: "dem" in t)
    except Exception as e: out.setdefault("errors", []).append(f"senate: {e}")
    try:
        scan("https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=CONTROLH-2026&limit=50", "house_d", lambda t: "dem" in t)
    except Exception as e: out.setdefault("errors", []).append(f"house: {e}")
    try:
        scan("https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=KXBALANCEPOWERCOMBO-27FEB&limit=50", "sweep_d", lambda t: "sweep" in t and "dem" in t)
    except Exception as e: out.setdefault("errors", []).append(f"combo: {e}")
    if not any(k in out for k in ("senate_d", "house_d", "sweep_d")):
        # fallback: page through open markets by title
        base = "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open"
        cursor = None
        for _ in range(5):
            data = getj(base + (("&cursor=" + cursor) if cursor else ""))
            for m in data.get("markets", []):
                t = " ".join(str(m.get(k) or "") for k in ("title", "yes_sub_title")).lower()
                yes = m.get("last_price") or m.get("yes_bid") or 0
                if "senate" in t and "control" in t and "dem" in t: out["senate_d"] = yes
                if "house" in t and "control" in t and "dem" in t: out["house_d"] = yes
            cursor = data.get("cursor")
            if len(out) >= 2 or not cursor: break
    if not any(k in out for k in ("senate_d", "house_d", "sweep_d")):
        raise RuntimeError("no matching Kalshi markets: " + "; ".join(out.get("errors", [])))
    return out


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
                    ("onpoint", onpoint), ("uf", uf_total)]:
        try:
            data[key] = fn()
            data["sources"][key] = {"ok": True, "at": now()}
        except Exception as e:
            data[key] = prev.get(key)
            data["sources"][key] = {"ok": False, "at": prev.get("sources", {}).get(key, {}).get("at"), "error": str(e)[:200]}
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
