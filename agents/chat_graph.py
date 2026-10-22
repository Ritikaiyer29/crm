"""
LangGraph graph for one chatbot turn.

    understand -> route -> policy ----> (answered) -> END
                       |           \\-> (not grounded) -> handoff -> END
                       +-> redirect_complaint / redirect_status / smalltalk / out_of_scope -> END
                       +-> handoff -> END

`understand` makes one LLM call that only describes the message. `route` is
plain code (agents/chat_rules.py) and decides whether a person must take over.
`policy` answers strictly from retrieved knowledge-base passages and gives up
when they do not support an answer. Every LLM-bound string is PII-redacted.

The graph never changes a ticket. The only thing a turn writes is the chat
transcript and, on handoff, the conversation's status, summary and draft reply
for the admin inbox.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agents import chat_rules as rules
from agents.knowledge import Passage, search
from agents.llm import invoke_structured
from agents.pii import redact_text

COMPLAINT_URL = "/submit-complaint"
STATUS_URL = "/complaint-status"


class UnderstandingModel(BaseModel):
    intent: Literal["policy_question", "raise_complaint", "check_status", "human_request", "smalltalk", "out_of_scope"]
    personal_incident: bool = Field(description="True only if the customer describes something that already happened to them.")
    risks: list[Literal["fraud", "money_loss", "legal_threat", "regulator_threat", "distress"]]
    urgency: Literal["low", "medium", "high", "critical"]
    amount_inr: Optional[int] = Field(default=None, description="Largest rupee amount the customer mentions, as a plain integer.")


class PolicyAnswerModel(BaseModel):
    grounded: bool = Field(description="True only if the numbered passages actually answer the question.")
    answer: str = Field(description="Plain-language answer under 120 words. Empty if grounded is false.")
    confidence: float = Field(ge=0.0, le=1.0)
    used: list[int] = Field(description="Numbers of the passages the answer relies on.")


class HandoffNoteModel(BaseModel):
    summary: str = Field(description="2-3 sentences for the staff member: who, what happened, amounts, what the customer wants.")
    draft_reply: str = Field(description="A reply the staff member could send, under 100 words.")


class ChatState(TypedDict, total=False):
    message: str
    history: list[dict]          # [{"role": "customer"|"bot"|"admin", "text": str}] oldest first, already redacted
    understanding: dict
    decision: dict
    reply: str
    citations: list[dict]
    handoff: Optional[dict]      # {reason, flags, summary, draft_reply}
    meta: dict
    fallbacks: int               # consecutive turns the bot could not help, before this one


def _transcript(history: list[dict], message: str, limit: int = 8) -> str:
    lines = [f"{h['role']}: {h['text']}" for h in history[-limit:]]
    lines.append(f"customer: {message}")
    return "\n".join(lines)


UNDERSTAND_PROMPT = """You classify one message from a customer of an Indian bank's complaints help chat.
Describe the message only. Do not answer it.

intent:
- policy_question: asks how something works, a timeline, a right, or what to do about a problem
  ("my payment failed, what should I do" is a policy_question)
- raise_complaint: explicitly says they want to file, register or lodge a complaint
- check_status: wants the status of an existing complaint
- human_request: asks for a person, agent or manager
- smalltalk: greeting or thanks
- out_of_scope: unrelated to banking complaints

personal_incident: true only if the customer says something already happened to them (money debited, a scam call,
an account blocked). A general question about what to do IF something happens is false.
risks (only when personal_incident is true): fraud (scam, unauthorised transaction, shared OTP/PIN), money_loss,
legal_threat, regulator_threat (says they will go to the RBI or Ombudsman), distress (very upset, panicking).
urgency: low, medium, high, critical (critical = ongoing loss or fraud in progress).
amount_inr: the largest rupee amount mentioned, as an integer; 1.5 lakh = 150000.

Conversation so far:
{transcript}"""

POLICY_PROMPT = """You are the help assistant for NovaPay Bank's complaints portal. Answer the customer's latest message
using ONLY the numbered passages below.

Rules:
- If the passages do not answer the question, set grounded=false and leave answer empty.
- Never promise a refund, reversal, compensation or any outcome. Never give legal advice.
- Never ask for an OTP, PIN, CVV, password or full card or account number.
- Plain language, under 120 words. A short list is fine. Do not mention "passages" or their numbers in the answer.
- If the customer describes a problem they have had, say they can raise a complaint on the portal.
- List the numbers of the passages you used in `used`.

Passages:
{passages}

Conversation so far:
{transcript}"""

HANDOFF_PROMPT = """A customer chat is being passed to a bank staff member. Reason: {reason}.
Write (1) a short summary for the staff member and (2) a draft reply they can edit and send.
The draft must be polite and specific, ask for any missing facts (date, amount, transaction ID), and must NOT
promise a refund, reversal or outcome. {extra}

Conversation:
{transcript}"""


def build_chat_graph(session: Session, org_id):
    def understand(state: ChatState) -> ChatState:
        result = invoke_structured(
            UnderstandingModel,
            UNDERSTAND_PROMPT.format(transcript=_transcript(state["history"], state["message"])),
            reasoning_effort="low",
        )
        return {**state, "understanding": result.model_dump()}

    def route(state: ChatState) -> ChatState:
        u = rules.Understanding(**state["understanding"])
        d = rules.decide(u, state["message"])
        if d.route == "out_of_scope" and state.get("fallbacks", 0) >= 1:
            d = rules.Decision("handoff", "Assistant could not help after two tries", ["repeated_fallback"])
        return {**state, "decision": {"route": d.route, "reason": d.reason, "flags": d.flags, "safety_note": d.safety_note}}

    def pick(state: ChatState) -> str:
        return state["decision"]["route"]

    def policy(state: ChatState) -> ChatState:
        query = state["message"]
        if len(query.split()) < 6:
            prev = [h["text"] for h in state["history"] if h["role"] == "customer"]
            if prev:
                query = f"{prev[-1]} {query}"
        passages: list[Passage] = search(session, query, org_id, k=4)
        top = passages[0].score if passages else None
        meta = {**state.get("meta", {}), "retrieval": [{"label": p.label, "score": round(p.score, 3), "method": p.method} for p in passages]}

        if top is None or top < rules.MIN_RETRIEVAL_SCORE:
            # Nothing relevant: not a hard case, just outside what the guides cover. Say so once; a second
            # miss in a row goes to a person.
            if state.get("fallbacks", 0) >= 1:
                return {**state, "meta": meta, "decision": {**state["decision"], "route": "handoff", "reason": "Assistant could not help after two tries", "flags": ["repeated_fallback"]}}
            return {
                **state,
                "meta": {**meta, "fallback": True},
                "reply": (
                    "I couldn't find anything about that in my guides. I can help with banking complaints and how the "
                    "complaint process works. If you'd like a team member to look at it, just say so."
                ),
            }

        numbered = "\n\n".join(f"[{i}] ({p.label}) {p.text}" for i, p in enumerate(passages, start=1))
        out = invoke_structured(
            PolicyAnswerModel,
            POLICY_PROMPT.format(passages=numbered, transcript=_transcript(state["history"], state["message"])),
            temperature=0.2,
        )
        reason = rules.answer_needs_human(top, out.grounded and bool(out.answer.strip()), out.confidence)
        if reason:
            return {**state, "meta": meta, "decision": {**state["decision"], "route": "handoff", "reason": reason, "flags": ["no_answer"]}}

        cited = [passages[i - 1] for i in dict.fromkeys(out.used) if 1 <= i <= len(passages)] or passages[:1]
        return {
            **state,
            "meta": {**meta, "confidence": out.confidence},
            "reply": out.answer.strip(),
            "citations": [{"label": p.label} for p in cited],
        }

    def after_policy(state: ChatState) -> str:
        return "handoff" if state["decision"]["route"] == "handoff" else "done"

    def redirect_complaint(state: ChatState) -> ChatState:
        return {
            **state,
            "reply": (
                "I can help you get this on record. Please use the complaint form. It takes a couple of minutes and "
                f"gives you a reference number you can track: [Raise a complaint]({COMPLAINT_URL}).\n\n"
                "Include the date, the amount, how you paid (UPI, card, ATM) and the transaction ID. "
                "Please don't type any OTP, PIN or password."
            ),
        }

    def redirect_status(state: ChatState) -> ChatState:
        return {
            **state,
            "reply": (
                f"You can check a complaint on the [Track a complaint]({STATUS_URL}) page with your reference number. "
                "If you can't find your reference number, tell me and I'll pass this to a team member."
            ),
        }

    def smalltalk(state: ChatState) -> ChatState:
        if rules.THANKS_RE.search(state["message"]):
            reply = "You're welcome. Ask me anything else about complaints, or I can pass you to a team member."
        else:
            reply = (
                "Hello, I'm NovaPay's help assistant. I can explain how complaints work, the RBI timelines, and what to "
                "do in common situations like a failed payment or a suspected scam. What would you like to know?"
            )
        return {**state, "reply": reply}

    def out_of_scope(state: ChatState) -> ChatState:
        return {
            **state,
            "meta": {**state.get("meta", {}), "fallback": True},
            "reply": (
                "I can only help with banking complaints and how the complaint process works, so I can't help with "
                "that one. If you'd like, I can pass you to a team member."
            ),
        }

    def handoff(state: ChatState) -> ChatState:
        d = state["decision"]
        reason = d.get("reason") or "Needs a person"
        extra = (
            "This looks like a possible fraud, so the draft should tell them to stop sharing codes, block the card or "
            "account with the bank, call 1930 and report on cybercrime.gov.in."
            if d.get("safety_note")
            else ""
        )
        try:
            note = invoke_structured(
                HandoffNoteModel,
                HANDOFF_PROMPT.format(reason=reason, extra=extra, transcript=_transcript(state["history"], state["message"], limit=12)),
                temperature=0.3,
                reasoning_effort="low",
            )
            summary, draft = note.summary.strip(), note.draft_reply.strip()
        except Exception:  # noqa: BLE001 - a missing summary must not block the handoff itself
            summary, draft = f"{reason}. Latest message: {state['message'][:300]}", ""

        if d.get("safety_note"):
            reply = (
                "I'm sorry this happened. I'm passing this to a team member now, and they will reply right here in this "
                "chat. In the meantime: don't share any OTP, PIN or CVV with anyone, contact your bank to block the card "
                "or account, and report it on cybercrime.gov.in or call 1930."
            )
        else:
            reply = (
                "I'm passing this to a team member who can look into it properly. They will reply right here in this "
                "chat. You can close the page and come back later; the conversation is saved in this browser."
            )
        return {
            **state,
            "reply": reply,
            "handoff": {"reason": reason, "flags": d.get("flags", []), "summary": summary, "draft_reply": draft},
        }

    g = StateGraph(ChatState)
    for name, fn in [
        ("understand", understand), ("route", route), ("policy", policy), ("redirect_complaint", redirect_complaint),
        ("redirect_status", redirect_status), ("smalltalk", smalltalk), ("out_of_scope", out_of_scope), ("handoff", handoff),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_edge("understand", "route")
    g.add_conditional_edges(
        "route",
        pick,
        {
            "policy": "policy", "redirect_complaint": "redirect_complaint", "redirect_status": "redirect_status",
            "smalltalk": "smalltalk", "out_of_scope": "out_of_scope", "handoff": "handoff",
        },
    )
    g.add_conditional_edges("policy", after_policy, {"handoff": "handoff", "done": END})
    for name in ("redirect_complaint", "redirect_status", "smalltalk", "out_of_scope", "handoff"):
        g.add_edge(name, END)
    return g.compile()
