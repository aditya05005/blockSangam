from app.domain.models import CorridorSlot, Task


def compatible_block_requirements(task: Task, slot: CorridorSlot) -> tuple[bool, str | None, str | None]:
    checks = (
        (task.requires_traffic_block, slot.traffic_block, "TRAFFIC_BLOCK_REQUIRED", "Slot does not provide a traffic block."),
        (task.requires_power_isolation, slot.power_isolation, "POWER_ISOLATION_REQUIRED", "Slot does not provide power isolation."),
        (task.requires_snt_disconnection, slot.snt_disconnection, "SNT_DISCONNECTION_REQUIRED", "Slot does not provide S&T disconnection."),
    )
    for required, available, code, message in checks:
        if required and not available:
            return False, code, message
    return True, None, None


def compatible_task_slot(task: Task, slot: CorridorSlot) -> tuple[bool, str | None, str | None]:
    if task.section != slot.section:
        return False, "SECTION_MISMATCH", "Task and slot are on different corridor sections."
    if task.line != slot.line:
        return False, "LINE_MISMATCH", "Task and slot are on different lines."
    return compatible_block_requirements(task, slot)
