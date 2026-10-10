"""Engine UNO murni (tanpa I/O/Telegram) — kolaborasi Hermes x Muse.
Fase 1: aturan inti; tantangan Draw Four & skor = fase 2.
Semua random lewat random.Random(seed) ter-inject -> test deterministik.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

WARNA = ("merah", "kuning", "hijau", "biru")
ANGKA = [str(n) for n in range(10)]
AKSI = ("skip", "reverse", "draw2")
WILD = ("wild", "wild4")


@dataclass(frozen=True)
class Kartu:
    warna: str | None   # salah satu WARNA, atau None untuk wild
    nilai: str          # ANGKA | AKSI | WILD

    def __str__(self) -> str:
        return f"{self.warna or 'wild'}-{self.nilai}"


def deck_standar() -> list[Kartu]:
    d: list[Kartu] = []
    for w in WARNA:
        d.append(Kartu(w, "0"))
        for n in ANGKA[1:]:
            d += [Kartu(w, n), Kartu(w, n)]
        for a in AKSI:
            d += [Kartu(w, a), Kartu(w, a)]
    for _ in range(4):
        d.append(Kartu(None, "wild"))
        d.append(Kartu(None, "wild4"))
    assert len(d) == 108
    return d


class Hasil(Enum):
    OK = "ok"
    TAK_MILIK = "tak_milik"
    TAK_COCOK = "tak_cocok"
    BUKAN_GILIRAN = "bukan_giliran"
    MENANG = "menang"
    AMBIL_OK = "ambil_ok"
    AMBIL_MAIN_OK = "ambil_main_ok"
    PENCETANGAN = "peringatan_uno"


@dataclass
class State:
    pemain: list[str] = field(default_factory=list)
    tangan: dict[str, list[Kartu]] = field(default_factory=dict)
    draw_pile: list[Kartu] = field(default_factory=list)
    discard: list[Kartu] = field(default_factory=list)
    kartu_atas: Kartu | None = None
    warna_aktif: str | None = None
    arah: int = 1
    giliran: int = 0
    fase: str = "lobby"   # lobby | bermain | selesai
    terlihat: set = field(default_factory=set)
    uno_diklaim: set = field(default_factory=set)
    pemenang: str | None = None


class Engine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.state = State()

    # ---- invariant: total kartu di semua lokasi selalu 108 ----
    def total_kartu(self) -> int:
        s = self.state
        n = len(s.draw_pile) + len(s.discard) + (1 if s.kartu_atas else 0)
        n += sum(len(t) for t in s.tangan.values())
        return n

    # ---- lobby ----
    def buat_lobby(self, pemain: list[str]) -> None:
        if len(pemain) < 2:
            raise ValueError("minimal 2 pemain")
        self.state = State(pemain=list(pemain), tangan={p: [] for p in pemain})
        self.state.fase = "lobby"

    def mulai(self) -> None:
        s = self.state
        d = deck_standar()
        self.rng.shuffle(d)
        s.draw_pile = d
        for p in s.pemain:
            s.tangan[p] = [s.draw_pile.pop() for _ in range(7)]
        # buka kartu pertama; wild awal -> pilih warna acak (fase 1)
        while True:
            k = s.draw_pile.pop()
            if k.nilai not in WILD:
                s.kartu_atas, s.warna_aktif = k, k.warna
                break
            s.discard.append(k)   # wild pembuka: masuk discard, coba lagi
        else:
            raise RuntimeError("deck kacau")
        s.terlihat = {s.kartu_atas} | {k for t in s.tangan.values() for k in t}
        s.fase = "bermain"
        s.giliran = 0
        s.arah = 1

    # ---- bantuan ----
    def pemain_giliran(self) -> str:
        return self.state.pemain[self.state.giliran]

    def _lanjut(self, langkah: int = 1) -> None:
        s = self.state
        s.giliran = (s.giliran + s.arah * langkah) % len(s.pemain)

    def bisa_main(self, k: Kartu) -> bool:
        s = self.state
        if k.nilai in WILD:
            return True
        return k.warna == s.warna_aktif or k.nilai == s.kartu_atas.nilai

    def _ambil(self, p: str, n: int) -> list[Kartu]:
        s = self.state
        out = []
        for _ in range(n):
            if not s.draw_pile:
                if not s.discard:
                    raise RuntimeError("habis total")
                # kartu_atas TIDAK ikut refill (dia slot terpisah, bukan isi discard) —
                # taruh dia ke discard = duplikasi fisik (temuan review Muse)
                s.draw_pile = s.discard
                s.discard = []
                self.rng.shuffle(s.draw_pile)
            k = s.draw_pile.pop()
            s.terlihat.add(k)
            s.tangan[p].append(k)
            out.append(k)
        return out

    # ---- aksi ----
    def main_kartu(self, pemain: str, kartu: Kartu, warna_pilihan: str | None = None) -> Hasil:
        s = self.state
        if s.fase != "bermain":
            raise ValueError("belum bermain")
        if pemain != self.pemain_giliran():
            return Hasil.BUKAN_GILIRAN
        if kartu not in s.tangan[pemain]:
            return Hasil.TAK_MILIK
        if not self.bisa_main(kartu):
            return Hasil.TAK_COCOK
        s.tangan[pemain].remove(kartu)
        s.discard.append(s.kartu_atas)
        s.kartu_atas = kartu
        s.warna_aktif = kartu.warna or warna_pilihan or self.rng.choice(list(WARNA))
        s.uno_diklaim.discard(pemain)
        if not s.tangan[pemain]:
            # menang — efek kartu terakhir tidak dieksekusi (aturan umum UNO)
            s.fase = "selesai"
            s.pemenang = pemain
            return Hasil.MENANG
        # efek
        langkah = 1
        if kartu.nilai == "skip":
            langkah = 2
        elif kartu.nilai == "reverse":
            s.arah *= -1
            if len(s.pemain) == 2:
                # Aturan resmi: reverse di 2 pemain = skip → PEMAIN YANG SAMA main lagi.
                # Ganti arah + tetap di pemain ini (langkah 0), lalu arah netral utk 2p:
                # dengan 2 pemain, arah apapun hasilnya selalu "lawan", jadi set arah
                # kembali +1 biar perilaku konsisten.
                s.giliran = s.pemain.index(pemain)
                langkah = 0
                s.arah = 1
        elif kartu.nilai == "draw2":
            target = s.pemain[(s.giliran + s.arah) % len(s.pemain)]
            self._ambil(target, 2)
            langkah = 2
        elif kartu.nilai == "wild4":
            target = s.pemain[(s.giliran + s.arah) % len(s.pemain)]
            self._ambil(target, 4)
            langkah = 2
        self._lanjut(langkah)
        return Hasil.OK

    def ambil(self, pemain: str) -> tuple[Hasil, Kartu | None]:
        s = self.state
        if pemain != self.pemain_giliran():
            return Hasil.BUKAN_GILIRAN, None
        k = self._ambil(pemain, 1)[0]
        if self.bisa_main(k):
            return Hasil.AMBIL_MAIN_OK, k   # boleh langsung main (aturan resmi)
        self._lanjut()
        return Hasil.AMBIL_OK, k

    def uno(self, pemain: str) -> Hasil:
        s = self.state
        if len(s.tangan.get(pemain, [])) == 1:
            s.uno_diklaim.add(pemain)
            return Hasil.OK
        return Hasil.PENCETANGAN  # salah timing

    def cek_uno(self) -> list[str]:
        """Pemain sisa 1 kartu tapi belum klaim UNO (kandidat penalti)."""
        s = self.state
        return [p for p, t in s.tangan.items() if len(t) == 1 and p not in s.uno_diklaim]

    def penalti(self, pemain: str) -> None:
        self._ambil(pemain, 2)
