"""Input validation, orchestration and transparent batch outputs."""
import json
from pathlib import Path
from .normalize import normalize
from .scoring import score_pair, duplicate_pairs, MATCH_THRESHOLD

DEFAULT_DATA = Path(__file__).resolve().parent.parent / 'data'


def load_events(path, source, timezone):
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(rows,list):
        raise ValueError(f'{path}: expected a JSON array')
    events, rejected, seen = [], [], set()
    for index,row in enumerate(rows):
        try:
            if not isinstance(row,dict):
                raise ValueError('Expected object')
            event = normalize(row,source,timezone)
            if event.id in seen:
                raise ValueError(f'Duplicate record ID: {event.id}')
            seen.add(event.id)
            events.append(event)
        except (ValueError,TypeError) as exc:
            rejected.append({'source':source,'row_index':index,'error':str(exc)})
    return events,rejected


def run(data_dir=DEFAULT_DATA, timezone='America/New_York', threshold=MATCH_THRESHOLD):
    if not 0 < threshold <= 1:
        raise ValueError('threshold must be in (0,1]')
    root = Path(data_dir)
    crm, bad_crm = load_events(root/'crm_events.json','crm',timezone)
    cal, bad_cal = load_events(root/'calendar_events.json','calendar',timezone)
    predictions = [score_pair(a,b,threshold) for a in crm for b in cal]
    duplicates = duplicate_pairs(cal)
    duplicate_keys = {frozenset((d['record_a'],d['record_b'])) for d in duplicates}
    for a in crm:
        matches = [p for p in predictions if p['crm_id']==a.id and p['match']]
        if len(matches)>1:
            ids = [p['calendar_id'] for p in matches]
            known_duplicate = all(frozenset((x,y)) in duplicate_keys for i,x in enumerate(ids) for y in ids[i+1:])
            for p in matches:
                p['warnings'].append('Multiple matches correspond to possible calendar duplicates' if known_duplicate else 'Multiple match candidates: manual resolution required')
    return {'config':{'timezone':timezone,'match_threshold':threshold,'confidence_kind':'heuristic_similarity_not_probability'},
            'counts':{'crm':len(crm),'calendar':len(cal),'pairs':len(predictions)},
            'predictions':predictions,'duplicate_candidates':duplicates,
            'unmatched_crm_ids':[a.id for a in crm if not any(p['match'] and p['crm_id']==a.id for p in predictions)],
            'unmatched_calendar_ids':[b.id for b in cal if not any(p['match'] and p['calendar_id']==b.id for p in predictions)],
            'data_quality':{'rejected_records':bad_crm+bad_cal,'record_warnings':[{'source':e.source,'id':e.id,'warnings':e.warnings} for e in crm+cal if e.warnings]}}
