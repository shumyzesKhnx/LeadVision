"""Compare immutable configuration identities for future analysis currentness checks."""

from app.models.icp import ICPVersion
from app.schemas.icp import InvalidationResponse


def configuration_change(previous: ICPVersion, current: ICPVersion) -> InvalidationResponse:
    # Result counts stay zero until analysis/scoring modules exist.
    return InvalidationResponse(scores_changed=previous.content_hash != current.content_hash,
                                semantic_changed=previous.semantic_input_hash != current.semantic_input_hash)


def configuration_is_current(profile, saved_version_id: str) -> bool:
    return not profile.archived and profile.current_version_id == saved_version_id


def campaign_configuration_is_current(campaign, profile, saved_icp_id: str, saved_version_id: str) -> bool:
    return (not campaign.archived and campaign.icp_id == profile.id == saved_icp_id
            and configuration_is_current(profile, saved_version_id))


def lead_analytical_inputs_are_current(lead, saved_input_revision: int) -> bool:
    return lead.analytical_input_revision == saved_input_revision
