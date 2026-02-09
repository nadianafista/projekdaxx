def scrape_gmaps(query):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import pandas as pd
    import time, re, os

    # =====================
    # LOAD DATASET WILAYAH
    # =====================
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    wilayah_path = os.path.join(BASE_DIR, "daerah_indo.xlsx")

    wilayah_df = pd.read_excel(wilayah_path)
    wilayah_df = wilayah_df.astype(str).apply(
        lambda c: c.str.lower().str.strip()
    )

    WILAYAH_KATA = {
        w for w in wilayah_df.values.flatten()
        if w and w != "nan"
    }

    # =====================
    # TEXT UTIL
    # =====================
    def normalize(text):
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def clean_text(text):
        if not text:
            return ""
        text = str(text)
        text = re.sub(r"[\ue000-\uf8ff]", "", text)
        text = text.replace("\n", " ")
        return re.sub(r"\s+", " ", text).strip()

    # =====================
    # 📍 PARSE LAT LNG (BARU)
    # =====================
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

    # =====================
    # INSERT AKTIVITAS
    # =====================
    def infer_aktivitas_from_nama(nama):
        if not nama:
            return "-"

        text = nama.lower()

        def has(*keys):
            return any(k in text for k in keys)

        if has("tpfi", "dinas", "dkp", "dkpp"):
            return "Badan kepengurusan kelautan dan perikanan"

        if has("rph", "hewan", "jagal"):
            return "Mengelola rumah potong hewan (Sapi, Kambing dkk)"

        if has("rpa", "ayam"):
            return "Mengelola rumah potong ayam"

        if has("tpi"):
            return "Tempat pelelangan ikan"

        if has("beku", "frozen"):
            return "Mengelola makanan frozen food"

        if has("cream", "krim"):
            return "Mengelola dan pembuatan es cream"

        if has("tea", "teh", "dung", "kepal", "puter", "putar", "wawan", "dawet"):
            return "Mengelola minuman dingin"

        if has("kristal", "crystal", "tube", "balok", "batu", "dry", "pabrik es"):
            if "agen" in text:
                return "Agen pengelola dan pembuatan es"
            return "Mengelola dan pembuatan es"

        if has("ikan", "kakap", "perikanan", "fish", "segar", "tuna", "laut", "lautan", "tambak"):
            if "supplier" in text:
                return "Supplier pengelola ikan"
            return "Mengelola ikan"

        if has("food", "bakar", "seafood"):
            return "Mengelola makanan"

        return "-"

    # =====================
    # ADMIN ADDRESS
    # =====================
    def extract_admin_part(alamat):
        if not alamat:
            return ""
        text = alamat.lower()
        pola = r"(kec\.?|kecamatan|kab\.?|kabupaten|kota|city|regency)\b.*"
        m = re.search(pola, text)
        return normalize(m.group(0)) if m else normalize(text)

    # =====================
    # 🔥 FALLBACK WILAYAH
    # =====================
    def infer_wilayah_from_address(alamat):
        if not alamat:
            return "Unknown"

        text = alamat.lower()

        blacklist = [
            "jl", "jalan", "raya", "gg", "gang",
            "blok", "no", "nomor", "perum", "perumnas"
        ]

        def clean(w):
            return re.sub(r"\s+", " ", w).strip().title()

        def valid(w):
            return len(w) >= 4 and not any(b in w.lower() for b in blacklist)

        m = re.search(r"\b(kabupaten|kab\.?|kota)\b\s+([a-z\s]+)", text)
        if m:
            wilayah = clean(m.group(2))
            if valid(wilayah):
                return wilayah

        m = re.search(r"\b(kec\.?|kecamatan)\b\s+([a-z\s]+)", text)
        if m:
            wilayah = clean(m.group(2))
            if valid(wilayah):
                return wilayah

        m = re.search(r"([a-z\s]+)\s+(city|regency)", text)
        if m:
            wilayah = clean(m.group(1))
            if valid(wilayah):
                return wilayah

        for w in sorted(WILAYAH_KATA, key=len, reverse=True):
            if w in text:
                return w.title()

        return "Unknown"

    # =====================
    # PHONE
    # =====================
    def extract_phone(driver):
        try:
            btn = driver.find_element(
                By.XPATH,
                '//button[contains(@aria-label,"Telepon") or '
                'contains(@aria-label,"Phone") or '
                'contains(@data-item-id,"phone")]'
            )
            text = btn.text or btn.get_attribute("aria-label") or ""
            m = re.search(r"(\+?\d[\d\s\-()]{7,})", text)
            return re.sub(r"[^\d+]", "", m.group(1)) if m else "-"
        except:
            return "-"

    # =====================
    # EXPAND QUERY
    # =====================
    def expand_query(q):
        q = q.lower().strip()
        variants = {q}
        terms = ["perusahaan", "pabrik", "industri"]

        for t in terms:
            if t in q:
                for r in terms:
                    if r != t:
                        variants.add(q.replace(t, r))
        return list(variants)

    # =====================
    # TARGET WILAYAH
    # =====================
    query_norm = normalize(query)
    target_wilayah = sorted(
        [w for w in WILAYAH_KATA if w in query_norm],
        key=len,
        reverse=True
    )

    # =====================
    # DRIVER
    # =====================
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=id-ID")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)

    rows = []

    # =====================
    # SCRAPE
    # =====================
    for q in expand_query(query):
        driver.get(f"https://www.google.com/maps/search/{q}")
        time.sleep(5)

        try:
            feed = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div.m6QErb[aria-label]')
                )
            )
        except:
            continue

        last = 0
        while True:
            cards = driver.find_elements(
                By.XPATH, '//div[contains(@class,"Nv2PK")]'
            )
            if len(cards) == last:
                break
            last = len(cards)
            driver.execute_script(
                "arguments[0].scrollBy(0, arguments[0].scrollHeight)", feed
            )
            time.sleep(1.2)

        links = {
            a.get_attribute("href")
            for a in driver.find_elements(
                By.XPATH, '//a[contains(@href,"/place/")]'
            )
            if a.get_attribute("href")
        }

        for link in links:
            driver.get(link)

            try:
                wait.until(
                    EC.presence_of_element_located((By.XPATH, "//h1"))
                )
            except:
                continue

            nama = clean_text(
                driver.find_element(By.XPATH, "//h1").text
            )

            try:
                alamat = clean_text(
                    driver.find_element(
                        By.XPATH,
                        '//button[contains(@aria-label,"Alamat") or '
                        'contains(@aria-label,"Address")]'
                    ).text
                )
            except:
                alamat = ""

            lat, lng = extract_lat_lng(link)

            rows.append({
                "nama": nama,
                "alamat": alamat,
                "admin": extract_admin_part(alamat),
                "no_telp": extract_phone(driver),
                "aktivitas": infer_aktivitas_from_nama(nama),
                "link_maps": link,
                "lat": lat,
                "lng": lng
            })

    driver.quit()

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["nama", "alamat"]
    )

    # 🔥 FILTER DATA TANPA KOORDINAT
    df = df.dropna(subset=["lat", "lng"])

    # =====================
    # FINAL FILTER WILAYAH
    # =====================
    if target_wilayah:
        df_f = df[
            df["admin"].apply(
                lambda x: any(w in x for w in target_wilayah)
            )
        ]

        if not df_f.empty:
            df = df_f.copy()
            df["wilayah"] = target_wilayah[0].title()
        else:
            df["wilayah"] = target_wilayah[0].title()
    else:
        df["wilayah"] = df["alamat"].apply(
            infer_wilayah_from_address
        )

    return (
        df.drop(columns=["admin"])
        .reset_index(drop=True)
        .to_dict(orient="records")
    )