from pathlib import Path
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data/raw")

TABLE_FILES = [
    ("customers", "customers.csv"),
    ("kyc_cases", "kyc_cases.csv"),
    ("accounts", "accounts.csv"),
    ("marketing_spend", "marketing_spend.csv"),
    ("experiment_assignments", "experiment_assignments.csv"),
    ("product_events", "product_events.csv"),
]


def connect():
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def copy_csv(cursor, table_name: str, csv_path: Path) -> None:
    with csv_path.open("r", encoding="utf-8") as handle:
        with cursor.copy(
            f"""
            COPY {table_name}
            FROM STDIN
            WITH (FORMAT CSV, HEADER TRUE, NULL '');
            """
        ) as copy:
            while data := handle.read(8192):
                copy.write(data)


def main() -> None:
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE
                    product_events,
                    experiment_assignments,
                    marketing_spend,
                    accounts,
                    kyc_cases,
                    customers
                CASCADE;
                """
            )

            for table_name, filename in TABLE_FILES:
                path = DATA_DIR / filename
                if not path.exists():
                    raise FileNotFoundError(
                        f"Missing {path}. Run generate_core_data.py first."
                    )
                copy_csv(cursor, table_name, path)
                print(f"Loaded {table_name}")

        conn.commit()
        print("\nCore Day 1 data loaded successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
