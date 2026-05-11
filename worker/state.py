from common.enums import WorkerStatus


class WorkerStateMachine:
    def __init__(self) -> None:
        self._status = WorkerStatus.HEALTHY

    @property
    def status(self) -> WorkerStatus:
        return self._status

    def transition(self, new_status: WorkerStatus) -> None:
        if self._status == WorkerStatus.UNHEALTHY and new_status == WorkerStatus.DRAINING:
            raise ValueError("Cannot transition from UNHEALTHY to DRAINING directly")
        self._status = new_status
