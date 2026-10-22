"""
Adds the "NovaPay help guide" to the knowledge base so the chatbot can answer
practical how-do-I questions, not only quote the RBI Ombudsman scheme.

This is demo content written for this project, not a real bank's policy. It
sticks to how the portal works and to widely published RBI guidance, and tells
customers to confirm specifics with the bank. Safe to re-run: it replaces the
document it created before.

Usage:
    python seed_help_kb.py
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

load_dotenv()
from agents.knowledge import embed_query
from models import KBChunk, KBDocument, Org

DOC_TITLE = "NovaPay Customer Help Guide"
DOC_SOURCE = "NovaPay help guide (demo content written for this project)"

TOPICS: list[tuple[str, str]] = [
    (
        "How to raise a complaint",
        "Open the NovaPay complaints portal and choose 'Raise a complaint'. Enter your name, then describe what "
        "happened in your own words, including amounts, dates and what you expected to happen. Email and phone are "
        "optional. When you submit, you immediately get a reference number. Save it: you need it to track the "
        "complaint.",
    ),
    (
        "What to include in a complaint",
        "A complaint is handled faster when it states the date, the amount, the channel (UPI, IMPS, ATM, card, net "
        "banking or branch), the transaction or reference ID of the payment, what you expected, and what the bank has "
        "told you so far. Never put your OTP, PIN, CVV or password in a complaint or in this chat. Nobody from the "
        "bank needs them.",
    ),
    (
        "Tracking a complaint",
        "Choose 'Track a complaint' and enter your reference number. You see the status, category, priority, the date "
        "received and the date by which the bank must resolve it. A new complaint shows category 'Other' and priority "
        "'medium' at first. That is normal: the category and priority are updated after a staff member reviews the "
        "assistant's classification.",
    ),
    (
        "What happens after you submit",
        "Your complaint is read by an automated assistant that proposes a category and a priority. Nothing changes on "
        "your complaint until a staff member approves that proposal. Staff can edit or reject it. As the resolution "
        "deadline gets close, the system flags the complaint to the handling team so it is not missed.",
    ),
    (
        "Resolution timeline and escalation",
        "Under the RBI Integrated Ombudsman Scheme the bank is expected to resolve your complaint within 30 days. The "
        "date is shown when you track your reference number. If the bank does not reply within 30 days, or you are not "
        "satisfied with its reply, you can take the complaint to the RBI Ombudsman through the RBI's Complaint "
        "Management System at cms.rbi.org.in.",
    ),
    (
        "Fraud and OTP safety",
        "Never share your OTP, PIN, CVV or password with anyone, including people who say they are from the bank. If "
        "you shared one or money was debited without your consent, contact the bank immediately to block the card or "
        "account, call the national cyber crime helpline 1930, and report it on cybercrime.gov.in. Reporting quickly "
        "matters: RBI's customer-protection rules generally limit your liability for unauthorised electronic "
        "transactions that are reported within three working days. Confirm the details for your case with the bank.",
    ),
    (
        "Failed transaction but money debited",
        "When a UPI or IMPS payment fails but the money leaves your account, it is normally reversed automatically. "
        "Under RBI's turnaround-time framework a failed UPI payment is generally expected to be reversed by the next "
        "working day, and cash that an ATM debited but did not dispense within five working days, with compensation of "
        "Rs. 100 per day of delay after that. If the money has not come back within that time, raise a complaint with "
        "the date, amount and transaction ID. Confirm the exact timelines for your case with the bank.",
    ),
    (
        "Charges and fees",
        "If you were charged for not maintaining a minimum balance, or you see a service charge you were not told "
        "about, note the date, the name of the charge and the amount from your statement, and raise a complaint with "
        "those details. Charges you were never notified about are a valid reason to complain.",
    ),
    (
        "KYC problems",
        "If your KYC details are not linked, or were updated incorrectly, raise a complaint stating which detail is "
        "wrong and when you last submitted documents. Keep the acknowledgement or reference you received when you "
        "submitted them.",
    ),
    (
        "Complaint types we handle",
        "The portal handles banking complaints such as amount debited without consent, wrongly transferred amounts, "
        "delay or denial of service, an account blocked without notice, fraudulent transactions, ATM cash debited but "
        "not dispensed, failed online transactions where the amount was debited, minimum-balance and service charges, "
        "misbehaviour or mis-selling by staff, delays in cards, cheque books or statements, insurance sold without "
        "consent, delays in loan processing, refunds or cashback not credited, KYC problems, and unwanted promotional "
        "or recovery calls.",
    ),
    (
        "When a staff member joins this chat",
        "The assistant answers general questions on its own. If your message involves fraud, a large amount, a legal "
        "or regulator threat, or if the assistant cannot answer reliably, the chat is passed to a staff member who "
        "replies in the same chat window. The conversation is saved in this browser, so you can close the page and "
        "come back to see the reply. You can also ask for a person at any time.",
    ),
    (
        "What the assistant cannot do",
        "The assistant cannot reverse a payment, refund money, block an account or promise an outcome, and it cannot "
        "see your account. It can explain the process, help you describe your complaint, and point you to the right "
        "step. Decisions about your complaint are made by bank staff.",
    ),
]


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        org = session.scalars(select(Org)).first()
        if org is None:
            raise SystemExit("No organization found; seed the database first.")

        session.execute(delete(KBDocument).where(KBDocument.org_id == org.id, KBDocument.title == DOC_TITLE))
        doc = KBDocument(org_id=org.id, title=DOC_TITLE, source=DOC_SOURCE)
        session.add(doc)
        session.flush()

        for i, (topic, body) in enumerate(TOPICS):
            chunk_text = f"[NovaPay help guide -- {topic}] {body}"
            session.add(KBChunk(document_id=doc.id, chunk_index=i, chunk_text=chunk_text, embedding=embed_query(chunk_text)))
        session.commit()
        print(f"Wrote {len(TOPICS)} chunks for '{DOC_TITLE}'.")


if __name__ == "__main__":
    main()
