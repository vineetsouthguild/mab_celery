from celery import Celery

app = Celery(
    "myproj",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=["tasks"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
)
