from scripts.monitor import REMINDER_SECONDS, notification_for


def test_new_issue_creates_alert():
    message = notification_for(["disk"], [], 0, 100)
    assert message is not None
    assert "disk" in message


def test_duplicate_issue_does_not_spam():
    message = notification_for(["disk"], ["disk"], 100, 100 + REMINDER_SECONDS - 1)
    assert message is None


def test_duplicate_issue_gets_six_hour_reminder():
    message = notification_for(["disk"], ["disk"], 100, 100 + REMINDER_SECONDS)
    assert message is not None


def test_recovery_creates_message():
    message = notification_for([], ["disk"], 100, 200)
    assert message is not None
    assert "восстановлена" in message
