from pathlib import Path
import pandas as pd

src = Path("data/rawdomains/coi/data.csv")
out = Path("data/rawdomains/coi/data_sd_county_only.csv")

df = pd.read_csv(src, dtype=str)

# safest filter
sd = df[df["county_fips"].astype(str).str.zfill(5) == "06073"].copy()

sd.to_csv(out, index=False)

print("Saved:", out)
print("Rows:", len(sd))
print(sd[["county_name", "county_fips", "year"]].drop_duplicates().head())