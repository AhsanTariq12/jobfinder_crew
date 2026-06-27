.\/.venv\Scripts\activate
celery -A worker.celery_app worker --loglevel=info --pool=solo