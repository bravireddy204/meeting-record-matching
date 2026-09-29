"""Non-destructive normalization with explicit data quality warnings."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import unicodedata
from zoneinfo import ZoneInfo


def text(value):
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()).strip()


def compact(value):
    return text(value).replace(' ', '')


def tokens(value):
    stop = {'the', 'a', 'an', 'and', 'with', 'for', 'of', 'to', 'in', 'on', 'meeting', 'discussion', 'call', 'session'}
    return set(text(value).split()) - stop


def overlap(a, b):
    a, b = tokens(a), tokens(b)
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


@dataclass
class Event:
    id: str
    source: str
    raw: dict
    day: object
    instant: object
    title: str
    body: str
    emails: list
    warnings: list


def normalize(raw, source, local_timezone='America/New_York'):
    warnings, emails = [], []
    zone = ZoneInfo(local_timezone)
    instant = day = None
    if source == 'crm':
        value = raw.get('meeting_date')
        for fmt in ('%Y-%m-%d', '%m-%d/%Y'):
            try:
                day = datetime.strptime(str(value), fmt).date()
                if fmt != '%Y-%m-%d':
                    warnings.append('Repaired date using explicit MM-DD/YYYY format')
                break
            except ValueError:
                pass
        if day is None:
            warnings.append('Missing or invalid meeting date')
        if day and raw.get('meeting_time'):
            try:
                instant = datetime.fromisoformat(f"{day}T{raw['meeting_time']}").replace(tzinfo=zone).astimezone(timezone.utc)
            except ValueError:
                warnings.append('Invalid meeting time')
        else:
            warnings.append('Missing meeting time')
        title, body = raw.get('subject') or '', raw.get('notes') or ''
        record_id = raw.get('crm_id')
    else:
        try:
            instant = datetime.fromisoformat(str(raw.get('start_time')).replace('Z', '+00:00'))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=zone)
                warnings.append('Naive timestamp interpreted in configured local timezone')
            day = instant.astimezone(zone).date()
            instant = instant.astimezone(timezone.utc)
        except ValueError:
            warnings.append('Missing or invalid start timestamp')
            instant = None
        people = raw.get('attendees') or []
        if not isinstance(people, list):
            warnings.append('Invalid attendees field; ignored')
            people = []
        for value in [raw.get('organizer')] + people:
            if not isinstance(value, str):
                continue
            repaired = value.lower().strip().replace('[at]', '@')
            if repaired != value.lower().strip():
                warnings.append('Repaired obfuscated email')
            if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', repaired):
                emails.append(repaired)
            else:
                warnings.append('Ignored non-email participant')
        title, body = raw.get('title') or '', raw.get('description') or ''
        record_id = raw.get('event_id')
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError(f'{source} record has missing/invalid ID')
    return Event(record_id, source, raw, day, instant, title, body, sorted(set(emails)), warnings)
