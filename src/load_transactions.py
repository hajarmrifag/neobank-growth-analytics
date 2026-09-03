from pathlib import Path
import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATA_DIR = Path("data/raw")

TABLE_FILES = [
    ("transactions", "transactions.csv"),
    ("card_transactions", "card_transactions.csv"),
    ("transfers", "transfers.csv"),
    ("fx_transactions", "fx_transactions.csv"),
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
                    fx_transactions,
                    transfers,
                    card_transactions,
                    transactions
                RESTART IDENTITY CASCADE;
                """
            )

            for table_name, filename in TABLE_FILES:
                path = DATA_DIR / filename

                if not path.exists():
                    raise FileNotFoundError(
                        f"Missing {path}. Run generate_transactions.py first."
                    )

                copy_csv(cursor, table_name, path)
                print(f"Loaded {table_name}")

            cursor.execute(
                """
                DELETE FROM product_events
                WHERE event_name IN ('first_funding', 'first_transaction');
                """
            )

            event_path = DATA_DIR / "transaction_events.csv"
            copy_csv(cursor, "product_events", event_path)
            print("Loaded transaction_events into product_events")

        conn.commit()
        print("\nTransaction data loaded successfully.")

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
