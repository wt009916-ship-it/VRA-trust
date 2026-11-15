"""Reserve future rechecks once per persisted source, not once per repeated action."""
import json
from .agent_selections import Selection
from .agent_semantics import NumericDelivery, Limitation
from .agent_comparisons import Comparison
from .agent_reviews import SourceReview


def additional_reads(record, calls):
    prior = {d['record_id'] for d in record.get('professional_deliveries', [])}
    previous_reviews = {d['record_id'] for d in record.get('professional_reviews', [])}
    sources, reviews = set(prior), set(previous_reviews)
    for call in calls:
        name = call['function']['name']
        if name not in {'professional_deliver', 'professional_limit', 'professional_review', 'professional_compare'}:
            continue
        try:
            args = call['function']['arguments']
            args = json.loads(args) if isinstance(args, str) else args
            if name == 'professional_deliver':
                raw = args['delivery']
                typed = (Selection if 'fact_keys' in raw else NumericDelivery).model_validate(raw)
                sources.add(typed.record_id)
            elif name == 'professional_limit':
                sources.add(Limitation.model_validate(args['limitation']).record_id)
            elif name == 'professional_review':
                reviews.add(SourceReview.model_validate(args['review']).record_id)
            else:
                typed = Comparison.model_validate(args['comparison'])
                sources.update((typed.baseline_id, typed.candidate_id))
        except (ValueError, KeyError, TypeError):
            pass  # Invalid actions cannot persist a delivery; invoke audits their refusal.
    return len(sources - prior) + len(reviews - previous_reviews)
