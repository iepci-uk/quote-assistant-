"""Import data/processed/price_catalogue.csv into the SQLite database."""

import argparse
from pathlib import Path
import pandas as pd
from src.database import engine, SessionLocal, CatalogueItem, init_db

def import_catalogue(replace: bool = False):
    init_db()
    csv_file = Path("data/processed/price_catalogue.csv")
    if not csv_file.exists():
        return

    session = SessionLocal()
    count = session.query(CatalogueItem).count()
    if count > 0 and not replace:
        session.close()
        return

    if count > 0 and replace:
        session.query(CatalogueItem).delete()
        session.commit()
    session.close()

    df = pd.read_csv(csv_file)

    # Clean text columns
    df["part_code_key"] = df["part_code_key"].fillna("").astype(str)
    df["supplier"] = df["supplier"].fillna("Unknown").astype(str)
    df["part_code"] = df["part_code"].fillna("").astype(str)

    df.to_sql("catalogue_items", con=engine, if_exists="append", index=False, chunksize=1000)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import CSV catalogue into SQLite database.")
    parser.add_argument("--replace", action="store_true", help="Replace existing catalogue items.")
    args = parser.parse_args()
    import_catalogue(replace=args.replace)