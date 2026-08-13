#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFI-OS · Trình đồng bộ tự động
Kéo số từ Google Ads + các nét affiliate → xuất afi-data.json cho dashboard đọc.

CHẠY THỬ (không cần token, dùng số giả để kiểm đường ống):
    python3 afi_sync.py --demo

CHẠY THẬT:
    pip install google-ads requests
    python3 afi_sync.py

CHẠY TỰ ĐỘNG MỖI SÁNG 7H (Linux/Mac):
    crontab -e
    0 7 * * *  cd /duong/dan/toi/sync && /usr/bin/python3 afi_sync.py >> sync.log 2>&1
"""
import os, sys, json, csv, glob, argparse
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "afi-data.json")
CFG  = os.path.join(HERE, "config.json")

# ============================================================
#  CẤU HÌNH MẪU — chạy lần đầu sẽ tự sinh config.json
# ============================================================
CONFIG_MAU = {
  "so_ngay_keo_ve": 30,

  "google_ads": {
    "bat": False,
    "_huong_dan": [
      "0. API Center CHỈ có trong tài khoản Người quản lý (MCC). Tài khoản Ads thường không thấy.",
      "   Tạo MCC miễn phí: ads.google.com/home/tools/manager-accounts",
      "   Rồi liên kết các tài khoản Ads con vào MCC (gửi lời mời từ MCC, vào acc con bấm Chấp nhận).",
      "1. Vào https://ads.google.com/aw/apicenter bằng đúng tài khoản MCC > điền form > nhận token.",
      "   Mặc định được Explorer Access — đủ để ĐỌC báo cáo hằng ngày, không phải chờ duyệt.",
      "2. Google Cloud Console: tạo project > bật Google Ads API > tạo OAuth Client (Desktop)",
      "3. Lấy refresh_token bằng công cụ oauth của thư viện google-ads",
      "4. Điền vào đây rồi đổi 'bat' thành true",
      "LƯU Ý: chỉ kéo được số của tài khoản ĐÃ liên kết vào MCC ghi ở login_customer_id."
    ],
    "developer_token": "",
    "client_id": "",
    "client_secret": "",
    "refresh_token": "",
    "login_customer_id": "",            # ID tài khoản MCC, bỏ dấu gạch ngang
    "customer_ids": []                  # danh sách ID tài khoản con, bỏ dấu gạch ngang
  },

  "nets": [
    {"ten": "Impact", "loai": "impact", "bat": False,
     "account_sid": "", "auth_token": "",
     "_huong_dan": "Impact > Settings > API Access > lấy Account SID và Auth Token"},

    {"ten": "PartnerStack", "loai": "partnerstack", "bat": False,
     "api_key": "", "api_secret": "",
     "_huong_dan": "PartnerStack > Settings > Integrations > API keys"},

    {"ten": "Rewardful", "loai": "rewardful", "bat": False,
     "api_secret": "",
     "_huong_dan": "Rewardful > Settings > API — dùng cho Pictory, Mubert, Heartbeat, Speechify"},

    {"ten": "CSV thu cong", "loai": "csv", "bat": True,
     "thu_muc": "csv_nets",
     "_huong_dan": [
       "Nét nào không có API thì xuất báo cáo ra CSV rồi bỏ vào thư mục này.",
       "Cần 3 cột, tên cột nhận cả tiếng Việt lẫn tiếng Anh:",
       "  subid / sub_id / gclid   |   date / ngay   |   commission / amount / hoa hong",
       "Tên file chính là tên dự án. Ví dụ: Pictory.csv"
     ]}
  ]
}

def nap_config():
    if not os.path.exists(CFG):
        json.dump(CONFIG_MAU, open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"→ Đã tạo {CFG}. Mở ra điền thông tin rồi chạy lại.")
        print("→ Muốn xem thử đường ống trước thì chạy:  python3 afi_sync.py --demo")
        sys.exit(0)
    return json.load(open(CFG, encoding="utf-8"))


# ============================================================
#  GOOGLE ADS
# ============================================================
GAQL = """
SELECT
  campaign.name, campaign.status, campaign.id,
  segments.date,
  metrics.impressions, metrics.clicks, metrics.cost_micros,
  metrics.conversions, metrics.conversions_value,
  metrics.search_impression_share,
  metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share
FROM campaign
WHERE segments.date BETWEEN '{tu}' AND '{den}'
  AND campaign.status != 'REMOVED'
"""

def keo_google_ads(cfg):
    g = cfg["google_ads"]
    if not g.get("bat"):
        print("· Google Ads: tắt")
        return [], []
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("✗ Chưa cài thư viện. Chạy:  pip install google-ads")
        return [], []

    client = GoogleAdsClient.load_from_dict({
        "developer_token": g["developer_token"],
        "client_id":       g["client_id"],
        "client_secret":   g["client_secret"],
        "refresh_token":   g["refresh_token"],
        "login_customer_id": g["login_customer_id"],
        "use_proto_plus": True,
    })
    svc = client.get_service("GoogleAdsService")
    den = datetime.now().date()
    tu  = den - timedelta(days=cfg.get("so_ngay_keo_ve", 30))
    q = GAQL.format(tu=tu.isoformat(), den=den.isoformat())

    rows, accs = [], []
    for cid in g.get("customer_ids", []):
        cid = str(cid).replace("-", "")
        try:
            n = 0
            for batch in svc.search_stream(customer_id=cid, query=q):
                for r in batch.results:
                    rows.append({
                        "date": r.segments.date,
                        "acc":  cid,
                        "camp": r.campaign.name,
                        "proj": doan_du_an(r.campaign.name),
                        "imp":  int(r.metrics.impressions),
                        "clk":  int(r.metrics.clicks),
                        "cost": round(r.metrics.cost_micros / 1_000_000, 4),
                        "conv": float(r.metrics.conversions),
                        "is":       round(float(r.metrics.search_impression_share or 0) * 100, 1),
                        "lost_bud": round(float(r.metrics.search_budget_lost_impression_share or 0) * 100, 1),
                        "lost_rank":round(float(r.metrics.search_rank_lost_impression_share or 0) * 100, 1),
                    })
                    n += 1
            accs.append({"id": cid, "ok": True, "dong": n})
            print(f"✓ Google Ads {cid}: {n} dòng")
        except Exception as e:
            accs.append({"id": cid, "ok": False, "loi": str(e)[:200]})
            print(f"✗ Google Ads {cid}: {str(e)[:150]}")
    return rows, accs


def doan_du_an(ten_camp):
    """'(c) US - MerlinAI | 2026-08-15'  →  'MerlinAI'"""
    import re
    s = re.sub(r"^\([a-dA-D]\)\s*", "", ten_camp).split("|")[0]
    p = re.split(r"\s+-\s+", s)
    return (p[-1] if len(p) > 1 else p[0]).strip()[:32] or ten_camp[:32]


# ============================================================
#  CÁC NÉT AFFILIATE
# ============================================================
def _req():
    try:
        import requests
        return requests
    except ImportError:
        print("✗ Chưa cài thư viện. Chạy:  pip install requests")
        return None

def keo_impact(n, tu, den):
    rq = _req()
    if not rq: return []
    url = f"https://api.impact.com/Mediapartners/{n['account_sid']}/Actions"
    out = []
    try:
        r = rq.get(url, auth=(n["account_sid"], n["auth_token"]),
                   params={"StartDate": tu, "EndDate": den, "PageSize": 1000},
                   headers={"Accept": "application/json"}, timeout=45)
        r.raise_for_status()
        for a in r.json().get("Actions", []):
            out.append({
                "net": n["ten"],
                "proj": a.get("CampaignName") or a.get("Campaign") or n["ten"],
                "subid": a.get("SubId1") or "",
                "date": (a.get("EventDate") or "")[:10],
                "amount": float(a.get("Payout") or 0),
                "status": (a.get("State") or "").lower(),
            })
    except Exception as e:
        print(f"✗ {n['ten']}: {str(e)[:150]}")
    return out

def keo_partnerstack(n, tu, den):
    rq = _req()
    if not rq: return []
    out = []
    try:
        r = rq.get("https://api.partnerstack.com/api/v2/transactions",
                   auth=(n["api_key"], n["api_secret"]),
                   params={"min_created": tu, "max_created": den, "limit": 1000}, timeout=45)
        r.raise_for_status()
        for t in r.json().get("data", {}).get("items", []):
            out.append({
                "net": n["ten"],
                "proj": (t.get("group") or {}).get("name") or n["ten"],
                "subid": t.get("customer_key") or "",
                "date": str(t.get("created", ""))[:10],
                "amount": float(t.get("amount", 0)) / 100.0,
                "status": (t.get("status") or "").lower(),
            })
    except Exception as e:
        print(f"✗ {n['ten']}: {str(e)[:150]}")
    return out

def keo_rewardful(n, tu, den):
    rq = _req()
    if not rq: return []
    out = []
    try:
        r = rq.get("https://api.getrewardful.com/v1/commissions",
                   auth=(n["api_secret"], ""), params={"limit": 100}, timeout=45)
        r.raise_for_status()
        for c in r.json().get("data", []):
            sale = c.get("sale") or {}
            out.append({
                "net": n["ten"],
                "proj": ((c.get("campaign") or {}).get("name")) or n["ten"],
                "subid": (sale.get("referral") or {}).get("id", ""),
                "date": str(c.get("created_at", ""))[:10],
                "amount": float(c.get("amount", 0)) / 100.0,
                "status": "paid" if c.get("paid_at") else "pending",
            })
    except Exception as e:
        print(f"✗ {n['ten']}: {str(e)[:150]}")
    return out

COT = {
    "subid":  ["subid", "sub_id", "sub id", "gclid", "click id", "s1"],
    "date":   ["date", "ngay", "ngày", "created", "event date", "conversion time"],
    "amount": ["commission", "amount", "payout", "hoa hong", "hoa hồng", "earnings", "revenue"],
    "status": ["status", "state", "trang thai", "trạng thái"],
}
def keo_csv(n, tu, den):
    thu_muc = os.path.join(HERE, n.get("thu_muc", "csv_nets"))
    os.makedirs(thu_muc, exist_ok=True)
    out = []
    for f in glob.glob(os.path.join(thu_muc, "*.csv")):
        du_an = os.path.splitext(os.path.basename(f))[0]
        try:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rd = csv.DictReader(fh)
                idx = {}
                for k, alias in COT.items():
                    for h in (rd.fieldnames or []):
                        if h and h.strip().lower() in alias:
                            idx[k] = h; break
                for row in rd:
                    if "amount" not in idx: continue
                    raw = str(row.get(idx["amount"], "0"))
                    val = "".join(ch for ch in raw if ch.isdigit() or ch in ".-")
                    out.append({
                        "net": n["ten"], "proj": du_an,
                        "subid": row.get(idx.get("subid", ""), "") or "",
                        "date": str(row.get(idx.get("date", ""), ""))[:10],
                        "amount": float(val or 0),
                        "status": (row.get(idx.get("status", ""), "") or "approved").lower(),
                    })
            print(f"✓ CSV {du_an}: {len(out)} dòng cộng dồn")
        except Exception as e:
            print(f"✗ CSV {f}: {str(e)[:120]}")
    return out

def keo_nap():
    """
    Sổ nạp tiền vào tài khoản Ads.
    Google Ads API KHÔNG trả số dư thẻ trả trước, nên đây là nguồn bán tự động:
    Google Ads > Thanh toán > Giao dịch > Tải xuống  →  lưu vào thư mục nap/
    Tên file = tên tài khoản (vd: nap/1234567890.csv). Chạy sync là nó tự đọc.
    Cột nhận: ngày/date · số tiền/amount/tổng · mô tả/description.
    """
    thu_muc = os.path.join(HERE, "nap")
    os.makedirs(thu_muc, exist_ok=True)
    ngay_a = ("ngày", "ngay", "date", "transaction date")
    tien_a = ("số tiền", "so tien", "amount", "tổng", "tong", "total")
    ghi_a  = ("mô tả", "mo ta", "description", "loại", "type")
    out = []
    for f in glob.glob(os.path.join(thu_muc, "*.csv")):
        acc = os.path.splitext(os.path.basename(f))[0]
        try:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rd = csv.DictReader(fh)
                cot = {}
                for h in (rd.fieldnames or []):
                    hl = (h or "").strip().lower()
                    if hl in ngay_a: cot["date"] = h
                    elif hl in tien_a: cot["amt"] = h
                    elif hl in ghi_a: cot["note"] = h
                if "amt" not in cot: continue
                for row in rd:
                    raw = str(row.get(cot["amt"], "0"))
                    val = "".join(ch for ch in raw if ch.isdigit() or ch in ".-")
                    try: so = float(val or 0)
                    except ValueError: continue
                    # chỉ lấy khoản NẠP VÀO (dương), bỏ dòng trừ tiền quảng cáo
                    if so <= 0: continue
                    ghi = str(row.get(cot.get("note", ""), "") or "")
                    if any(k in ghi.lower() for k in ("chi phí", "cost", "spend", "quảng cáo")): continue
                    out.append({"date": str(row.get(cot.get("date", ""), ""))[:10],
                                "acc": acc, "amt": round(so, 2), "note": ghi[:60] or "nạp"})
            print(f"✓ Nạp {acc}: {len([o for o in out if o['acc']==acc])} lần")
        except Exception as e:
            print(f"✗ Nạp {f}: {str(e)[:120]}")
    return out


KEO = {"impact": keo_impact, "partnerstack": keo_partnerstack,
       "rewardful": keo_rewardful, "csv": keo_csv}

def keo_cac_net(cfg):
    den = datetime.now().date()
    tu  = den - timedelta(days=cfg.get("so_ngay_keo_ve", 30))
    tat_ca, trang_thai = [], []
    for n in cfg.get("nets", []):
        if not n.get("bat"):
            print(f"· {n['ten']}: tắt"); continue
        fn = KEO.get(n.get("loai"))
        if not fn:
            print(f"? {n['ten']}: chưa hỗ trợ loại '{n.get('loai')}'"); continue
        rows = fn(n, tu.isoformat(), den.isoformat())
        tat_ca += rows
        trang_thai.append({"ten": n["ten"], "loai": n["loai"], "dong": len(rows)})
        if n.get("loai") != "csv":
            print(f"✓ {n['ten']}: {len(rows)} giao dịch")
    return tat_ca, trang_thai


# ============================================================
#  GHÉP & XUẤT
# ============================================================
def tong_hop(ads_rows, hoa_hong):
    """Ghép doanh thu về từng CAMP qua gclid trong SubID. Không khớp thì gom về dự án."""
    gclid_camp = {}   # điền dần khi có bảng gclid→camp; hiện ghép theo tên dự án
    theo_camp, theo_du_an = {}, {}
    for h in hoa_hong:
        tien = h["amount"]
        key = gclid_camp.get(h["subid"])
        if key:
            theo_camp[key] = theo_camp.get(key, 0) + tien
        else:
            p = h["proj"]
            d = theo_du_an.setdefault(p, {"pend": 0, "appr": 0, "rej": 0, "paid": 0, "net": h["net"]})
            st = h["status"]
            if   "paid" in st or "đã trả" in st: d["paid"] += tien
            elif "rej" in st or "declin" in st or "void" in st: d["rej"] += tien
            elif "appr" in st or "lock" in st or "confirm" in st: d["appr"] += tien
            else: d["pend"] += tien
    return theo_camp, theo_du_an

def xuat(ads_rows, ads_accs, hoa_hong, net_tt):
    theo_camp, theo_du_an = tong_hop(ads_rows, hoa_hong)
    data = {
        "v": 3,
        "cap_nhat_luc": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "ROWS": ads_rows,
        "META": {p: {k: round(v, 2) for k, v in d.items() if k != "net"} | {"net": d["net"]}
                 for p, d in theo_du_an.items()},
        "CAMPREV": {k: round(v, 2) for k, v in theo_camp.items()},
        "DEPOSITS": keo_nap(),
        "nguon": {"google_ads": ads_accs, "nets": net_tt},
        "thong_ke": {
            "so_dong_ads": len(ads_rows),
            "so_camp": len({r["camp"] for r in ads_rows}),
            "so_tai_khoan": len({r["acc"] for r in ads_rows}),
            "chi_phi": round(sum(r["cost"] for r in ads_rows), 2),
            "so_giao_dich": len(hoa_hong),
            "hoa_hong": round(sum(h["amount"] for h in hoa_hong), 2),
        },
    }
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    t = data["thong_ke"]
    print("\n" + "─" * 58)
    print(f"✓ Đã ghi {OUT}")
    print(f"  {t['so_dong_ads']} dòng · {t['so_camp']} camp · {t['so_tai_khoan']} tài khoản")
    print(f"  Chi phí {t['chi_phi']:,.2f}  ·  Hoa hồng {t['hoa_hong']:,.2f}  ·  "
          f"Lãi {t['hoa_hong'] - t['chi_phi']:,.2f}")
    print("─" * 58)
    print("Mở AFI-OS → tầng ⑤ → dán đường dẫn file này vào ô 'Nguồn tự động'.")


def demo():
    import random
    random.seed(7)
    du_an = [("Pictory", 0.55), ("Skool", 1.7), ("Magiclight", 1.9), ("Whop", 1.25)]
    rows, hh = [], []
    den = datetime.now().date()
    for i, (p, ty) in enumerate(du_an):
        acc = f"{1234567890 + i}"
        tong = 0
        for c in range(1, 4):
            base = 1.2 + random.random() * 2
            for d in range(14):
                ngay = (den - timedelta(days=13 - d)).isoformat()
                chi = round(base * (0.75 + random.random() * 0.6), 2)
                tong += chi
                rows.append({"date": ngay, "acc": acc, "camp": f"(b) US - {p} #{c}",
                             "proj": p, "imp": int(chi / 0.0024), "clk": int(chi / 0.073),
                             "cost": chi, "conv": 0, "is": round(40 + random.random() * 40, 1),
                             "lost_bud": round(random.random() * 25, 1),
                             "lost_rank": round(random.random() * 35, 1)})
        for k in range(int(tong * ty / 40) + 1):
            hh.append({"net": "Demo", "proj": p, "subid": f"gclid_demo_{i}_{k}",
                       "date": (den - timedelta(days=random.randint(0, 13))).isoformat(),
                       "amount": 40.0,
                       "status": random.choice(["pending", "approved", "approved", "paid", "rejected"])})
    xuat(rows, [{"id": "demo", "ok": True, "dong": len(rows)}], hh,
         [{"ten": "Demo", "loai": "demo", "dong": len(hh)}])


def chay_mot_lan(demo_mode=False):
    """Chạy trọn một vòng kéo số. Trả về True nếu ghi được file."""
    try:
        if demo_mode:
            demo()
        else:
            cfg = nap_config()
            ads_rows, ads_accs = keo_google_ads(cfg)
            hoa_hong, net_tt = keo_cac_net(cfg)
            if not ads_rows and not hoa_hong:
                print("\n⚠ Chưa kéo được gì. Kiểm tra config.json — mọi nguồn đang tắt?")
            xuat(ads_rows, ads_accs, hoa_hong, net_tt)
        return True
    except Exception as e:
        print(f"✕ Vòng kéo số lỗi: {e}")
        return False


def phuc_vu(port, moi_phut, demo_mode=False):
    """
    Một lệnh duy nhất: tự kéo số theo chu kỳ + mở web ngay tại máy.
    Mở http://localhost:<port>/afi-os.html — dashboard đọc afi-data.json cùng thư mục,
    không cần kéo thả, không dính CORS.
    """
    import http.server, socketserver, threading, time, shutil

    # đưa afi-os.html vào cùng thư mục để cùng gốc với afi-data.json
    for ten in ("afi-os.html",):
        nguon = os.path.join(os.path.dirname(HERE), ten)
        dich = os.path.join(HERE, ten)
        if os.path.exists(nguon) and not os.path.samefile(os.path.dirname(nguon), HERE):
            try:
                if not os.path.exists(dich) or os.path.getmtime(nguon) > os.path.getmtime(dich):
                    shutil.copy2(nguon, dich)
            except Exception:
                pass

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=HERE, **k)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

    def vong_lap():
        while True:
            time.sleep(max(60, moi_phut * 60))
            print(f"\n↻ Kéo số lại · {datetime.now():%H:%M}")
            chay_mot_lan(demo_mode)

    chay_mot_lan(demo_mode)
    threading.Thread(target=vong_lap, daemon=True).start()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), H) as srv:
        print("\n" + "═" * 58)
        print(f"  ĐANG CHẠY · tự kéo số lại mỗi {moi_phut} phút")
        print(f"  Mở trình duyệt:  http://localhost:{port}/afi-os.html")
        print(f"  Nguồn tự động :  afi-data.json   (điền sẵn, khỏi sửa)")
        print("  Dừng: Ctrl+C")
        print("═" * 58)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nĐã dừng.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="chạy thử bằng số giả")
    ap.add_argument("--serve", action="store_true",
                    help="chạy nền: tự kéo số theo chu kỳ + mở dashboard tại localhost")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--moi", type=int, default=60, help="số phút giữa hai lần kéo (mặc định 60)")
    a = ap.parse_args()
    print(f"AFI-OS sync · {datetime.now():%Y-%m-%d %H:%M}")
    if a.serve:
        phuc_vu(a.port, a.moi, a.demo)
    else:
        chay_mot_lan(a.demo)
