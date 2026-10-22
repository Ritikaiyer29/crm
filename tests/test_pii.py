from agents.pii import redact, redact_text


def test_masks_phone_and_email():
    text, counts = redact("Call me on 9876543210 or +91 98765 43210, mail ritika.iyer@gmail.com")
    assert "9876543210" not in text and "98765 43210" not in text and "gmail.com" not in text
    assert counts == {"EMAIL": 1, "PHONE": 2}


def test_masks_valid_card_but_not_random_16_digits():
    assert "[CARD]" in redact_text("my card 4111 1111 1111 1111 was charged")
    assert "[CARD]" not in redact_text("order 1234 5678 9012 3456 failed")


def test_masks_aadhaar_pan_ifsc():
    text, counts = redact("Aadhaar 2345 6789 0123, PAN ABCDE1234F, IFSC HDFC0001234")
    assert counts == {"AADHAAR": 1, "PAN": 1, "IFSC": 1}
    assert "ABCDE1234F" not in text


def test_masks_otp_pin_cvv_digits_but_keeps_the_word():
    text, counts = redact("I shared OTP 482913 and my cvv is 123 with them")
    assert "482913" not in text and "123" not in text
    assert "OTP" in text and counts["SECRET"] == 2


def test_masks_upi_id_and_account_number():
    text, counts = redact("paid merchant@okhdfcbank from account 123456789012")
    assert "merchant@okhdfcbank" not in text and "123456789012" not in text
    assert counts == {"UPI_ID": 1, "ACCOUNT_NO": 1}


def test_keeps_amounts_dates_and_reference_numbers():
    ref = "3f2b8c1e-8d4a-4e6f-9a1b-2c3d4e5f6a7b"
    original = f"UPI payment of Rs. 38,073 and Rs 5000 on 15 October failed, ref {ref}"
    text, counts = redact(original)
    assert text == original and counts == {}


def test_plain_question_is_untouched():
    q = "What happens if my complaint isn't resolved within 30 days?"
    assert redact_text(q) == q
