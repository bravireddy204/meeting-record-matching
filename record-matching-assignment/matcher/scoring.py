"""Fixed, interpretable heuristics; this module never reads evaluation labels."""
from .normalize import compact, overlap, text

MATCH_THRESHOLD = 0.68
REVIEW_THRESHOLD = 0.50


def name_in_emails(name, emails):
    name = compact(name)
    return bool(name) and any(name == compact(e.split('@')[0]) for e in emails)


def score_pair(crm, calendar, threshold=MATCH_THRESHOLD):
    warnings = list(crm.warnings + calendar.warnings)
    same_day = crm.day is not None and crm.day == calendar.day
    minutes = abs((crm.instant-calendar.instant).total_seconds()) / 60 if crm.instant and calendar.instant else None
    timing = (1 if minutes <= 15 else .85 if minutes <= 45 else .65 if minutes <= 90 else .4 if minutes <= 180 else 0) if minutes is not None else None
    name = crm.raw.get('client_name')
    if text(name) in ('multiple', 'unknown', 'n a'):
        name = None
    company = crm.raw.get('client_company')
    identity = max(float(name_in_emails(name, calendar.emails)), overlap(company, calendar.title)) if name or company else None
    owner = float(name_in_emails(crm.raw.get('relationship_owner'), calendar.emails)) if crm.raw.get('relationship_owner') and calendar.emails else None
    topic = max(overlap(crm.title, calendar.title), .85*overlap(crm.title+' '+crm.body, calendar.title+' '+calendar.body))
    location = overlap(crm.raw.get('location'), calendar.raw.get('location')) if crm.raw.get('location') and calendar.raw.get('location') else None
    features = {'time': timing, 'identity': identity, 'topic': topic, 'owner': owner, 'location': location}
    weights = {'time': .30, 'identity': .25, 'topic': .25, 'owner': .15, 'location': .05}
    denominator = sum(weights[k] for k,v in features.items() if v is not None)
    score = sum(weights[k]*v for k,v in features.items() if v is not None) / denominator
    reasons = []
    if not same_day:
        score = 0.0
        reasons.append('Different or unknown local dates: automatic match blocked')
    else:
        reasons.append('Same local meeting date')
    if identity == 1:
        reasons.append('Client name/email or company text agrees')
    if topic >= .5:
        reasons.append('Meeting subject/content overlaps')
    if minutes is not None:
        reasons.append(f'Start-time difference: {minutes:g} minutes')
    strong_evidence = identity is not None and identity >= .8 or topic >= .5
    if not strong_evidence:
        score = min(score, .49)
        reasons.append('Insufficient client/topic evidence')
    if text(crm.raw.get('status')) in ('cancelled','canceled') or text(calendar.raw.get('status')) in ('cancelled','canceled'):
        warnings.append('Cancellation present; identity match does not imply active meeting')
    loc = text(calendar.raw.get('location'))
    if text(crm.raw.get('meeting_type')) == 'in person' and any(t in loc for t in ('zoom','teams','virtual')):
        warnings.append('Meeting modality conflict; not treated as an identity veto')
    if minutes is not None and minutes > 45 and same_day:
        warnings.append('Large time difference: verify rescheduling/timezone assumptions')
    decision = 'match' if score >= threshold else 'review' if score >= min(REVIEW_THRESHOLD,threshold) else 'non_match'
    return {'crm_id': crm.id, 'calendar_id': calendar.id, 'match': decision == 'match', 'decision': decision,
            'confidence': round(score,4), 'confidence_kind': 'heuristic_similarity_not_probability',
            'features': features, 'reasons': reasons, 'warnings': sorted(set(warnings))}


def duplicate_pairs(events):
    """Conservative candidate detection, preserving every original record."""
    result = []
    for i,a in enumerate(events):
        for b in events[i+1:]:
            if not a.instant or not b.instant or a.day != b.day:
                continue
            delta = abs((a.instant-b.instant).total_seconds())/60
            people_a, people_b = set(a.emails),set(b.emails)
            attendees = len(people_a & people_b)/min(len(people_a),len(people_b)) if people_a and people_b else 0
            topic = max(overlap(a.title,b.title),overlap(a.title+' '+a.body,b.title+' '+b.body))
            if delta <= 60 and attendees >= .8 and topic >= .5 and overlap(a.raw.get('location'),b.raw.get('location')) >= .5:
                result.append({'source':'calendar','record_a':a.id,'record_b':b.id,'duplicate':True,
                               'decision':'possible_duplicate','confidence':round(.4*attendees+.4*topic+.2*(1-delta/120),4),
                               'reason':'Nearby starts, overlapping participants, topic and location; retain both pending review'})
    return result
