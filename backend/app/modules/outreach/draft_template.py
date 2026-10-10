"""A source-linked service introduction when generated text cannot be validated."""
from app.modules.outreach.draft_grounding import check_text


def service_introduction(snapshot, sources):
    source = next(item for item in sources if item['source_id'] == 'service')
    excerpt = source['text'][:400]
    subject = 'A conversation about your technology priorities'
    body = (f'Hello,\n\nI am reaching out from {snapshot["agency_name"]} to ask whether a conversation '
            'about your technology priorities would be useful.\n\n'
            f'Our selected service is described as:\n{excerpt}\n\n'
            'We would first want to understand your requirements, existing arrangements, and whether '
            'this service is relevant to your plans. We are not assuming that you need a new system '
            'or changes to your current setup.\n\n'
            'Would you be open to a brief introductory conversation? If this is not a priority, '
            'please feel free to let us know.\n\nBest regards,\n' + snapshot['agency_name'])
    values = {'subject': subject, 'body': body,
              'claims': [{'text': excerpt, 'source_id': 'service', 'quote': excerpt}]}
    return check_text(values, sources)
