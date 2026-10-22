from agents.chat_rules import (
    Understanding,
    answer_needs_human,
    decide,
    largest_amount,
)


def u(intent="policy_question", personal=False, risks=None, urgency="low", amount=None):
    return Understanding(intent, personal, risks or [], urgency, amount)


def test_plain_policy_question_is_answered():
    d = decide(u(), "What happens if my complaint isn't resolved within 30 days?")
    assert d.route == "policy"


def test_general_fraud_question_is_not_escalated():
    d = decide(u(), "What should I do if I get a fraud call?")
    assert d.route == "policy"


def test_person_asking_for_human_is_escalated_even_if_model_misses_it():
    d = decide(u(), "can I talk to a real person please")
    assert d.route == "handoff" and "human_request" in d.flags


def test_fraud_incident_is_escalated_with_safety_note():
    d = decide(u(personal=True, risks=["fraud"]), "Someone called and my account was hacked")
    assert d.route == "handoff" and d.safety_note and d.flags == ["fraud"]


def test_regex_backstop_catches_fraud_when_the_model_misses_it():
    d = decide(u(), "I shared my OTP with a caller and Rs. 20,000 was debited")
    assert d.route == "handoff" and d.safety_note


def test_large_amount_is_escalated_but_small_is_not():
    big = decide(u(personal=True, risks=["money_loss"], amount=120000), "my payment of 1.2 lakh failed")
    small = decide(u(personal=True, risks=["money_loss"], amount=3200), "my payment of Rs. 3,200 failed")
    assert big.route == "handoff" and "large_amount" in big.flags
    assert small.route == "policy"


def test_legal_threat_only_counts_when_it_is_the_customers_own_case():
    own = decide(u(personal=True), "The bank has not replied, I will go to court")
    general = decide(u(), "Can a complaint end up in court?")
    assert own.route == "handoff" and general.route == "policy"


def test_routes_follow_intent():
    assert decide(u("raise_complaint"), "I want to complain").route == "redirect_complaint"
    assert decide(u("check_status"), "where is my complaint").route == "redirect_status"
    assert decide(u("smalltalk"), "hello").route == "smalltalk"
    assert decide(u("out_of_scope"), "best pizza").route == "out_of_scope"


def test_amount_parsing():
    assert largest_amount("Rs. 38,073 and Rs 5000") == 38073
    assert largest_amount("lost ₹2.5 lakh") == 250000
    assert largest_amount("no money mentioned") == 0


def test_answer_needs_human_gates():
    assert answer_needs_human(0.2, True, 0.9)
    assert answer_needs_human(0.7, False, 0.9)
    assert answer_needs_human(0.7, True, 0.3)
    assert answer_needs_human(0.7, True, 0.9) is None
