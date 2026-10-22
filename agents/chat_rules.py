"""
Deciding what the chatbot does with a customer message.

The model only describes the message (what the customer wants, whether it
happened to them, which risks are present). Plain code, here, decides whether
that means "answer it" or "hand it to a person". Handoff rules are deliberately
not left to the model: whether a fraud report or a large loss reaches an admin
should not depend on how the model feels that day. Regex backstops catch the
cases where the model's classification misses an obvious signal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

LARGE_AMOUNT_INR = 50_000
MIN_RETRIEVAL_SCORE = 0.40   # below this the knowledge base has nothing relevant
MIN_ANSWER_CONFIDENCE = 0.5

HUMAN_RE = re.compile(
    r"\b(human|real person|live agent|live chat agent|representative|"
    r"(talk|speak|chat) (to|with) (a |an |the )?(person|agent|someone|somebody|staff|executive|manager|human|officer)|"
    r"connect me (to|with) (a |an )?(person|agent|someone|staff|executive|manager)|"
    r"customer (care|service) (agent|executive|team))\b",
    re.I,
)
FRAUD_RE = re.compile(
    r"\b(fraud\w*|scam\w*|phish\w*|hack\w*|stolen|unauthori[sz]ed|cheat\w*|duped|compromised|vishing|spoof\w*|"
    r"without my (consent|knowledge|permission))\b",
    re.I,
)
SECRET_SHARED_RE = re.compile(
    r"\b(shared|gave|given|told|sent|leaked|revealed)\b.{0,40}\b(otp|pin|cvv|password)\b|"
    r"\b(otp|pin|cvv|password)\b.{0,40}\b(shared|given|leaked|revealed)\b",
    re.I,
)
HAPPENED_RE = re.compile(
    r"\b(was|were|got|has been|have been|had|happened|debited|deducted|lost|called me|asked me|messaged me|"
    r"clicked|shared|transferred|charged)\b",
    re.I,
)
FIRST_PERSON_RE = re.compile(r"\b(i|my|me|mine|we|our)\b", re.I)
LEGAL_RE = re.compile(r"\b(lawyer|advocate|sue|suing|court|legal action|consumer (forum|court)|police|fir)\b", re.I)
AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr|k)?", re.I)
THANKS_RE = re.compile(r"^\s*(thanks|thank you|thx|ty|ok thanks|great,? thanks)\b", re.I)

_MULTIPLIER = {"k": 1_000, "lakh": 100_000, "lac": 100_000, "crore": 10_000_000, "cr": 10_000_000}


def largest_amount(text: str) -> int:
    best = 0
    for m in AMOUNT_RE.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        best = max(best, int(value * _MULTIPLIER.get((m.group(2) or "").lower(), 1)))
    return best


@dataclass
class Understanding:
    intent: str
    personal_incident: bool
    risks: list[str] = field(default_factory=list)
    urgency: str = "low"
    amount_inr: Optional[int] = None


@dataclass
class Decision:
    route: str                       # policy | redirect_complaint | redirect_status | smalltalk | out_of_scope | handoff
    reason: Optional[str] = None     # shown to the admin when route == "handoff"
    flags: list[str] = field(default_factory=list)
    safety_note: bool = False        # include fraud-safety guidance in the customer reply


def decide(u: Understanding, message: str) -> Decision:
    flags: list[str] = []

    wants_human = u.intent == "human_request" or bool(HUMAN_RE.search(message))
    if wants_human:
        return Decision("handoff", "Customer asked for a person", ["human_request"])

    personal = u.personal_incident
    risks = set(u.risks)

    backstop_fraud = bool(
        (FRAUD_RE.search(message) or SECRET_SHARED_RE.search(message))
        and HAPPENED_RE.search(message)
        and FIRST_PERSON_RE.search(message)
    )
    if backstop_fraud:
        personal = True
        risks.add("fraud")
    if personal and LEGAL_RE.search(message):
        risks.add("legal_threat")

    if personal:
        amount = max(u.amount_inr or 0, largest_amount(message))
        if "fraud" in risks:
            return Decision("handoff", "Possible fraud or scam reported", ["fraud"], safety_note=True)
        if "money_loss" in risks and amount >= LARGE_AMOUNT_INR:
            return Decision("handoff", f"Large amount involved (about Rs. {amount:,})", ["large_amount"])
        if "legal_threat" in risks:
            return Decision("handoff", "Customer mentions legal action", ["legal_threat"])
        if "regulator_threat" in risks:
            return Decision("handoff", "Customer says they will go to the regulator or Ombudsman", ["regulator_threat"])
        if "distress" in risks:
            return Decision("handoff", "Customer appears distressed", ["distress"])
        if u.urgency == "critical":
            return Decision("handoff", "Assessed as critical urgency", ["critical_urgency"])

    routes = {
        "policy_question": "policy",
        "raise_complaint": "redirect_complaint",
        "check_status": "redirect_status",
        "smalltalk": "smalltalk",
        "out_of_scope": "out_of_scope",
    }
    return Decision(routes.get(u.intent, "policy"), None, flags)


def answer_needs_human(top_score: Optional[float], grounded: bool, confidence: float) -> Optional[str]:
    if top_score is None or top_score < MIN_RETRIEVAL_SCORE:
        return "No relevant passage in the knowledge base"
    if not grounded:
        return "Knowledge base does not answer the question"
    if confidence < MIN_ANSWER_CONFIDENCE:
        return "Assistant was not confident in its answer"
    return None
