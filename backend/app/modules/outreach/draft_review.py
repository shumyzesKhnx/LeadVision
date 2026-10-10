import re
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import check_revision
from app.modules.processing.activity_service import record_activity
from app.modules.outreach.outreach_model import OutreachRevision
from app.modules.outreach import outreach_repository as repository
from app.modules.outreach.outreach_service import response, grounding_stale
from app.modules.outreach.draft_grounding import check_text


def edit(session, draft, body, expected):
    check_revision(draft.revision, expected)
    previous = repository.revisions(session, draft.id)[0]
    values, unresolved = check_text(body.model_dump(), repository.sources(session, draft.id))
    old_text = previous.subject + '\n' + previous.body
    # Changed substantive sentences must be explicitly linked; editing never refreshes sources.
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', values['subject'] + '\n' + values['body']):
        sentence = sentence.strip()
        if not sentence or sentence in old_text or sentence in ('Hello,', 'Hi,', 'Thank you.', 'Best regards,') or sentence.endswith('?'):
            continue
        if not any(sentence in claim['text'] or claim['text'] in sentence for claim in values['claims']):
            unresolved.append('Link each changed factual statement to a source before approval.')
    draft.revision += 1
    session.add(OutreachRevision(draft_id=draft.id, number=draft.revision, state='Edited',
                                **values, unresolved_claims=list(dict.fromkeys(unresolved))))
    session.flush()
    record_activity(session, action='outreach.edited', origin='api', agency_id=draft.agency_id,
                    lead_id=draft.lead_id, new_value={'draft_id': draft.id, 'revision': draft.revision})
    return response(session, draft)


def review(session, draft, body, expected):
    check_revision(draft.revision, expected)
    current = repository.revisions(session, draft.id)[0]
    if body.decision == 'Approved':
        if not body.factual_review_acknowledged:
            raise AppError('FACTUAL_REVIEW_REQUIRED', 'Review the factual claims and acknowledge the source check.', 422)
        if current.unresolved_claims:
            raise AppError('UNRESOLVED_CLAIMS', 'Resolve the listed factual claims before approval.', 409)
        if grounding_stale(session, draft.grounding):
            raise AppError('CONTEXT_STALE', 'Prepare a new draft using current research and agency facts.', 409)
    elif not body.reason or not body.reason.strip():
        raise AppError('REJECTION_REASON_REQUIRED', 'Explain why you are rejecting this draft.', 422)
    if not body.reviewer.strip():
        raise AppError('REVIEWER_REQUIRED', 'Enter your reviewer name.', 422)
    draft.revision += 1
    session.add(OutreachRevision(draft_id=draft.id, number=draft.revision, state=body.decision,
        subject=current.subject, body=current.body, claims=current.claims, unresolved_claims=current.unresolved_claims,
        reviewer=body.reviewer.strip(), reason=body.reason))
    session.flush()
    record_activity(session, action=f'outreach.{body.decision.lower()}', origin='api', agency_id=draft.agency_id,
                    lead_id=draft.lead_id, new_value={'draft_id': draft.id, 'revision': draft.revision})
    return response(session, draft)


def approved_text(session, draft):
    current = repository.revisions(session, draft.id)[0]
    if current.state != 'Approved':
        raise AppError('DRAFT_NOT_APPROVED', 'Approve the current text before copying it.', 409)
    return {'subject': current.subject, 'body': current.body, 'revision_id': current.id,
            'stale_reasons': grounding_stale(session, draft.grounding), 'sent': False}
