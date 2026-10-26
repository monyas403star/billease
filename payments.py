"""Validate finite installment schedules before saving any row."""
from werkzeug.exceptions import BadRequest
import billease_security as security


def validate(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 120:
        raise BadRequest('Invalid payment schedule (1–120 payments required)')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise BadRequest('Invalid payment schedule')
        result.append(dict(amount=security.money(row.get('amount')),
                           due_date=security.due_date(security.text(row, 'due_date', 10, required=True))))
    return result
