"""Background work. One worker process built from the same image as the API (Celery + Redis).
With TASKS_EAGER=true tasks run inline, which is what tests and single-process setups use."""
from celery import Celery
from celery.schedules import crontab

from .config import get_settings
from .db import session_factory

settings = get_settings()
celery = Celery("talentmatch", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_always_eager=settings.tasks_eager, task_acks_late=True, worker_prefetch_multiplier=1,
    task_default_queue="scoring", timezone="UTC", broker_connection_retry_on_startup=True,
    task_routes={"app.tasks.alerts": {"queue": "low"}, "app.tasks.rescore": {"queue": "low"}},
    beat_schedule={
        "pending-rejections": {"task": "app.tasks.pending_rejections", "schedule": 60.0},
        "retention-purge": {"task": "app.tasks.retention", "schedule": crontab(hour=3, minute=17)},
        "job-alerts": {"task": "app.tasks.alerts", "schedule": crontab(day_of_week=1, hour=7, minute=40)},
    },
)


def _run(fn, *args):
    with session_factory()() as db:
        try:
            out = fn(db, *args)
            db.commit()
            return out
        except Exception:
            db.rollback()
            raise


@celery.task(name="app.tasks.process", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process(application_id: str):
    from .services import process_application
    _run(process_application, application_id)


@celery.task(name="app.tasks.rescore")
def rescore(job_id: str):
    from .services import rescore_job
    return _run(rescore_job, job_id)


@celery.task(name="app.tasks.pending_rejections")
def pending_rejections():
    from .services import send_pending_rejections
    return _run(send_pending_rejections)


@celery.task(name="app.tasks.retention")
def retention():
    from .services import purge_retention
    return _run(purge_retention)


@celery.task(name="app.tasks.alerts")
def alerts():
    from .matching import send_job_alerts
    return _run(send_job_alerts)


def enqueue(task, *args) -> None:
    """Queue a task; if the broker is unreachable, run it inline rather than lose the work."""
    try:
        task.delay(*args)
    except Exception:
        task.apply(args=args)
