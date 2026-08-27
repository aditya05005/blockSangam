from app.candidates.models import Candidate


def can_share_block(left: Candidate, right: Candidate) -> tuple[bool, str | None, str | None]:
    if left.section != right.section:
        return False, "SECTION_MISMATCH", "Candidates are on different corridor sections."
    if left.line != right.line:
        return False, "LINE_MISMATCH", "Candidates are on different lines."
    if left.start_time >= right.end_time or right.start_time >= left.end_time:
        return False, "NO_TIME_OVERLAP", "Candidates do not overlap; they can remain separate assignments."
    # A shared resource cannot be used by two activities at the same time.
    if set(left.resource_ids) & set(right.resource_ids):
        return False, "RESOURCE_CONFLICT", "Candidates use the same resource during overlapping time."
    return True, None, None
