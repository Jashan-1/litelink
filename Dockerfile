FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY app app
COPY evals evals
COPY migrations migrations
RUN useradd --create-home litelink && mkdir -p evals/data && chown litelink evals/data
USER litelink
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
