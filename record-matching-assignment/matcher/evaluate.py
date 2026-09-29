"""Evaluate explicitly labeled pairs only; absent labels are unknown."""
def metrics(rows):
    tp=sum(r['actual'] and r['predicted'] for r in rows)
    fp=sum(not r['actual'] and r['predicted'] for r in rows)
    fn=sum(r['actual'] and not r['predicted'] for r in rows)
    tn=sum(not r['actual'] and not r['predicted'] for r in rows)
    div=lambda a,b: round(a/b,4) if b else None
    return {'labeled_pairs':len(rows),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'precision':div(tp,tp+fp),'recall':div(tp,tp+fn),'f1':div(2*tp,2*tp+fp+fn),'accuracy':div(tp+tn,len(rows)),
            'errors':[r for r in rows if r['actual']!=r['predicted']]}


def evaluate(result, labels):
    index={(p['crm_id'],p['calendar_id']):p for p in result['predictions']}
    rows=[]
    seen=set()
    for label in labels.get('cross_source_pairs',[]):
        key=(label['crm_id'],label['calendar_id'])
        if key in seen or key not in index or not isinstance(label['match'],bool):
            raise ValueError(f'Duplicate, unavailable or invalid label: {key}')
        seen.add(key)
        p=index[key]
        rows.append({**label,'actual':label['match'],'predicted':p['match'],'confidence':p['confidence'],'decision':p['decision']})
    duplicate_keys={frozenset((d['record_a'],d['record_b'])) for d in result['duplicate_candidates']}
    dup_rows=[]
    for label in labels.get('intra_source_duplicates',[]):
        if label['source'] != 'calendar':
            raise ValueError('Only calendar duplicate evaluation is implemented')
        dup_rows.append({**label,'actual':label['duplicate'],'predicted':frozenset((label['record_a'],label['record_b'])) in duplicate_keys})
    return {'cross_source':metrics(rows),'duplicate_detection':metrics(dup_rows),'labeled_predictions':rows,
            'label_coverage':len(rows)/len(index) if index else 0,
            'limitations':'Partial, small, visible label set; descriptive evaluation, not an independent test of generalization. Review decisions count as negative for binary metrics. Unlabeled pairs excluded.'}
