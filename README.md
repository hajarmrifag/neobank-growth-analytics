# Neobank Growth & Unit Economics Analytics

Synthetic fintech product analytics project covering acquisition, KYC, activation,
retention, monetisation, unit economics and experimentation.

## Day 1
1. Start PostgreSQL with Docker.
2. Create the schema.
3. Generate synthetic core data.
4. Load it into PostgreSQL.
5. Run validation queries.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
docker compose up -d

docker compose exec -T postgres psql \
  -U neobank_user -d neobank_analytics < sql/00_schema.sql

python src/generate_core_data.py
python src/load_core_data.py

docker compose exec -T postgres psql \
  -U neobank_user -d neobank_analytics < sql/01_validation.sql
```

Do not commit `.env` or generated CSV files.
