import pandas as pd
import re

REQUIRED_COLUMNS = [
    "nama", "alamat", "wilayah",
    "no_telp", "aktivitas", "link_maps"
]

COLUMN_ALIASES = {
    "nama perusahaan": "nama",
    "nama": "nama",
    "alamat": "alamat",
    "wilayah": "wilayah",
    "no telepon": "no_telp",
    "no telpon": "no_telp",
    "telepon": "no_telp",
    "nomor telepon": "no_telp",
    "aktivitas": "aktivitas",
    "link google maps": "link_maps",
    "google maps": "link_maps",
    "link maps": "link_maps",
    "link": "link_maps",
    "latitude": "lat",
    "longitude": "lng",
    "long": "lng"
}

def normalize_column(col):
    return COLUMN_ALIASES.get(
        str(col).strip().lower(),
        str(col).strip().lower()
    )

def extract_lat_lng(link):
    if not isinstance(link, str):
        return None, None

    patterns = [
        r'@(-?\d+\.\d+),(-?\d+\.\d+)',      
        r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',  
        r'!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)'   
    ]

    for p in patterns:
        m = re.search(p, link)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if abs(lat) <= 90 and abs(lng) <= 180:
                return lat, lng

    return None, None
def validate_excel(file_path):
    try:
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path, dtype=str)
        else:
            df = pd.read_excel(
                file_path,
                engine="openpyxl",
                dtype=str
            )

        df.columns = [normalize_column(c) for c in df.columns]
        missing_columns = [
            c for c in REQUIRED_COLUMNS
            if c not in df.columns
        ]

        if missing_columns:
            return {
                "status": "error",
                "missing_columns": missing_columns,
                "found_columns": list(df.columns)
            }

        if "lat" not in df.columns or "lng" not in df.columns:
            df["lat"], df["lng"] = zip(
                *df["link_maps"].apply(extract_lat_lng)
            )
        else:
            df["lat"] = pd.to_numeric(
                df["lat"], errors="coerce"
            )
            df["lng"] = pd.to_numeric(
                df["lng"], errors="coerce"
            )

        df = df.dropna(subset=["lat", "lng"])

        return {
            "status": "success",
            "columns": list(df.columns),
            "total_rows": len(df),
            "preview": df.head(5).to_dict(
                orient="records"
            )
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Gagal membaca file: {str(e)}"
        }
