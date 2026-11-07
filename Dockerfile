FROM python:3.13-slim
WORKDIR /srv/portal
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY brand /srv/brand
COPY schema /srv/schema
ENV EBOX_BRAND_DIR=/srv/brand \
    EBOX_SCHEMA=/srv/schema/profile.schema.json \
    EBOX_PROFILES_DIR=/srv/profiles
RUN useradd -r -u 10001 portal && mkdir -p /srv/profiles && chown portal /srv/profiles
USER portal
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
