"""Folyamatlista bejárása szálbiztosan."""
import psutil


def iter_processes(attrs: list[str]):
    """
    (Process, info) párokat ad, ahol az info a hívó saját dict-je.
    A psutil a Process objektumokat globálisan cache-eli, így a `process_iter(attrs)`
    által beállított `proc.info`-t egy másik szál bejárása felülírhatja.
    """
    for proc in psutil.process_iter():
        try:
            yield proc, proc.as_dict(attrs=attrs)
        except psutil.NoSuchProcess:
            continue
