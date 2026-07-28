FROM python:latest
LABEL authors="tian"
EXPOSE 8000
# No buffering, no .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Stage 1 Update y Req
#RUN apt-get update
#RUN apt-get install -y libgdal-dev libpq-dev


WORKDIR /app

COPY requirements.txt /app/
RUN python -m pip install --no-cache-dir -r requirements.txt

# Stage 2

COPY nutriapp /app

# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 1000 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "nutriapp.wsgi"]