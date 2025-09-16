# backend/app/genai_provider.py
import json
import logging
from typing import Dict, Any, Tuple, Optional
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an infrastructure extraction assistant. Read the user's short request and output a single JSON object only (no commentary).
The JSON must follow this schema exactly:

{
  "intent": "create_instance" | "other",
  "inferred": {
    "environment": "dev"|"qa"|"prod"|null,
    "instance_type": "string|null",
    "operating_system": "ubuntu"|"ubuntu22"|"amazon-linux"|"windows"|"centos"|null,
    "storage_size": integer|null,
    "region": "string|null",
    "keypair": {"type":"existing"|"new"|"default", "name":"string|null"},
    "vpc": {"mode":"default"|"existing", "id":"string|null"},
    "subnet": {"mode":"default"|"existing", "id":"string|null"}
  },
  "missing": ["list of dotted field names that are required but missing"],
  "confidence": 0.0
}

Rules:
- Only output JSON. No extra text.
- Use lowercase for enum-like fields.
- If you are not asked to create infrastructure, set intent to "other".
- Put null for unknown fields.
- Try to infer as much as possible; list missing required fields in `missing`.
"""

# Minimal list of required top-level fields we need before deploy
REQUIRED_FIELDS = [
    "environment",
    "instance_type",
    "operating_system",
    "storage_size",
    "region",
    "keypair.type"
]


class OpenAIProvider:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or OPENAI_API_KEY
        if not key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIProvider")
        self.client = AsyncOpenAI(api_key=key)

    async def extract_requirements(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calls the LLM to extract structured infra requirements.
        Returns dict matching the schema above. Falls back to a conservative parsed output
        on parse errors.
        """
        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.0,
                max_tokens=450,
            )
            raw = resp.choices[0].message.content.strip()
            parsed = json.loads(raw)
            # Basic shape validation & normalization
            parsed = _normalize_parsed(parsed)
            return parsed
        except Exception as e:
            logger.warning(f"OpenAI extract_requirements failed: {e}")
            # fallback: try a tiny heuristic parser
            return _heuristic_fallback(text)


def _normalize_parsed(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure keys exist and types are consistent. Will add missing arrays/fields.
    """
    out = {
        "intent": parsed.get("intent", "other"),
        "inferred": {
            "environment": None,
            "instance_type": None,
            "operating_system": None,
            "storage_size": None,
            "region": None,
            "keypair": {"type": "existing", "name": None},
            "vpc": {"mode": "default", "id": None},
            "subnet": {"mode": "default", "id": None},
        },
        "missing": [],
        "confidence": float(parsed.get("confidence", 0.0)) if parsed.get("confidence") is not None else 0.0
    }

    inf = parsed.get("inferred", {}) or {}
    for k in ["environment", "instance_type", "operating_system", "storage_size", "region"]:
        if k in inf and inf[k] is not None:
            out["inferred"][k] = inf[k]
    # keypair
    if "keypair" in inf and isinstance(inf["keypair"], dict):
        out["inferred"]["keypair"]["type"] = inf["keypair"].get("type", out["inferred"]["keypair"]["type"])
        out["inferred"]["keypair"]["name"] = inf["keypair"].get("name", None)
    # vpc/subnet
    if "vpc" in inf and isinstance(inf["vpc"], dict):
        out["inferred"]["vpc"]["mode"] = inf["vpc"].get("mode", out["inferred"]["vpc"]["mode"])
        out["inferred"]["vpc"]["id"] = inf["vpc"].get("id", None)
    if "subnet" in inf and isinstance(inf["subnet"], dict):
        out["inferred"]["subnet"]["mode"] = inf["subnet"].get("mode", out["inferred"]["subnet"]["mode"])
        out["inferred"]["subnet"]["id"] = inf["subnet"].get("id", None)

    # compute missing fields
    missing = []
    for f in REQUIRED_FIELDS:
        if "." in f:
            a, b = f.split(".", 1)
            if out["inferred"].get(a) is None or out["inferred"][a].get(b) is None:
                missing.append(f)
        else:
            if out["inferred"].get(f) is None:
                missing.append(f)
    out["missing"] = missing
    return out


def _heuristic_fallback(text: str) -> Dict[str, Any]:
    """
    Super-simple regex-based fallback if LLM call fails.
    Not perfect — but avoids blocking the flow.
    """
    import re
    low = text.lower()
    env = None
    for e in ("dev", "qa", "prod"):
        if re.search(rf"\b{e}\b", low):
            env = e
            break

    it = None
    m = re.search(r"\b([tmcmr]?[\d]+(?:\.\w+)?)\b", low)
    if m:
        it = m.group(1)

    os_type = None
    for k in ("ubuntu22","ubuntu","amazon linux","amazon-linux","windows","centos"):
        if k in low:
            os_type = k.replace(" ", "-")
            break

    region = None
    r = re.search(r"\b([a-z]{2}-[a-z]+-\d)\b", low)
    if r:
        region = r.group(1)

    sz = None
    s = re.search(r"(\d+)\s?gb", low)
    if s:
        sz = int(s.group(1))

    keypair_type = "existing" if "key" in low or "keypair" in low or "ssh" in low else "default"

    inferred = {
        "environment": env,
        "instance_type": it,
        "operating_system": os_type,
        "storage_size": sz,
        "region": region,
        "keypair": {"type": keypair_type, "name": None},
        "vpc": {"mode": "default", "id": None},
        "subnet": {"mode": "default", "id": None},
    }
    missing = []
    for f in REQUIRED_FIELDS:
        if "." in f:
            a, b = f.split(".",1)
            if inferred.get(a) is None or inferred[a].get(b) is None:
                missing.append(f)
        else:
            if inferred.get(f) is None:
                missing.append(f)
    return {"intent": "create_instance", "inferred": inferred, "missing": missing, "confidence": 0.2}
