"""Háttérmunka a Qt szálkészletén; az eredmény jelzéssel (Signal) érkezik vissza a GUI-szálra."""
import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)
_running: set["_Task"] = set()  # a Python-oldali hivatkozás nélkül a feladat idő előtt felszabadulna


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float)


class _Task(QRunnable):
    def __init__(self, work: Callable, with_progress: bool):
        super().__init__()
        self.work = work
        self.with_progress = with_progress
        # A GUI-szálon jön létre, így a jelzései a GUI-szálon futtatják a fogadókat
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.work(self.signals.progress.emit) if self.with_progress else self.work()
        except Exception as e:
            log.exception("Háttérfeladat hiba")
            self._emit(self.signals.failed, str(e))
            return
        self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # az ablak közben bezárult, nincs kinek jelezni


def run_task(work: Callable, done: Callable | None = None, failed: Callable[[str], None] | None = None,
             progress: Callable[[float], None] | None = None) -> None:
    """`work` a szálkészleten fut; `progress` megadásakor a work egy progress(float) függvényt kap."""
    task = _Task(work, progress is not None)
    _running.add(task)
    task.signals.done.connect(lambda _: _running.discard(task))
    task.signals.failed.connect(lambda _: _running.discard(task))
    if done:
        task.signals.done.connect(done)
    if failed:
        task.signals.failed.connect(failed)
    if progress:
        task.signals.progress.connect(progress)
    QThreadPool.globalInstance().start(task)
