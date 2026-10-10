# strategi.py — otak BOT Uno (murni, tanpa I/O) — dari Muse, review Hermes
from collections import Counter


def _bisa(state, kartu):
    if kartu.nilai in ("wild", "wild4"):
        return True
    return kartu.warna == state.warna_aktif or kartu.nilai == state.kartu_atas.nilai


def _warna_terbaik(tangan):
    c = Counter(k.warna for k in tangan if k.warna)
    return c.most_common(1)[0][0] if c else "merah"


def pilih(state, level, rng):
    tangan = state.tangan["BOT"]
    kandidat = [k for k in tangan if _bisa(state, k)]
    if not kandidat:
        return None  # ambil kartu
    lawan_min = min((len(state.tangan[p]) for p in state.pemain if p != "BOT"), default=99)
    if level == 1:
        k = kandidat[0]
    elif level == 2:
        aksi = [k for k in kandidat if k.nilai in ("skip", "reverse", "draw2", "wild4")]
        k = aksi[0] if (lawan_min <= 3 and aksi) else max(
            kandidat, key=lambda x: sum(1 for t in tangan if t.warna == x.warna))
    else:
        terlihat = Counter(state.terlihat)

        def skor(k):
            s = 0
            if k.nilai == "wild4":
                s += 5 if lawan_min <= 2 else -3
            if k.nilai in ("skip", "reverse", "draw2"):
                s += 4 if lawan_min <= 3 else 1
            if k.warna:
                s += sum(1 for t in tangan if t.warna == k.warna)
            s -= terlihat[k]  # kartu yang sudah banyak keluar, nilainya kecil
            return s
        k = max(kandidat, key=skor)
    warna = _warna_terbaik(tangan) if k.nilai in ("wild", "wild4") else None
    return (k, warna)
