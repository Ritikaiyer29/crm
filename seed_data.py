"""
Synthetic seed data generator for the agentic CRM.

Generates contacts, accounts, and tickets whose category distribution
matches the real `typical_share` weights already seeded into
grievance_categories (schema.sql) — so the data downstream agents are
built and evaluated against reflects real NCH complaint proportions,
not an arbitrary uniform spread.

Ticket narratives are template-based, not LLM-generated: this keeps
seeding fast, free, and reproducible (fixed --seed), and is an honest
methodology to describe in an interview ("synthetic narratives
calibrated to a real category distribution") rather than pretending
they're real complaint text.

Usage:
    pip install --break-system-packages faker sqlalchemy pgvector psycopg2-binary
    export DATABASE_URL=postgresql+psycopg2://...
    python seed_data.py --reset   # wipes previously generated demo data first
    python seed_data.py           # adds to whatever's already there
"""
from __future__ import annotations

import argparse
import os
import random
import string

from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()
from models import (
    Org, Contact, Account, GrievanceCategory, Ticket, Deal, Activity,
    AccountProduct, AccountStatus, TicketStatus, TicketPriority,
    DealType, DealStage, ActivityType,
)

# ---------- Config ----------
ORG_NAME = "NovaPay Bank"          # fictional — this is one bank's own complaint-handling CRM
NUM_CONTACTS = 260
NUM_TICKETS = 800
FREQUENT_POOL_FRACTION = 0.15      # share of contacts treated as repeat complainants
FREQUENT_PICK_PROB = 0.35          # chance a ticket goes to that pool instead of a fresh contact
RANDOM_SEED = 42

HIGH_SEVERITY_KEYWORDS = [
    "without user consent", "invested via website", "otp", "qr code", "blocked or held",
]

# ---------- Narrative templates, matched by keyword against the real category name ----------
# (Keyword matching avoids fragile exact-string/em-dash comparisons against the DB rows.)

def _fillers(fake: Faker) -> dict:
    return dict(
        amount=f"Rs. {random.randint(500, 250000):,}",
        ref="".join(random.choices(string.ascii_uppercase + string.digits, k=10)),
        channel=random.choice(["UPI", "IMPS", "NEFT", "ATM", "POS", "net banking", "the mobile app"]),
        city=fake.city(),
        merchant=fake.company(),
        days=random.randint(2, 12),
        card_last4=f"{random.randint(0, 9999):04d}",
    )


TEMPLATE_RULES: list[tuple[list[str], list[str]]] = [
    (["without user consent"], [
        "An amount of {amount} was debited from my account on {channel} without my knowledge or approval, reference {ref}.",
        "I noticed a debit of {amount} (ref {ref}) that I never authorised. No OTP or approval request reached me.",
    ]),
    (["wrongly transferred"], [
        "I tried to send {amount} to my own account but it went to an unknown account instead, transaction ref {ref}.",
        "Due to a wrong account number entered at the branch, {amount} was transferred to someone else's account (ref {ref}). The receiving bank has not responded in {days} days.",
    ]),
    (["delay or denial of service"], [
        "I have been trying to get my request processed at the {city} branch for {days} days with no response.",
        "My request submitted via {channel} has been pending for {days} days without any update from the bank.",
    ]),
    (["blocked or held"], [
        "My account was blocked without any prior notice. I only found out when a payment of {amount} failed.",
        "Since {days} days ago my account has been on hold and nobody at the {city} branch can explain why.",
    ]),
    (["invested via website"], [
        "I was convinced to invest {amount} through a website that promised guaranteed returns; the site is no longer reachable, ref {ref}.",
        "A fraudulent investment app took {amount} from my account (ref {ref}) and has since gone offline.",
    ]),
    (["otp", "qr code"], [
        "I received a call asking me to share an OTP to 'verify my account' and {amount} was debited immediately after, ref {ref}.",
        "I scanned a QR code sent by someone claiming to be from the bank and {amount} was deducted, ref {ref}.",
    ]),
    (["not dispensed from atm"], [
        "I withdrew {amount} at the {city} ATM but no cash came out, yet my account was debited (ref {ref}).",
        "The ATM near {city} debited {amount} without dispensing cash, and this was {days} days ago with no reversal.",
    ]),
    (["failed or delayed but amount debited"], [
        "A {channel} transaction of {amount} to {merchant} failed but the amount was debited and not reversed after {days} days.",
        "My payment of {amount} via {channel} shows failed on my end but the money left my account (ref {ref}).",
    ]),
    (["minimum balance"], [
        "I was charged a penalty for not maintaining minimum balance despite never being informed of the requirement, amount {amount}.",
        "An unexpected charge of {amount} was deducted for minimum balance non-maintenance without prior notice.",
    ]),
    (["misbehaviour", "misselling"], [
        "A bank representative at the {city} branch pressured me into buying a product I did not need and was rude when I declined.",
        "I was sold a product by an agent who misrepresented its terms; I only realised the actual terms {days} days later.",
    ]),
    (["cheque book"], [
        "I requested a new debit card {days} days ago and it still has not arrived at my registered address.",
        "My cheque book request from the {city} branch has been pending for {days} days with no tracking update.",
    ]),
    (["insurance policy"], [
        "An insurance policy was added to my account bundled with my loan without my explicit consent, premium {amount}.",
        "I discovered an insurance premium of {amount} being deducted for a policy I never agreed to purchase.",
    ]),
    (["excess or unnotified"], [
        "I was charged {amount} in service fees that were never disclosed to me when I opened the account.",
        "An unexplained charge of {amount} appeared on my statement with no prior notification.",
    ]),
    (["inactive account"], [
        "I asked the {city} branch to reactivate my account {days} days ago and it is still shown as inactive.",
        "My account has remained inactive for {days} days after I submitted the reactivation form.",
    ]),
    (["disbursement of loan"], [
        "My loan was approved but the disbursement of {amount} has been delayed by {days} days with no explanation.",
        "Despite completing all formalities, my loan amount of {amount} has still not been credited after {days} days.",
    ]),
    (["refund or cashback"], [
        "A refund of {amount} for a cancelled transaction (ref {ref}) was promised but never credited after {days} days.",
        "The cashback of {amount} advertised for using {channel} was never credited to my account.",
    ]),
    (["kyc details"], [
        "My KYC update submitted {days} days ago still shows as pending, and I cannot perform transactions above a limit.",
        "Incorrect KYC details were linked to my account, causing a mismatch that has blocked {channel} transactions.",
    ]),
    (["recovery calls", "promotional"], [
        "I keep receiving recovery calls for a loan I have already closed, several times a week.",
        "I am getting repeated promotional calls despite registering on the do-not-disturb list {days} days ago.",
    ]),
]

# Used only for the "Other" category (the NCH taxonomy's genuine catch-all
# bucket -- every one of the other 18 categories has a keyword-matched
# template above). The previous version of this list ("pending since N days",
# "not resolved after N days") accidentally read as generic delay complaints,
# which the triage agent then -- reasonably -- classified as "Delay or denial
# of service" instead of "Other", since nothing in the text actually signals
# "doesn't fit a standard category". These describe complaints that
# genuinely don't fit any of the 18 specific categories, so a classifier
# has an actual chance at learning what "Other" looks like instead of
# learning to associate it with generic delay language.
DEFAULT_TEMPLATES = [
    "The branch refused my locker surrender request without giving any valid reason, ref {ref}.",
    "The mobile banking app keeps logging me out while I try to update my nominee details, not during any payment.",
    "I requested an interest certificate for tax filing and was told the {city} branch does not issue this document, though other branches do.",
    "I have been trying to close my account for personal reasons and the {city} branch keeps giving me a different requirement each time I visit.",
    "My grievance is about a change in terms and conditions I was never properly informed about, not about any specific transaction.",
    "No staff member at the {city} branch could explain the process to me in a language I understand, so my query went unresolved.",
]


def render_narrative(fake: Faker, category_name: str) -> str:
    name_lower = category_name.lower()
    for keywords, templates in TEMPLATE_RULES:
        if any(kw in name_lower for kw in keywords):
            return random.choice(templates).format(**_fillers(fake))
    return random.choice(DEFAULT_TEMPLATES).format(**_fillers(fake))


def is_high_severity(category_name: str) -> bool:
    name_lower = category_name.lower()
    return any(kw in name_lower for kw in HIGH_SEVERITY_KEYWORDS)


def pick_priority(category_name: str) -> TicketPriority:
    if is_high_severity(category_name):
        weights = {TicketPriority.critical: 0.35, TicketPriority.high: 0.40,
                   TicketPriority.medium: 0.20, TicketPriority.low: 0.05}
    else:
        weights = {TicketPriority.low: 0.25, TicketPriority.medium: 0.45,
                   TicketPriority.high: 0.25, TicketPriority.critical: 0.05}
    return random.choices(list(weights.keys()), weights=list(weights.values()))[0]


def pick_status_and_resolution(date_received: datetime, now: datetime) -> tuple[TicketStatus, datetime | None]:
    age_days = (now - date_received).days
    if age_days <= 30:
        status = random.choices(
            [TicketStatus.open, TicketStatus.in_review, TicketStatus.pending_approval, TicketStatus.resolved],
            weights=[0.45, 0.20, 0.20, 0.15],
        )[0]
    else:
        status = random.choices(
            [TicketStatus.resolved, TicketStatus.escalated, TicketStatus.in_review, TicketStatus.pending_approval],
            weights=[0.75, 0.15, 0.05, 0.05],
        )[0]

    resolved_at = None
    if status == TicketStatus.resolved:
        resolved_at = date_received + timedelta(days=random.randint(1, min(30, max(age_days, 1))))
        resolved_at = min(resolved_at, now)
    return status, resolved_at


def reset_demo_data(session: Session) -> None:
    """Wipes generated demo data (contacts and everything that cascades from them)
    but leaves grievance_categories and any kb_documents/kb_chunks reference data intact."""
    session.execute(text("TRUNCATE contacts RESTART IDENTITY CASCADE;"))
    session.commit()
    print("Reset: cleared contacts, accounts, tickets, deals, activities.")


def get_or_create_org(session: Session) -> Org:
    org = session.scalar(select(Org).where(Org.name == ORG_NAME))
    if org is None:
        org = Org(name=ORG_NAME)
        session.add(org)
        session.commit()
        print(f"Created org: {ORG_NAME}")
    return org


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe previously generated demo data first")
    args = parser.parse_args()

    random.seed(RANDOM_SEED)
    fake = Faker("en_IN")
    Faker.seed(RANDOM_SEED)

    engine = create_engine(os.environ["DATABASE_URL"])
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        if args.reset:
            reset_demo_data(session)

        org = get_or_create_org(session)

        categories = session.scalars(select(GrievanceCategory)).all()
        if not categories:
            raise SystemExit("No grievance_categories found — run schema.sql first.")
        cat_weights = [float(c.typical_share or 0) for c in categories]

        # ---------- Contacts ----------
        contacts: list[Contact] = []
        for _ in range(NUM_CONTACTS):
            c = Contact(
                org_id=org.id,
                full_name=fake.name(),
                email=fake.email(),
                phone=fake.phone_number(),
            )
            contacts.append(c)
        session.add_all(contacts)
        session.commit()
        print(f"Created {len(contacts)} contacts.")

        # ---------- Accounts (1-2 per contact) ----------
        products = list(AccountProduct)
        accounts_by_contact: dict[str, list[Account]] = {}
        all_accounts = []
        for c in contacts:
            n = random.choices([1, 2], weights=[0.7, 0.3])[0]
            my_accounts = []
            for _ in range(n):
                opened_at = fake.date_between(start_date="-10y", end_date="-30d")
                status = random.choices(
                    [AccountStatus.active, AccountStatus.dormant, AccountStatus.closed],
                    weights=[0.85, 0.10, 0.05],
                )[0]
                a = Account(
                    org_id=org.id,
                    contact_id=c.id,
                    product=random.choice(products),
                    status=status,
                    opened_at=opened_at,
                )
                my_accounts.append(a)
                all_accounts.append(a)
            accounts_by_contact[str(c.id)] = my_accounts
        session.add_all(all_accounts)
        session.commit()
        print(f"Created {len(all_accounts)} accounts.")

        # ---------- Repeat-complainant pool ----------
        frequent_pool = random.sample(contacts, k=max(1, int(FREQUENT_POOL_FRACTION * len(contacts))))

        # ---------- Tickets ----------
        tickets_created: list[Ticket] = []
        for _ in range(NUM_TICKETS):
            contact = random.choice(frequent_pool) if random.random() < FREQUENT_PICK_PROB else random.choice(contacts)
            category = random.choices(categories, weights=cat_weights)[0]

            days_ago = random.randint(0, 180)
            date_received = now - timedelta(days=days_ago, hours=random.randint(0, 23))

            status, resolved_at = pick_status_and_resolution(date_received, now)
            priority = pick_priority(category.category_name)
            narrative = render_narrative(fake, category.category_name)

            my_accounts = accounts_by_contact.get(str(contact.id), [])
            account_id = random.choice(my_accounts).id if my_accounts else None

            t = Ticket(
                org_id=org.id,
                contact_id=contact.id,
                account_id=account_id,
                category_id=category.id,
                seeded_category_id=category.id,
                company=ORG_NAME,
                narrative=narrative,
                status=status,
                priority=priority,
                date_received=date_received,
                resolved_at=resolved_at,
            )
            tickets_created.append(t)
        session.add_all(tickets_created)
        session.commit()
        print(f"Created {len(tickets_created)} tickets.")

        # ---------- Activities (one "received via" note per ticket) ----------
        activities = [
            Activity(
                org_id=org.id,
                contact_id=t.contact_id,
                ticket_id=t.id,
                type=ActivityType.note,
                content="Complaint received and logged in the system.",
                created_at=t.date_received,
            )
            for t in tickets_created
        ]
        session.add_all(activities)
        session.commit()
        print(f"Created {len(activities)} activity log entries.")

        # ---------- Deals (retention risk / cross-sell, derived from ticket outcomes) ----------
        tickets_by_contact: dict[str, list[Ticket]] = {}
        for t in tickets_created:
            tickets_by_contact.setdefault(str(t.contact_id), []).append(t)

        deals = []
        for c in contacts:
            my_tickets = tickets_by_contact.get(str(c.id), [])
            if any(t.status == TicketStatus.escalated for t in my_tickets):
                deals.append(Deal(org_id=org.id, contact_id=c.id, type=DealType.retention_risk,
                                   stage=DealStage.identified,
                                   notes="Flagged: unresolved complaint past the 30-day regulatory window."))
            elif my_tickets and all(t.status == TicketStatus.resolved for t in my_tickets) and random.random() < 0.20:
                deals.append(Deal(org_id=org.id, contact_id=c.id, type=DealType.cross_sell,
                                   stage=DealStage.identified,
                                   notes="Cleanly resolved history — candidate for a cross-sell offer."))
        session.add_all(deals)
        session.commit()
        print(f"Created {len(deals)} deals ({sum(1 for d in deals if d.type == DealType.retention_risk)} retention-risk, "
              f"{sum(1 for d in deals if d.type == DealType.cross_sell)} cross-sell).")

        # ---------- Summary: does the generated distribution track typical_share? ----------
        print("\nCategory distribution check (generated % vs seeded typical_share %):")
        total = len(tickets_created)
        counts = {}
        for t in tickets_created:
            counts[t.category_id] = counts.get(t.category_id, 0) + 1
        for cat in sorted(categories, key=lambda c: float(c.typical_share or 0), reverse=True):
            got = counts.get(cat.id, 0)
            print(f"  {cat.category_name:<55} generated {got/total*100:5.1f}%   seeded {float(cat.typical_share or 0):5.1f}%")


if __name__ == "__main__":
    main()
