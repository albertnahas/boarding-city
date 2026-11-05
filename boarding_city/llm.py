"""One structured-output call via the OpenAI Responses API, with a timeout, retries, and a per-call cost log."""
import json, os, time
import requests
from . import config


def ask(work, model, prompt, schema, tag, effort=None):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set (export it or put it in .env)")
    body = {"model": model, "input": prompt,
            "text": {"format": {"type": "json_schema", "name": "out", "strict": True, "schema": schema}}}
    if effort:
        body["reasoning"] = {"effort": effort}
    t = time.time()
    for attempt in range(1, config.RETRIES + 1):
        try:
            r = requests.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"},
                              json=body, timeout=config.TIMEOUT).json()
        except requests.RequestException as e:
            if attempt == config.RETRIES:
                raise SystemExit(f"{tag}: {e}")
            time.sleep(2 * attempt)
            continue
        if r.get("error"):
            if attempt == config.RETRIES:
                raise SystemExit(f"{tag}: {r['error']}")
            time.sleep(2 * attempt)
            continue
        break
    out = json.loads(next(c["text"] for o in r["output"] if o["type"] == "message" for c in o["content"]))
    u = r["usage"]
    pi, po = config.PRICES.get(model, (0, 0))
    cost = (u["input_tokens"] * pi + u["output_tokens"] * po) / 1e6
    with open(work / "costs.jsonl", "a") as f:
        f.write(json.dumps({"tag": tag, "model": model, "in": u["input_tokens"], "out": u["output_tokens"],
                            "cost": round(cost, 5), "s": round(time.time() - t)}) + "\n")
    return out


def spent(work):
    p = work / "costs.jsonl"
    return sum(json.loads(l)["cost"] for l in p.read_text().splitlines()) if p.exists() else 0.0
