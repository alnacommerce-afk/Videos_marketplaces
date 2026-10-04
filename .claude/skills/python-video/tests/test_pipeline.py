"""Testes do pipeline python-video.

  python tests/test_pipeline.py            # tudo (renderiza vídeos reais; ~3–5 min)
  python tests/test_pipeline.py --fast     # só testes rápidos (sem render)

Nenhum teste usa a internet nem credenciais: a loja é simulada por um servidor HTTP local, e a locução
do ElevenLabs por uma voz sintética falsa (só para exercitar ducking/retime/sincronia).
"""
from __future__ import annotations

import copy
import http.server
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import numpy as np  # noqa: E402

FAST = "--fast" in sys.argv
if FAST:
    sys.argv.remove("--fast")

TMP = Path(tempfile.mkdtemp(prefix="pyvideo-test-"))
os.environ.update({"ALNA_OUTPUT_DIR": str(TMP / "out"), "ALNA_WORK_DIR": str(TMP / "work"),
                   "ALNA_CACHE_DIR": str(TMP / "cache"), "ALNA_LOGS_DIR": str(TMP / "logs")})

import audio as A  # noqa: E402
import product_fetcher as pf  # noqa: E402
import storyboard as SB  # noqa: E402
import validator as V  # noqa: E402
from build_video import build_video  # noqa: E402
from common import (Logger, PipelineError, ffprobe_json, load_archetypes, load_config, load_json, save_json)  # noqa: E402
from fixtures import make_catalog, make_photo  # noqa: E402

LOG = Logger("test", echo=False)


def cfg_fast_fps() -> dict:
    cfg = load_config()
    cfg["formats"]["9x16"]["fps"] = 15  # metade dos quadros => testes mais rápidos; as regras são as mesmas
    return cfg


def fake_speech(text: str, sr: int) -> np.ndarray:
    """Voz 'de mentira': rajadas de tom com envelope silábico (só para testar ducking/tempo)."""
    dur = 0.35 + 0.055 * len(text)
    t = np.arange(int(dur * sr)) / sr
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 4.2 * t)) ** 0.7 * np.minimum(t / 0.05, 1) * np.minimum((dur - t) / 0.08, 1)
    x = sum(np.sin(2 * np.pi * 190 * k * t) / k for k in range(1, 6)) * env * 0.4
    return np.stack([x, x], axis=1).astype(np.float32)


class FakeVoice:
    def __enter__(self):
        self.o = (A.voice_settings, A.tts_elevenlabs, A.decode_audio)
        A.voice_settings = lambda cfg: ("k", "voz-teste")
        def tts(text, cfg, cache, logger, allow=False):
            p = TMP / f"fake-{abs(hash(text)) % 10**8}.npy"
            np.save(p, fake_speech(text, cfg["audio"]["sample_rate"]))
            return p
        A.tts_elevenlabs = tts
        A.decode_audio = lambda p, sr: np.load(p) if str(p).endswith(".npy") else self.o[2](p, sr)
        import build_video as BV
        self.bv = (BV.A.tts_elevenlabs, BV.A.decode_audio, BV.A.voice_settings)
        return self

    def __exit__(self, *a):
        A.voice_settings, A.tts_elevenlabs, A.decode_audio = self.o


# ----------------------------------------------------------------------------
class TestFacts(unittest.TestCase):
    def test_classify_and_risk(self):
        raw = {"name": "X", "description": "Medidas: 30 x 40 cm\nMaterial: algodão\nGarantia vitalícia contra defeitos\nO melhor do mercado\nIdeal para o dia a dia.",
               "attributes": [], "price": {"value": "49.9", "currency": "BRL"}}
        facts, missing = pf.build_facts(raw, show_price=False)
        by = {f["text"]: f for f in facts}
        self.assertEqual(by["Medidas: 30 x 40 cm"]["kind"], "dimension")
        self.assertEqual(by["Material: algodão"]["kind"], "material")
        self.assertTrue(by["Garantia vitalícia contra defeitos"]["risk"])
        self.assertFalse(by["Garantia vitalícia contra defeitos"]["usable"])
        self.assertTrue(by["O melhor do mercado"]["risk"])
        self.assertEqual(by["Ideal para o dia a dia"]["kind"], "use")
        price = [f for f in facts if f["kind"] == "price"][0]
        self.assertFalse(price["usable"], "preço só é usado com show_price=true")
        self.assertIn("quantity", missing)
        self.assertEqual(price["text"], "R$ 49,90")

    def test_manual_fact_overrides_risk(self):
        raw = {"name": "X", "description": "", "manual_facts": [{"kind": "characteristic", "text": "Garantia de 12 meses (confirmada pelo dono)"}]}
        facts, _ = pf.build_facts(raw)
        self.assertTrue(facts[0]["usable"])
        self.assertEqual(facts[0]["source"], "manual:catalogo")

    def test_no_fact_is_invented(self):
        raw = {"name": "Toalha X", "description": "Toalha de banho. Medidas 80x150cm.", "attributes": []}
        facts, _ = pf.build_facts(raw)
        desc = raw["description"].lower()
        for f in facts:
            self.assertIn(f["text"].lower().rstrip("."), desc.replace("  ", " "), "todo fato é trecho literal da fonte")

    def test_display_limit(self):
        facts, _ = pf.build_facts({"name": "X", "description": "Um texto bem longo " * 8 + "."})
        self.assertIsNone(facts[0]["display"])


class TestFetcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = TMP / "site"
        photos = [make_photo(cls.root / f"p{i}.jpg", hue=h, seed=i) for i, h in enumerate([(200, 60, 60), (60, 90, 200), (60, 160, 90)])]
        cls.pages = {
            "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /admin\n"),
            "/loja": ("text/html", '<html><body><a href="/produto/toalha-teste">Toalha</a><a href="/produto/tabua-teste">Tábua</a>'
                                    '<a href="/sobre">Sobre</a><a href="/loja?page=2" rel="next">Próxima</a></body></html>'),
            "/loja?page=2": ("text/html", '<html><body><a href="/produto/kit-teste">Kit</a></body></html>'),
            "/produto/toalha-teste": ("text/html", '<html><head><script type="application/ld+json">' + json.dumps({
                "@context": "https://schema.org", "@type": "Product", "name": "Toalha Teste", "sku": "T1",
                "description": "Toalha de teste.\nMedidas: 80 x 150 cm\nCompre agora com frete grátis",
                "image": ["/img/p0.jpg", "/img/p1.jpg"], "offers": {"@type": "Offer", "price": "59.90", "priceCurrency": "BRL"},
                "additionalProperty": [{"name": "Material", "value": "algodão de teste"}]}) + '</script></head><body></body></html>'),
            "/produto/tabua-teste": ("text/html", '<html><head><meta property="og:title" content="Tábua Teste"><meta property="og:description" content="Tábua de teste, tamanho 30 x 40 cm.">'
                                                  '<meta property="og:image" content="/img/p2.jpg"></head><body><h1>Tábua Teste</h1></body></html>'),
            "/produto/kit-teste": ("text/html", '<html><body><script id="__NEXT_DATA__" type="application/json">' + json.dumps(
                {"props": {"pageProps": {"product": {"id": 9, "name": "Kit Teste", "description": "Kit com 3 peças de teste.",
                                                       "images": [{"url": "/img/p1.jpg"}]}}}}) + '</script></body></html>'),
            "/admin": ("text/html", "proibido"),
        }
        for i in range(3):
            cls.pages[f"/img/p{i}.jpg"] = ("image/jpeg", (cls.root / f"p{i}.jpg").read_bytes())
        pages = cls.pages

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                key = self.path
                if key not in pages:
                    key = key.split("?")[0] if key.split("?")[0] in pages and "?" not in key else key
                if key not in pages:
                    self.send_response(404); self.end_headers(); return
                ct, body = pages[key]
                body = body if isinstance(body, bytes) else body.encode()
                self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a): pass
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.cfg = load_config()
        cls.cfg["store"].update({"base_url": f"http://127.0.0.1:{cls.srv.server_port}", "min_delay_s": 0.0})
        cls.cfg["store"]["supabase"]["enabled"] = False       # estes testes exercitam a leitura das páginas HTML

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_discover_and_brief(self):
        raws = pf.list_products(self.cfg, LOG)
        names = sorted(r["name"] for r in raws)
        self.assertEqual(names, ["Kit Teste", "Toalha Teste", "Tábua Teste"])
        toalha = next(r for r in raws if r["name"] == "Toalha Teste")
        brief = pf.get_brief(toalha, self.cfg, LOG)
        self.assertEqual(len(brief["product"]["images"]), 2)
        texts = {f["text"]: f for f in brief["confirmed_facts"]}
        self.assertIn("Medidas: 80 x 150 cm", texts)
        self.assertTrue(texts["Compre agora com frete grátis"]["risk"])
        self.assertIn("Material: algodão de teste", texts)
        self.assertFalse(next(f for f in brief["confirmed_facts"] if f["kind"] == "price")["usable"])
        self.assertTrue(Path(brief["product"]["images"][0]["path"]).exists())

    def test_og_fallback(self):
        raws = pf.list_products(self.cfg, LOG)
        tabua = next(r for r in raws if r["name"] == "Tábua Teste")
        self.assertEqual(len(tabua["images"]), 1)
        self.assertIn("30 x 40 cm", tabua["description"])

    def test_robots_respected(self):
        http_ = pf.Http(self.cfg, LOG)
        with self.assertRaises(PipelineError):
            http_.get(self.cfg["store"]["base_url"] + "/admin")

    def test_diagnose_report(self):
        p = pf.diagnose(self.cfg, LOG, TMP / "diag")
        txt = p.read_text(encoding="utf-8")
        self.assertIn("Produto 1", txt)
        self.assertIn("fatos:", txt)
        self.assertIn("RISCO", txt)                       # o 'frete grátis' do produto de teste foi retido
        self.assertTrue((TMP / "diag" / "list.html").exists())

    def test_empty_store_explains(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["store"]["list_path"] = "/sobre-vazio"
        self.pages["/sobre-vazio"] = ("text/html", "<html><body><div id='root'></div></body></html>")
        with self.assertRaises(PipelineError) as cm:
            pf.list_products(cfg, LOG)
        self.assertIn("catálogo manual", str(cm.exception))


class TestOps(unittest.TestCase):
    """Operação: trava, diagnóstico, doctor, aviso e feedback."""

    def test_lock_abandoned_and_live(self):
        import scheduler as S
        from common import work_dir
        cfg = load_config()
        lk = work_dir(cfg) / "daily.lock"
        lk.parent.mkdir(parents=True, exist_ok=True)
        lk.write_text(json.dumps({"pid": 2 ** 22 + 999}))
        with S.Lock(cfg):
            pass                                              # processo morto => assume
        lk.write_text(json.dumps({"pid": os.getpid()}))
        with self.assertRaises(PipelineError):
            with S.Lock(cfg):
                pass                                          # processo vivo => recusa
        lk.unlink()

    def test_doctor_runs(self):
        import doctor
        doctor.ROWS.clear()
        # a tarefa agendada só existe depois da instalação: aqui não faz parte do que o teste verifica
        doctor.check_task = lambda: doctor.add("OK", "Tarefa agendada", "(ignorada no teste)")
        rc = doctor.main(["--offline"])
        self.assertEqual(rc, 0, doctor.ROWS)
        self.assertTrue(any(r[1] == "FFmpeg" and r[0] == "OK" for r in doctor.ROWS))

    def test_doctor_reads_real_state_not_the_overwritten_summary(self):
        import datetime as dt
        import doctor
        from common import logs_dir, work_dir
        cfg = load_config()
        today = dt.date.today().isoformat()
        save_json(work_dir(cfg) / "state.json", {"days": {today: {"slots": {
            "1": {"status": "READY", "delivered": True, "final_name": "video_01_a"},
            "2": {"status": "READY", "delivered": True, "final_name": "video_02_b"},
            "3": {"status": "READY", "delivered": True, "final_name": "video_03_c"}}}}})
        save_json(logs_dir() / f"daily-{today}.json", {"day": today, "target": 3, "ready": 0, "note": "sobrescrito pela versão antiga"})
        doctor.ROWS.clear()
        doctor.check_last_runs(cfg)
        lvl, name, detail, _ = doctor.ROWS[-1]
        self.assertEqual((lvl, name), ("OK", "Última rotina"))
        self.assertIn("3/3", detail)

    def test_notify_format_and_channels(self):
        import notify
        summ = {"day": "2026-01-01", "ready": 2, "target": 3, "late": True,
                "videos": [{"produto": "A", "arquetipo": "X", "arquivo": "G:/a.mp4"}],
                "skipped": [{"slot": 3, "motivo": "sem produto"}], "errors": [{"erro": "boom"}]}
        subj, body = notify.format_summary(summ)
        self.assertIn("2/3", subj)
        self.assertIn("08:00", body)
        sent = []
        notify._send_telegram = lambda text: sent.append(text) or True
        res = notify.notify_daily(summ)
        self.assertTrue(res["telegram"] and sent and (notify.logs_dir() / "ultimo-resumo.txt").exists())

    def test_feedback(self):
        import feedback
        cfg = load_config()
        save_json(Path(os.environ["ALNA_WORK_DIR"]) / "state.json", {"days": {"2026-06-01": {"slots": {
            "1": {"archetype": "PRODUCT_HERO", "music": "PREMIUM", "hook": "question", "final_name": "video_01_x", "product_id": "p"}}}}})
        self.assertEqual(feedback.cmd_add(cfg, "video_01", 4, "ótimo gancho", "2026-06-01"), 0)
        self.assertEqual(feedback.cmd_add(cfg, "video_01", 9, "", "2026-06-01"), 2)
        self.assertEqual(feedback.cmd_summary(), 0)
        rec = [json.loads(l) for l in (feedback.logs_dir() / "feedback.jsonl").read_text(encoding="utf-8").splitlines()][-1]
        self.assertEqual((rec["archetype"], rec["score"]), ("PRODUCT_HERO", 4))


class TestStructureTechniques(unittest.TestCase):
    """Continuidade de movimento, corte na batida, crescendo, texturas e pontes sonoras."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()
        cls.briefs = [pf.get_brief(r, cls.cfg, LOG) for r in pf.load_catalog(make_catalog(TMP / "fx"))]

    def test_pan_direction_is_continuous(self):
        pairs = rev = 0
        for b in self.briefs:
            for arch, why in SB.eligible_archetypes(b).items():
                if why:
                    continue
                for seed in range(1, 6):
                    st = SB.build_storyboard(b, self.cfg, arch, seed)["continuity"]
                    pairs += st["pairs"]
                    rev += st["pan_reversals"]
        self.assertGreater(pairs, 100)
        self.assertEqual(rev, 0, "pan nunca inverte o sentido entre cenas seguidas")

    def test_transition_direction_follows_camera(self):
        import renderer as R
        from PIL import Image
        rd = R.Renderer.__new__(R.Renderer)
        rd.W, rd.H = 400, 200
        A = Image.new("RGB", (400, 200), (255, 0, 0))
        B = Image.new("RGB", (400, 200), (0, 0, 255))
        fwd = rd.transition("directional_wipe", A, B, 0.6, +1)
        back = rd.transition("directional_wipe", A, B, 0.6, -1)
        self.assertGreater(fwd.getpixel((20, 100))[2], 200)       # +1: B revelado da esquerda
        self.assertGreater(fwd.getpixel((380, 100))[0], 200)
        self.assertGreater(back.getpixel((380, 100))[2], 200)     # -1: B revelado da direita
        self.assertGreater(back.getpixel((20, 100))[0], 200)

    def test_beat_lock_aligns_every_cut(self):
        for b in self.briefs:
            for arch, why in SB.eligible_archetypes(b).items():
                if why:
                    continue
                sb = SB.build_storyboard(b, self.cfg, arch, 3)
                plan = A.plan_music(sb, self.cfg, 14)
                sb, info = SB.beat_lock(sb, self.cfg, plan)
                self.assertIsNotNone(info, arch)
                p, fps = 60.0 / info["bpm"], sb["format"]["fps"]
                cuts = [s["start"] for s in sb["scenes"][1:]] + [sb["total_duration"]]
                self.assertLessEqual(max(abs(t - round(t / p) * p) for t in cuts), 0.5 / fps + 0.006, arch)
                self.assertTrue(all(s["duration"] >= 1.2 - 1e-6 for s in sb["scenes"]))
                self.assertTrue(15 <= sb["total_duration"] <= 18)
                self.assertAlmostEqual(sum(s["duration"] for s in sb["scenes"]), sb["total_duration"], places=2)
                self.assertLessEqual(abs(info["bpm"] / plan["bpm"] - 1), 0.1001)

    def test_beat_lock_respects_voice_and_untagged_tracks(self):
        sb = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", 2)
        needs = {s["index"]: s["duration"] + 0.9 for s in sb["scenes"][:2]}
        sb, _ = SB.retime(sb, needs, self.cfg)
        sb, info = SB.beat_lock(sb, self.cfg, A.plan_music(sb, self.cfg, 5), needs)
        for s in sb["scenes"]:
            if s["index"] in needs:
                self.assertGreaterEqual(s["duration"], needs[s["index"]] - 0.04)
        sb2 = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", 2)
        _, none = SB.beat_lock(sb2, self.cfg, {"source": "arquivo", "bpm": None, "tunable": False})
        self.assertIsNone(none, "faixa sem BPM no nome: cortes livres")
        _, fixed = SB.beat_lock(sb2, self.cfg, {"source": "arquivo", "bpm": 100.0, "tunable": False})
        self.assertTrue(fixed is None or fixed["bpm"] == 100.0, "faixa com BPM não é re-sintonizada")

    def test_synth_beats_land_on_grid(self):
        sr, bpm = 48000, 120.0
        m = A.synth_music("ENERGETIC", 6.0, sr, 11, bpm=bpm)
        lp = np.convolve(np.abs(m[:, 0]), np.ones(96) / 96, mode="same")
        p = 60.0 / bpm
        for k in (2, 4, 6):                                   # kick de 4 tempos: onsets em k·p
            seg = lp[int((k * p - 0.04) * sr):int((k * p + 0.10) * sr)]
            thr = seg[: int(0.03 * sr)].mean() + 0.35 * (seg.max() - seg[: int(0.03 * sr)].mean())
            onset = np.argmax(seg > thr) / sr - 0.04
            self.assertLess(abs(onset), 0.015, f"batida {k}: {onset * 1000:.1f} ms")

    def test_crescendo_layers(self):
        sb = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", 2)
        pts = A.energy_points(sb)
        es = [e for _, e in pts]
        self.assertEqual(es, sorted(es), "energia só sobe")
        self.assertEqual(es[-1], 1.0)
        m = A.synth_music("MODERN", sb["total_duration"], 48000, 11, energy_pts=pts)
        n = len(m)
        rms = lambda x: 20 * np.log10(float(np.sqrt((x ** 2).mean())) + 1e-9)
        self.assertGreater(rms(m[2 * n // 3:]) - rms(m[: n // 3]), 5.0, "trilha cresce > 5 dB do início ao fim")

    def test_textures_are_continuous_and_bridge_cuts(self):
        sb = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", 2)
        rep = A.build_mix(sb, self.cfg, {}, LOG, TMP / "tex.wav", seed=3)
        self.assertEqual(len(rep["bridges"]), len(sb["scenes"]) - 1)
        self.assertTrue(all(b["lead_s"] >= 0.2 for b in rep["bridges"]))
        pcm = A.decode_audio(TMP / "tex.wav", 48000)
        w = int(0.4 * 48000)
        self.assertGreater(min(20 * np.log10(float(np.sqrt((pcm[i * w:(i + 1) * w] ** 2).mean())) + 1e-9)
                               for i in range(1, len(pcm) // w - 1)), -60.0)


class TestRealStoreDescriptions(unittest.TestCase):
    """Regressão com descrições REAIS da loja (tests/store_samples.py)."""

    def facts(self, desc):
        f, miss = pf.build_facts({"name": "x", "description": desc, "price": {"value": "22.86", "currency": "BRL"}})
        return {x["text"]: x for x in f}, f

    def test_toalha_each_line_is_its_own_literal_fact(self):
        from store_samples import TOALHA
        by, allf = self.facts(TOALHA)
        self.assertEqual(by["Tamanho: 70 x 130 cm"]["kind"], "dimension")
        self.assertEqual(by["Composição: Algodão com Poliéster"]["kind"], "material")
        self.assertEqual(by["Gramatura: 200g"]["display"], "Gramatura: 200g")
        self.assertEqual(by["Ideal para praia, piscina, academia, viagens e uso diário"]["kind"], "use")
        self.assertEqual(by["1 Toalha de Capivaras 70 x 130 cm – 200g"]["kind"], "contents")
        self.assertFalse(by["Observação: a tonalidade das cores pode apresentar pequenas variações conforme a iluminação e a tela do dispositivo"]["usable"])
        for f in allf:   # todo fato é trecho literal da descrição publicada
            if f["kind"] != "price":
                self.assertIn(f["text"].replace(" ", ""), TOALHA.replace(" ", "").replace("\n", ""), f["text"])

    def test_headings_never_become_facts(self):
        from store_samples import TOALHA, TOP
        for d in (TOALHA, TOP):
            _, allf = self.facts(d)
            for f in allf:
                self.assertFalse(f["text"].startswith(("Para quem", "Dois lados", "M 24", "Conteúdo da", "Características", "Medidas aproximadas")), f["text"])

    def test_approximate_measures_are_not_shown_as_exact(self):
        from store_samples import TOP
        by, _ = self.facts(TOP)
        f = by["Tamanho M: 24 cm de largura × 12 cm de altura"]
        self.assertTrue(f["approx"] and f["display"].startswith("Aprox. "))
        self.assertIn("Aprox. Tamanho G: 27 cm de largura × 14 cm de altura", [x["display"] for x in by.values()])

    def test_unverifiable_comparatives_are_held(self):
        from store_samples import TOP
        _, allf = self.facts(TOP)
        held = [f for f in allf if f["risk"]]
        self.assertTrue(any("melhor adaptação" in f["text"] for f in held))
        self.assertTrue(all(not f["usable"] for f in held))

    def test_last_line_without_period_is_not_swallowed(self):
        by, _ = self.facts("Medidas: 30 x 40 cm\nIdeal para o dia a dia.")
        self.assertIn("Ideal para o dia a dia", by)
        by, _ = self.facts("Toalha de teste.\nCompre agora com frete grátis")
        self.assertTrue(by["Compre agora com frete grátis"]["risk"], "trecho de risco é registrado, não descartado em silêncio")


class TestStoreApi(unittest.TestCase):
    """API pública da loja (PostgREST/Supabase) simulada localmente com o mesmo formato de resposta."""

    @classmethod
    def setUpClass(cls):
        from store_samples import TOALHA, TOP
        root = TMP / "api"
        for n, hue in (("a", (200, 60, 60)), ("b", (60, 90, 200)), ("c", (60, 160, 90)), ("d", (200, 160, 60))):
            make_photo(root / f"{n}.jpg", hue=hue, seed=ord(n))
        cls.rows = [
            {"id": "u1", "title": "Toalha de Capivara 70x130cm 200g Sublimação", "slug": "toalha-capivara", "description": TOALHA,
             "status": "published", "video_url": None, "category": {"name": "Banho"},
             "product_images": [{"storage_path": "u1/a.jpg", "alt_text": "Toalha dobrada mostrando a estampa completa", "position": 0},
                                {"storage_path": "u1/b.jpg", "alt_text": "Close na textura da toalha", "position": 1},
                                {"storage_path": "u1/c.jpg", "alt_text": "Pessoa usando a toalha após o banho", "position": 2},
                                {"storage_path": "u1/d.jpg", "alt_text": "Embalagem da toalha pronta para presente", "position": 3}],
             "product_variants": [{"name": "Toalha de Capivaras", "price_cents": 2286, "stock_quantity": 10}]},
            {"id": "u2", "title": "Top Feminino Esgotado", "slug": "top-esgotado", "description": TOP, "status": "published",
             "video_url": None, "category": None,
             "product_images": [{"storage_path": "u2/a.jpg", "alt_text": "Top", "position": 0}],
             "product_variants": [{"name": "TOP M", "price_cents": 1583, "stock_quantity": 0}, {"name": "TOP G", "price_cents": 1583, "stock_quantity": 0}]}]
        cls.seen = []
        rows, seen = cls.rows, cls.seen
        files = {"/storage/v1/object/public/product-media/u1/" + n + ".jpg": (root / f"{n}.jpg").read_bytes() for n in "abcd"}
        files["/storage/v1/object/public/product-media/u2/a.jpg"] = (root / "a.jpg").read_bytes()

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/rest/v1/products":
                    seen.append(self.headers.get("apikey"))
                    if self.headers.get("apikey") != "test-key":
                        self.send_response(401); self.end_headers(); return
                    body, ct = json.dumps(rows).encode(), "application/json"
                elif path in files:
                    body, ct = files[path], "image/jpeg"
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a): pass
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.cfg = load_config()
        cls.cfg["store"].update({"min_delay_s": 0.0})
        cls.cfg["store"]["supabase"].update({"enabled": True, "url": f"http://127.0.0.1:{cls.srv.server_port}", "publishable_key": "test-key"})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_reads_structured_products_with_stock_and_image_roles(self):
        raws = pf.list_products(self.cfg, LOG)
        self.assertEqual([r["source"] for r in raws], ["api", "api"])
        self.assertIn("test-key", self.seen)
        toalha = raws[0]
        self.assertEqual(toalha["stock"], 10)
        self.assertEqual(toalha["url"].rsplit("/", 2)[-2:], ["produto", "toalha-capivara"])
        roles = [toalha["image_meta"][u]["role"] for u in toalha["images"]]
        self.assertEqual(roles, ["product", "detail", "lifestyle", "packaging"])
        self.assertEqual(toalha["price"]["value"], "22.86")
        self.assertEqual(raws[1]["stock"], 0)

    def test_brief_keeps_alt_text_and_role(self):
        raws = pf.list_products(self.cfg, LOG)
        brief = pf.get_brief(raws[0], self.cfg, LOG)
        imgs = brief["product"]["images"]
        self.assertEqual([i["role"] for i in imgs], ["product", "detail", "lifestyle", "packaging"])
        self.assertIn("Close na textura", imgs[1]["alt"])
        self.assertEqual(brief["product"]["stock"], 10)
        self.assertIn("Tamanho: 70 x 130 cm", [f["text"] for f in brief["confirmed_facts"] if f["usable"]])

    def test_out_of_stock_products_get_no_video(self):
        import scheduler as S
        raws = pf.list_products(self.cfg, LOG)
        kept = S.in_stock(raws, self.cfg, LOG)
        self.assertEqual([r["name"] for r in kept], ["Toalha de Capivara 70x130cm 200g Sublimação"])
        cfg2 = copy.deepcopy(self.cfg)
        cfg2["daily"]["skip_out_of_stock"] = False
        self.assertEqual(len(S.in_stock(raws, cfg2, LOG)), 2)

    def test_detail_shots_prefer_detail_photos(self):
        raws = pf.list_products(self.cfg, LOG)
        brief = pf.get_brief(raws[0], self.cfg, LOG)
        for seed in range(1, 6):
            sb = SB.build_storyboard(brief, self.cfg, "DETAIL_MACRO", seed)
            hook = sb["scenes"][0]                            # plano macro
            self.assertEqual(brief["product"]["images"][hook["image_index"]]["role"], "detail", seed)
            for s in sb["scenes"]:
                if s["camera"]["shot"].startswith("hero"):
                    self.assertEqual(s["image_index"], 0, "planos hero usam a capa")

    def test_wrong_key_or_dead_api_falls_back_to_html(self):
        bad = copy.deepcopy(self.cfg)
        bad["store"]["supabase"]["publishable_key"] = "chave-errada"
        with self.assertRaises(PipelineError):
            pf.list_products(bad, LOG, source="api")
        dead = copy.deepcopy(self.cfg)
        dead["store"]["supabase"]["url"] = "http://127.0.0.1:9"
        dead["store"]["base_url"] = "http://127.0.0.1:9"
        with self.assertRaises(PipelineError) as cm:               # sem API e sem HTML: erro claro, não vídeo inventado
            pf.list_products(dead, LOG)
        self.assertTrue(str(cm.exception))


# chave FALSA de teste (montada em pedaços para a varredura de segredos não acusar este arquivo)
FILE_KEY = "1234567" + "8-" + "abcdef0123456789" + "abcdef01"


def make_clip(path: Path, size: str, dur: int = 8, rate: int = 30) -> Path:
    """Clipe sintético (padrão de teste do FFmpeg) — só para exercitar a leitura/composição."""
    from common import run, which_tool
    path.parent.mkdir(parents=True, exist_ok=True)
    run([which_tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={dur}",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(path)])
    return path


def fake_brief_with_use(desc: str, name: str = "Produto Teste"):
    facts, _ = pf.build_facts({"name": name, "description": desc})
    return {"product": {"id": "x", "name": name, "category": "", "images": []}, "confirmed_facts": facts}


class TestBroll(unittest.TestCase):
    """Clipes de ambiente (Pixabay simulado). O que importa aqui são as REGRAS de segurança."""

    @classmethod
    def setUpClass(cls):
        import broll
        cls.broll = broll
        root = TMP / "px"
        cls.land4k = make_clip(root / "land4k.mp4", "3840x2160", dur=6, rate=10)
        cls.land = make_clip(root / "land.mp4", "1920x1080", dur=8)
        cls.port = make_clip(root / "port.mp4", "1080x1920", dur=8)
        cls.calls = []
        calls = cls.calls
        files = {"/files/land4k.mp4": cls.land4k, "/files/land.mp4": cls.land, "/files/port.mp4": cls.port}
        cls.force_fail = False

        def rend(name, w, h, big=True):
            return {"url": f"{{BASE}}/files/{name}.mp4", "width": w, "height": h, "size": 1000} if big else {"url": "", "width": 0, "height": 0, "size": 0}
        hits = [
            {"id": 1, "pageURL": "https://pixabay.com/videos/id-1/", "tags": "beach, child, sea", "duration": 8, "user": "Autor-A",
             "videos": {"large": rend("land4k", 3840, 2160), "medium": rend("land", 1920, 1080)}},
            {"id": 2, "pageURL": "https://pixabay.com/videos/id-2/", "tags": "beach, towel, sand", "duration": 8, "user": "Autor-B",
             "videos": {"large": rend("land4k", 3840, 2160, False), "medium": rend("land", 1920, 1080)}},
            {"id": 3, "pageURL": "https://pixabay.com/videos/id-3/", "tags": "beach, sea, waves, pool", "duration": 8, "user": "Autor-C",
             "videos": {"large": rend("land4k", 3840, 2160), "medium": rend("land", 1920, 1080)}},
            {"id": 4, "pageURL": "https://pixabay.com/videos/id-4/", "tags": "beach, sunset, gym", "duration": 8, "user": "Autor-D",
             "videos": {"large": rend("port", 1080, 1920), "medium": rend("port", 1080, 1920)}},
        ]

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                from urllib.parse import parse_qs, urlparse
                u = urlparse(self.path)
                if u.path == "/api/videos/":
                    q = parse_qs(u.query)
                    calls.append({"q": q.get("q", [""])[0], "lang": q.get("lang", [""])[0], "key": q.get("key", [""])[0]})
                    if cls.force_fail:
                        self.send_response(500); self.end_headers(); return
                    if q.get("key", [""])[0] not in ("pixkey", FILE_KEY):
                        self.send_response(400); self.end_headers(); self.wfile.write(b"[ERROR 400] Invalid API key"); return
                    base = f"http://127.0.0.1:{cls.srv.server_port}"
                    body = json.dumps({"total": 4, "totalHits": 4, "hits": json.loads(json.dumps(hits).replace("{BASE}", base))}).encode()
                    ct = "application/json"
                elif u.path in files:
                    calls.append({"download": u.path})
                    body, ct = files[u.path].read_bytes(), "video/mp4"
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a): pass
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.cfg = cfg_fast_fps()
        cls.cfg["store"]["min_delay_s"] = 0.0
        cls.cfg["broll"].update({"enabled": True, "api_url": f"http://127.0.0.1:{cls.srv.server_port}/api/videos/", "min_delay_s": 0.0})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.calls.clear()
        type(self).force_fail = False
        os.environ["PIXABAY_API_KEY"] = "pixkey"
        from common import cache_dir
        shutil.rmtree(cache_dir(self.cfg) / "broll", ignore_errors=True)
        shutil.rmtree(cache_dir(self.cfg) / "http", ignore_errors=True)

    def tearDown(self):
        os.environ.pop("PIXABAY_API_KEY", None)

    def test_themes_come_only_from_confirmed_use_facts(self):
        from store_samples import TOALHA
        b = fake_brief_with_use(TOALHA, "Toalha de Capivara")
        themes = self.broll.themes_for(b)
        self.assertEqual({t["theme"] for t in themes}, {"praia", "piscina", "academia", "viagem"})
        use = next(f for f in b["confirmed_facts"] if f["kind"] == "use" and "praia" in f["text"])
        self.assertTrue(all(t["fact_id"] == use["id"] for t in themes), "cada tema aponta o fato de uso que o justifica")
        # "praia" numa frase de marketing que NÃO é fato de uso não gera busca
        b2 = fake_brief_with_use("Deixe seus momentos de praia, piscina e lazer muito mais divertidos com a Toalha!")
        self.assertEqual(self.broll.themes_for(b2), [])
        # fato de uso marcado como risco/retido também não
        b3 = fake_brief_with_use("Ideal para praia")
        b3["confirmed_facts"][0]["usable"] = False
        self.assertEqual(self.broll.themes_for(b3), [])

    def test_choose_hit_filters(self):
        cfg = self.cfg
        mk = lambda i, tags, dur=8, w=1920, big=None: {"id": i, "tags": tags, "duration": dur,
             "videos": {"large": big or {"url": "", "width": 0}, "medium": {"url": f"u{i}", "width": w, "height": 1080}}}
        conflicts = self.broll.conflict_words({"product": {"name": "Toalha de Capivara 70x130cm", "category": ""}})
        self.assertIn("towel", conflicts)
        self.assertIn("toalha", conflicts)
        hits = [mk(1, "beach, child"), mk(2, "beach, towel"), mk(3, "beach", dur=2), mk(4, "beach", w=1280), mk(5, "beach, sea")]
        self.assertEqual(self.broll.choose_hit(hits, conflicts, cfg)["hit"]["id"], 5)
        self.assertIsNone(self.broll.choose_hit(hits[:4], conflicts, cfg))
        self.assertEqual(self.broll.choose_hit([mk(6, "beach", big={"url": "L", "width": 3840, "height": 2160})], set(), cfg)["rendition"]["name"], "large")

    def test_prepare_downloads_records_origin_and_caches(self):
        from store_samples import TOALHA
        b = fake_brief_with_use(TOALHA, "Toalha de Capivara 70x130cm")
        out = self.broll.prepare_broll(b, self.cfg, LOG)
        self.assertEqual(len(out), 1, "no máximo max_per_video")
        it = out[0]
        self.assertEqual((it["provider"], it["theme"]), ("pixabay", "praia"))
        self.assertEqual(it["id"], 3, "id 1 tem criança, id 2 tem 'towel'")
        self.assertTrue(Path(it["path"]).exists() and it["sha256"] and it["user"] == "Autor-C" and it["page_url"].endswith("id-3/"))
        self.assertEqual(it["rendition"], "large")
        first = self.calls[0]
        self.assertEqual((first["q"], first["lang"], first["key"]), ("praia", "pt", "pixkey"))
        n = len(self.calls)
        again = self.broll.prepare_broll(b, self.cfg, LOG)                     # 2ª vez: tudo do cache (API exige 24 h)
        self.assertEqual(len(self.calls), n, "sem nova busca nem novo download")
        self.assertEqual(again[0]["id"], 3)

    def test_reads_the_key_from_the_local_file(self):
        """A chave pode vir do arquivo `APIpixabay` (Bloco de Notas) em vez da variável de ambiente."""
        from store_samples import TOALHA
        d = TMP / "keyfile"
        d.mkdir(parents=True, exist_ok=True)
        (d / "APIpixabay.txt").write_text(f"chave: {FILE_KEY}", encoding="utf-8")
        cfg = copy.deepcopy(self.cfg)
        cfg["broll"]["key_file"] = str(d / "APIpixabay")
        os.environ.pop("PIXABAY_API_KEY")                      # sem variável: só o arquivo
        out = self.broll.prepare_broll(fake_brief_with_use(TOALHA, "Toalha de Capivara 70x130cm"), cfg, LOG)
        self.assertEqual(len(out), 1)
        self.assertEqual(self.calls[0]["key"], FILE_KEY, "a chave do arquivo é a que vai para a API")

    def test_no_key_or_disabled_means_no_network(self):
        from store_samples import TOALHA
        b = fake_brief_with_use(TOALHA)
        os.environ.pop("PIXABAY_API_KEY")
        self.assertEqual(self.broll.prepare_broll(b, self.cfg, LOG), [])
        os.environ["PIXABAY_API_KEY"] = "pixkey"
        off = copy.deepcopy(self.cfg)
        off["broll"]["enabled"] = False
        self.assertEqual(self.broll.prepare_broll(b, off, LOG), [])
        self.assertEqual(self.calls, [])

    def test_api_failure_never_breaks_the_video(self):
        from store_samples import TOALHA
        type(self).force_fail = True
        self.assertEqual(self.broll.prepare_broll(fake_brief_with_use(TOALHA), self.cfg, LOG), [])
        os.environ["PIXABAY_API_KEY"] = "chave-errada"
        type(self).force_fail = False
        self.assertEqual(self.broll.prepare_broll(fake_brief_with_use(TOALHA), self.cfg, LOG), [])

    def _brief_with_clip(self):
        raws = pf.load_catalog(make_catalog(TMP / "fx"))
        brief = pf.get_brief(raws[0], self.cfg, LOG)            # produto teste com fato de uso "Ideal para testes de vídeo"
        use = next(f for f in brief["confirmed_facts"] if f["kind"] == "use")
        brief["broll"] = [{"theme": "praia", "fact_id": use["id"], "path": str(self.land4k), "provider": "pixabay", "id": 3,
                           "page_url": "https://pixabay.com/videos/id-3/", "user": "Autor-C", "tags": "beach, sea, waves",
                           "duration": 8, "width": 3840, "height": 2160, "rendition": "large", "sha256": "x"}]
        return brief, use

    def test_storyboard_adds_labelled_clip_scene_only_with_a_clip(self):
        brief, use = self._brief_with_clip()
        sb = SB.build_storyboard(brief, self.cfg, "PRODUCT_HERO", seed=2)
        clips = [s for s in sb["scenes"] if s.get("clip")]
        self.assertEqual(len(clips), 1)
        s = clips[0]
        self.assertTrue(s["illustrative"] and s["text"]["source"] == f"fact:{use['id']}" and s["image"] is None)
        self.assertEqual(SB.expected_text(s["text"]["source"], brief, self.cfg), s["text"]["text"])
        self.assertEqual(sum(1 for x in sb["scenes"] if x["text"] and x["text"]["source"] == f"fact:{use['id']}"), 1, "o fato de uso não repete")
        self.assertTrue(15 <= sb["total_duration"] <= 18)
        brief2 = copy.deepcopy(brief)
        brief2["broll"] = []
        sb2 = SB.build_storyboard(brief2, self.cfg, "PRODUCT_HERO", seed=2)
        self.assertFalse(any(x.get("clip") for x in sb2["scenes"]))
        self.assertTrue(15 <= sb2["total_duration"] <= 18)
        brief3 = copy.deepcopy(brief)
        brief3["broll"][0]["fact_id"] = "f999"                  # tema sem fato de uso correspondente: não entra
        self.assertFalse(any(x.get("clip") for x in SB.build_storyboard(brief3, self.cfg, "PRODUCT_HERO", seed=2)["scenes"]))

    def test_clip_source_composes_vertical_frames(self):
        import renderer as R
        for path, name in ((self.land4k, "4K recortado"), (self.land, "1080p com fundo desfocado"), (self.port, "vertical")):
            src = R.ClipSource(str(path), 1080, 1920, 30)
            f0, f20 = src.read(0), src.read(20)
            self.assertEqual(f0.size, (1080, 1920), name)
            diff = np.abs(np.asarray(f0, np.int16) - np.asarray(f20, np.int16)).mean()
            self.assertGreater(diff, 1.0, f"{name}: o vídeo se move")
            self.assertEqual(src.peek(1.0).size, (1080, 1920))
            last = src.read(100000)                              # além do fim: congela o último quadro
            self.assertTrue(np.array_equal(np.asarray(last), np.asarray(src.read(100001))))
            src.close()

    def test_demo_mode_relaxes_filters_but_normal_mode_does_not(self):
        from store_samples import TOALHA
        brief = fake_brief_with_use(TOALHA, "Toalha de Capivara 70x130cm")
        normal = self.broll.prepare_broll(brief, self.cfg, LOG)
        self.assertEqual([i["id"] for i in normal], [3], "rotina diária: 1 clipe, sem produto parecido (towel) e sem crianças")
        shutil.rmtree(Path(os.environ["ALNA_CACHE_DIR"]) / "http", ignore_errors=True)
        self.calls.clear()
        demo = copy.deepcopy(self.cfg)
        demo["broll"].update({"demo": True, "max_per_video": 3})
        out = self.broll.prepare_broll(brief, demo, LOG)
        self.assertEqual([i["id"] for i in out], [2, 3, 4], "demo: aceita 'towel', 3 clipes distintos, ainda sem crianças (id 1)")
        self.assertEqual([i["theme"] for i in out], ["praia", "piscina", "academia"])
        self.assertEqual(self.calls[0]["q"], "towel beach", "demo busca o produto + tema (pessoas usando)")
        self.assertTrue(all(i["fact_id"] == out[0]["fact_id"] for i in out), "todo clipe aponta o fato de uso que o justifica")

    def test_demo_ranks_by_closeness_to_the_product(self):
        mk = lambda i, tags: {"id": i, "tags": tags, "duration": 8, "videos": {"large": {"url": "", "width": 0}, "medium": {"url": f"u{i}", "width": 1920, "height": 1080}}}
        brief = fake_brief_with_use("Ideal para praia", "Toalha de Banho Algodão")
        brief["confirmed_facts"].append({"id": "fx", "kind": "material", "text": "Composição: algodão", "usable": True, "display": "x"})
        sim = self.broll.similarity_terms(brief)
        self.assertIn("towel", sim["primary"])
        self.assertIn("cotton", sim["extra"])
        rank = {"sim": sim, "theme_words": ["beach"], "people": True, "min_score": 3}
        hits = [mk(1, "beach, sea"), mk(2, "beach, woman"), mk(3, "beach, towel, woman, cotton"), mk(4, "forest, tree")]
        best = self.broll.choose_hit(hits, set(), self.cfg, rank=rank)
        self.assertEqual(best["hit"]["id"], 3, "o clipe mais próximo (toalha + praia + pessoa + algodão) vence, não o primeiro")
        self.assertIn("towel", best["matched"])
        self.assertEqual(self.broll.choose_hit([mk(4, "forest, tree")], set(), self.cfg, rank=rank), None, "sem relação com produto/tema: nenhum serve")
        self.assertEqual(self.broll.choose_hit(hits, set(), self.cfg)["hit"]["id"], 1, "rotina diária (sem ranking): primeiro que passa")

    def _brief_with_clips(self, n=3):
        brief, use = self._brief_with_clip()
        paths = [self.land4k, self.land, self.port]
        brief["broll"] = [{**brief["broll"][0], "id": 10 + k, "path": str(paths[k]), "theme": ["praia", "piscina", "academia"][k],
                           "user": f"Autor-{k}"} for k in range(n)]
        return brief, use

    def test_demo_mix_alternates_photos_and_clips(self):
        brief, use = self._brief_with_clips(3)
        demo = copy.deepcopy(self.cfg)
        demo["broll"].update({"demo": True, "max_per_video": 3})
        sb = SB.build_storyboard(brief, demo, "DEMO_MIX", seed=2)
        roles = ["clip" if s.get("clip") else "foto" for s in sb["scenes"]]
        self.assertEqual(roles, ["clip", "foto", "foto", "clip", "foto", "clip", "foto"])
        texts = [s["text"] for s in sb["scenes"] if s.get("clip")]
        self.assertEqual(sum(1 for x in texts if x), 1, "só um clipe leva o texto do fato de uso; os outros ficam sem texto")
        self.assertTrue(all(s["illustrative"] for s in sb["scenes"] if s.get("clip")))
        self.assertTrue(15 <= sb["total_duration"] <= 18)
        self.assertTrue(sb["scenes"][0]["sfx"] and sb["scenes"][1]["sfx"], "efeitos sonoros nas trocas")
        self.assertEqual(len([s for s in SB.build_storyboard(self._brief_with_clips(2)[0], demo, "DEMO_MIX", seed=2)["scenes"] if s.get("clip")]), 2)
        one = self._brief_with_clips(1)[0]
        self.assertNotEqual(SB.eligible_archetypes(one)["DEMO_MIX"], "", "com 1 clipe só (rotina diária) o DEMO_MIX não é elegível")
        brief.pop("broll")
        self.assertNotEqual(SB.eligible_archetypes(brief)["DEMO_MIX"], "")

    def test_demo_video_end_to_end(self):
        if FAST:
            self.skipTest("renderiza vídeo")
        brief, use = self._brief_with_clips(3)
        cfg = copy.deepcopy(self.cfg)
        cfg["broll"].update({"demo": True, "max_per_video": 3})
        res = build_video(brief, cfg, "demo-e2e", day="2026-07-02", archetype="DEMO_MIX", seed=3, voice_mode="off",
                          out_root=TMP / "out-demo")
        self.assertEqual(res["status"], "READY", res)
        job = TMP / "work" / "2026-07-02" / "demo-e2e"
        val = load_json(job / "validation.json")
        self.assertTrue(val["ok"], val["errors"])
        self.assertIn("MODO DEMONSTRAÇÃO", (job / "creditos.txt").read_text(encoding="utf-8"))
        sb = load_json(job / "storyboard.json")
        self.assertTrue(sb["strategy"]["demo"])
        rr = load_json(job / "render_report.json")
        labels = [l for sc in rr["scenes"] for l in sc["layers"] if l["role"] == "badge"]
        self.assertEqual(len(labels), 3, "rótulo 'Imagem ilustrativa' em cada cena de clipe")
        # o gate continua barrando clipe sem fato de uso que o justifique
        bf = load_json(job / "brief.json")
        sb2 = copy.deepcopy(sb)
        next(s for s in sb2["scenes"] if s.get("clip"))["clip"]["fact_id"] = "f999"
        r = V.validate(job / "video.mp4", sb2, bf, cfg, rr, load_json(job / "audio_report.json"))
        self.assertFalse(r["ok"])

    def test_validator_rules_for_clips(self):
        if FAST:
            self.skipTest("renderiza vídeo")
        brief, use = self._brief_with_clip()
        res = build_video(brief, self.cfg, "broll-e2e", day="2026-07-01", archetype="PRODUCT_HERO", seed=2, voice_mode="off",
                          out_root=TMP / "out-broll")
        self.assertEqual(res["status"], "READY", res)
        job = TMP / "work" / "2026-07-01" / "broll-e2e"
        sb, bf = load_json(job / "storyboard.json"), load_json(job / "brief.json")
        rr, ar = load_json(job / "render_report.json"), load_json(job / "audio_report.json")
        val = load_json(job / "validation.json")
        names = {c["name"]: c for c in val["checks"]}
        for k in ("b-roll: ilustra só um uso confirmado e tem origem registrada", 'b-roll: rótulo "Imagem ilustrativa" visível',
                  "b-roll: sem crianças nas tags"):
            self.assertTrue(names[k]["ok"], names[k])
        self.assertIn("Autor-C", (job / "creditos.txt").read_text(encoding="utf-8"))
        self.assertTrue((TMP / "out-broll" / "2026-07-01" / "_auditoria" / res["final_name"] / "creditos.txt").exists())
        # sem o rótulo => reprova
        rr2 = copy.deepcopy(rr)
        for sc in rr2["scenes"]:
            sc["layers"] = [l for l in sc["layers"] if l["role"] != "badge"]
        self.assertFalse(V.validate(job / "video.mp4", sb, bf, self.cfg, rr2, ar)["ok"])
        # texto que não é fato de USO => reprova
        sb2 = copy.deepcopy(sb)
        other = next(f for f in bf["confirmed_facts"] if f["kind"] != "use" and f["usable"] and f["display"])
        cs = next(s for s in sb2["scenes"] if s.get("clip"))
        cs["text"].update({"source": f"fact:{other['id']}", "text": other["display"]})
        r = V.validate(job / "video.mp4", sb2, bf, self.cfg, rr, ar)
        self.assertFalse(r["ok"])
        self.assertTrue(any("uso confirmado" in e for e in r["errors"]))
        # clipe com tag de criança => reprova; origem apagada => reprova
        sb3 = copy.deepcopy(sb)
        next(s for s in sb3["scenes"] if s.get("clip"))["clip"]["tags"] = "beach, child"
        self.assertFalse(V.validate(job / "video.mp4", sb3, bf, self.cfg, rr, ar)["ok"])
        sb4 = copy.deepcopy(sb)
        next(s for s in sb4["scenes"] if s.get("clip"))["clip"]["user"] = ""
        self.assertFalse(V.validate(job / "video.mp4", sb4, bf, self.cfg, rr, ar)["ok"])


class TestSecrets(unittest.TestCase):
    """Chave do Pixabay em arquivo local (fora do git): leitura, vazamento e varredura."""

    def setUp(self):
        self.d = TMP / f"sec-{id(self)}"
        self.d.mkdir(parents=True, exist_ok=True)
        os.environ.pop("PIXABAY_API_KEY", None)

    def read(self, **kw):
        import localsecrets as L
        return L.read_secret("PIXABAY_API_KEY", ["APIpixabay"], L.PIXABAY_KEY, base=self.d)

    def test_file_formats_from_notepad(self):
        cases = {
            "APIpixabay": FILE_KEY,                                                        # só a chave, sem extensão
            "APIpixabay.txt": f"chave: {FILE_KEY}\n",                                      # Bloco de Notas esconde o .txt
            "APIpixabay.txt.txt": f"# minha chave\nkey={FILE_KEY} (Pixabay)\n\n",         # comentário e linhas extras
        }
        for name, content in cases.items():
            for f in self.d.glob("APIpixabay*"):
                f.unlink()
            (self.d / name).write_text(content, encoding="utf-8")
            val, origin = self.read()
            self.assertEqual(val, FILE_KEY, name)
            self.assertIn("arquivo", origin)
            self.assertNotIn(FILE_KEY, origin, "a origem descreve o arquivo, nunca o valor")
        for f in self.d.glob("APIpixabay*"):
            f.unlink()
        (self.d / "APIpixabay").write_bytes(b"\xef\xbb\xbf" + FILE_KEY.encode())              # UTF-8 com BOM
        self.assertEqual(self.read()[0], FILE_KEY)
        (self.d / "APIpixabay").write_bytes(FILE_KEY.encode("utf-16"))                      # UTF-16 (Bloco de Notas antigo)
        self.assertEqual(self.read()[0], FILE_KEY)

    def test_missing_invalid_and_env_priority(self):
        self.assertEqual(self.read(), (None, ""))
        (self.d / "APIpixabay").write_text("cole a chave aqui", encoding="utf-8")
        self.assertEqual(self.read()[0], None, "texto sem uma chave no formato esperado não é aceito")
        (self.d / "APIpixabay").write_text(FILE_KEY, encoding="utf-8")
        os.environ["PIXABAY_API_KEY"] = "da-variavel"
        try:
            self.assertEqual(self.read(), ("da-variavel", "variável PIXABAY_API_KEY"))
        finally:
            os.environ.pop("PIXABAY_API_KEY")

    def test_logs_and_errors_never_contain_the_key(self):
        from common import logs_dir, redact
        secret = "ZZ-SEGREDO-123"
        self.assertEqual(redact(f"GET /api/videos/?key={secret}&q=praia"), "GET /api/videos/?key=***&q=praia")
        self.assertEqual(redact(f"token={secret} password={secret}"), "token=*** password=***")
        log = Logger("sec-test", echo=False)
        log.warn(f"falhou https://x/api?key={secret}&q=1", erro=f"url=https://x/?apikey={secret}")
        text = "".join(p.read_text(encoding="utf-8") for p in logs_dir().glob("*.jsonl"))
        self.assertNotIn(secret, text)
        self.assertIn("key=***", text)
        http_ = pf.Http(load_config(), LOG)
        with self.assertRaises(PipelineError) as cm:                       # porta fechada: o erro do requests traz a URL inteira
            http_.get_json("http://127.0.0.1:9/api/videos/", {"key": secret, "q": "praia"}, ttl_hours=0)
        self.assertNotIn(secret, str(cm.exception))

    def test_no_secret_in_project_files(self):
        """Falha se uma chave (Pixabay/ElevenLabs/service_role) aparecer em qualquer arquivo versionável da skill."""
        from common import SKILL_DIR
        pats = [re.compile(r"\b\d{6,}-[0-9a-f]{20,}\b"), re.compile(r"\bsk_[0-9a-f]{24,}\b"),
                re.compile(r"service_role[\"'\s:=]+eyJ"), re.compile(r"\bxi-api-key\s*[:=]\s*[0-9a-f]{20,}", re.I)]
        skip = {"work", "cache", "output", "logs", ".venv", "__pycache__"}
        ign = (SKILL_DIR / ".gitignore").read_text(encoding="utf-8")
        for needle in ("APIpixabay", "*.key", ".env"):
            self.assertIn(needle, ign, f".gitignore precisa ignorar {needle}")
        bad = []
        for p in SKILL_DIR.rglob("*"):
            if p.is_dir() or skip & set(p.relative_to(SKILL_DIR).parts) or p.name.startswith("APIpixabay") or p.suffix in (".ttf", ".jpg", ".png", ".pyc", ".mp4"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in pats:
                if pat.search(text):
                    bad.append(f"{p.relative_to(SKILL_DIR)} ~ {pat.pattern[:30]}")
        self.assertEqual(bad, [], "possível segredo em arquivo do projeto")


class TestStoryboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()
        cat = make_catalog(TMP / "fx")
        cls.raws = pf.load_catalog(cat)
        cls.briefs = [pf.get_brief(r, cls.cfg, LOG) for r in cls.raws]

    def test_eligibility_never_invents(self):
        b1, b2, b3 = self.briefs
        e1, e2 = SB.eligible_archetypes(b1), SB.eligible_archetypes(b2)
        self.assertEqual(e1["GIFT_ANGLE"] and "bloqueado", "bloqueado", "sem fato 'gift' não há arquétipo de presente")
        self.assertEqual(e2["GIFT_ANGLE"], "")  # produto 2 tem fato de presente confirmado
        self.assertTrue(e1["PROBLEM_SOLUTION"] and e1["BEFORE_AFTER"] and e1["COMPARISON"])
        self.assertEqual(e1["PRODUCT_HERO"], "")

    def test_text_traceable_and_unique_facts(self):
        for b in self.briefs:
            for arch in [a for a, why in SB.eligible_archetypes(b).items() if not why]:
                sb = SB.build_storyboard(b, self.cfg, arch, seed=5)
                used = []
                for s in sb["scenes"]:
                    if s["text"]:
                        self.assertEqual(SB.expected_text(s["text"]["source"], b, self.cfg), s["text"]["text"])
                        if s["text"]["source"].startswith("fact:"):
                            used.append(s["text"]["source"])
                self.assertEqual(len(used), len(set(used)), "mesmo fato não repete no vídeo")
                self.assertTrue(15 <= sb["total_duration"] <= 18, sb["total_duration"])
                self.assertAlmostEqual(sum(s["duration"] for s in sb["scenes"]), sb["total_duration"], places=2)
                self.assertEqual(sb["scenes"][-1]["text"]["role"], "cta")

    def test_risky_facts_never_used(self):
        b3 = self.briefs[2]
        sb = SB.build_storyboard(b3, self.cfg, "FEATURE_SHOWCASE" if not SB.eligible_archetypes(b3)["FEATURE_SHOWCASE"] else "PRODUCT_HERO", seed=1)
        shown = " ".join(s["text"]["text"].lower() for s in sb["scenes"] if s["text"])
        self.assertNotIn("garantia", shown)
        self.assertNotIn("melhor", shown)

    def test_variety_across_seeds(self):
        import random
        b = self.briefs[0]
        picks = {SB.choose_archetype(b, random.Random(i)) for i in range(40)}
        self.assertGreater(len(picks), 3)
        avoid = SB.choose_archetype(b, random.Random(1), avoid_archetypes=["PRODUCT_HERO", "FEATURE_SHOWCASE"])
        self.assertNotIn(avoid, ["PRODUCT_HERO", "FEATURE_SHOWCASE"])

    def test_all_transitions_default_hard_cut(self):
        sb = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", seed=2)
        kinds = [s["transition_in"]["type"] for s in sb["scenes"]]
        self.assertGreaterEqual(kinds.count("hard_cut") + kinds.count("match_cut"), len(kinds) // 2)

    def test_retime_fits_voice(self):
        sb = SB.build_storyboard(self.briefs[0], self.cfg, "PRODUCT_HERO", seed=2)
        needs = {s["index"]: s["duration"] + 0.8 for s in sb["scenes"][:3]}
        sb2, dropped = SB.retime(copy.deepcopy(sb), needs, self.cfg)
        self.assertTrue(15 <= sb2["total_duration"] <= 18)
        for s in sb2["scenes"]:
            if s["index"] in needs and s["index"] not in dropped:
                self.assertGreaterEqual(s["duration"], needs[s["index"]] - 0.04)
        self.assertAlmostEqual(sb2["scenes"][-1]["start"] + sb2["scenes"][-1]["duration"], sb2["total_duration"], places=2)
        huge = {s["index"]: 5.0 for s in sb["scenes"]}
        sb3, dropped = SB.retime(copy.deepcopy(sb), huge, self.cfg)
        self.assertTrue(dropped, "quando não cabe, falas são removidas em vez de cortadas")
        self.assertLessEqual(sb3["total_duration"], 18)


class TestAudio(unittest.TestCase):
    def test_speakable_numbers(self):
        self.assertEqual(A.speakable("80x150cm"), "80 por 150 centímetros")
        self.assertEqual(A.speakable("Medidas: 80 x 150 cm"), "Medidas: 80 por 150 centímetros")
        self.assertEqual(A.speakable("30 x 40"), "30 por 40")
        self.assertEqual(A.speakable("100% algodão"), "100 por cento algodão")
        self.assertEqual(A.speakable("R$ 49,90"), "49 reais e 90 centavos")

    def test_sfx_and_music_valid(self):
        for k in ["whoosh", "swipe", "impact", "soft_impact", "click", "pop", "rise", "hit", "ambient", "transition"]:
            x = A.synth_sfx(k)
            self.assertEqual(x.shape[1], 2)
            self.assertTrue(np.isfinite(x).all() and (0.02 if k != "ambient" else 0.001) < np.abs(x).max() <= 1.2, k)
        for p in A.PROFILES:
            m = A.synth_music(p, 4.0)
            self.assertEqual(m.shape, (4 * 48000, 2), p)
            self.assertTrue(np.isfinite(m).all() and 0.3 < np.abs(m).max() <= 0.55, p)
        a, b = A.synth_music("MODERN", 2, seed=1), A.synth_music("MODERN", 2, seed=1)
        self.assertTrue(np.array_equal(a, b), "determinístico")

    def test_ducking_curve(self):
        sr = 48000
        voice = np.zeros((sr * 4, 2), np.float32)
        voice[sr:2 * sr] = fake_speech("x" * 15, sr)[:sr]
        g = A.duck_curve(voice, sr, -14.0)
        self.assertAlmostEqual(float(g[int(0.3 * sr)]), 1.0, places=2)
        self.assertLess(float(g[int(1.5 * sr)]), A.db(-12))
        self.assertGreater(float(g[int(3.8 * sr)]), 0.9, "volta ao normal depois da fala")

    def test_voice_lock(self):
        from common import CONFIG_PATH
        lock = CONFIG_PATH.parent / "voice.lock.json"
        existed = lock.exists()
        backup = lock.read_bytes() if existed else None
        try:
            lock.unlink(missing_ok=True)
            A.enforce_voice_lock("voz-A")
            A.enforce_voice_lock("voz-A")
            with self.assertRaises(PipelineError):
                A.enforce_voice_lock("voz-B")
            A.enforce_voice_lock("voz-B", allow_change=True)
        finally:
            lock.unlink(missing_ok=True)
            if backup:
                lock.write_bytes(backup)

    def test_voice_not_configured(self):
        env = {k: os.environ.pop(k) for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID") if k in os.environ}
        try:
            with self.assertRaises(A.VoiceNotConfigured):
                A.voice_settings(load_config())
        finally:
            os.environ.update(env)


class TestGraphics(unittest.TestCase):
    def test_fonts_and_contrast(self):
        import graphics as g
        cfg = load_config()
        from common import fonts_dir
        path, fam = g.find_font(cfg, fonts_dir(cfg))
        self.assertEqual(fam, "Inter", "a Inter que acompanha a skill é a fonte escolhida")
        self.assertTrue(Path(path).exists(), fam)
        self.assertGreater(g.contrast_ratio((255, 255, 255), (0, 0, 0)), 20)
        self.assertLess(g.contrast_ratio((255, 255, 255), (250, 250, 250)), 1.2)


# ----------------------------------------------------------------------------
@unittest.skipIf(FAST, "teste lento (renderiza vídeos)")
class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = cfg_fast_fps()
        cls.raws = pf.load_catalog(make_catalog(TMP / "fx"))

    def brief(self, i=0):
        return pf.get_brief(self.raws[i], self.cfg, LOG)

    def test_full_video_with_voice(self):
        with FakeVoice():
            res = build_video(self.brief(0), self.cfg, "e2e-voice", day="2026-01-01", archetype="PRODUCT_HERO", seed=4,
                              voice_mode="required", out_root=TMP / "out")
        self.assertEqual(res["status"], "READY")
        mp4 = Path(res["final_path"])
        self.assertTrue(mp4.exists())
        probe = ffprobe_json(mp4)
        v = next(s for s in probe["streams"] if s["codec_type"] == "video")
        a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
        self.assertEqual((v["codec_name"], v["pix_fmt"], v["width"], v["height"]), ("h264", "yuv420p", 1080, 1920))
        self.assertEqual(a["codec_name"], "aac")
        self.assertTrue(15 <= float(probe["format"]["duration"]) <= 18.05)
        self.assertTrue(V.moov_before_mdat(mp4))
        job = TMP / "work" / "2026-01-01" / "e2e-voice"
        ar = load_json(job / "audio_report.json")
        self.assertTrue(ar["has_voice"])
        self.assertGreaterEqual(ar["ducking_applied_db"], 6)
        self.assertFalse(ar["voice_cut"])
        st = load_json(job / "status.json")
        self.assertEqual([h["status"] for h in st["history"]], ["QUEUED", "PROCESSING", "RENDERING", "VALIDATING", "READY"])
        val = load_json(job / "validation.json")
        self.assertTrue(val["ok"], val["errors"])
        names = {c["name"]: c for c in val["checks"]}
        for key in ("cortes na batida (erro ≤ meio quadro)", "pontes sonoras (som da cena entra antes do corte)",
                    "áudio nunca em silêncio (textura contínua)", "trilha cresce até o clímax (≥ 3 dB do início ao fim)"):
            self.assertTrue(names[key]["ok"], names[key])
        self.assertTrue(load_json(job / "storyboard.json")["music"]["locked"])
        self.assertTrue((TMP / "out" / "2026-01-01" / "_auditoria" / "video_01_produto-teste-um" / "script.md").exists())

    def test_validator_rejects_corrupt_and_invented(self):
        res = build_video(self.brief(1), self.cfg, "e2e-neg", day="2026-01-02", seed=2, voice_mode="off", out_root=TMP / "out",
                          deliver_output=False)
        job = TMP / "work" / "2026-01-02" / "e2e-neg"
        sb, brief = load_json(job / "storyboard.json"), load_json(job / "brief.json")
        rr, ar = load_json(job / "render_report.json"), load_json(job / "audio_report.json")
        good = V.validate(job / "video.mp4", sb, brief, self.cfg, rr, ar)
        self.assertTrue(good["ok"], good["errors"])
        # 1) arquivo truncado = corrompido
        bad_mp4 = TMP / "truncated.mp4"
        data = (job / "video.mp4").read_bytes()
        bad_mp4.write_bytes(data[: len(data) // 3])
        r1 = V.validate(bad_mp4, sb, brief, self.cfg, rr, ar)
        self.assertFalse(r1["ok"])
        # 2) texto inventado no storyboard
        sb2 = copy.deepcopy(sb)
        tgt = next(s for s in sb2["scenes"] if s["text"] and s["text"]["source"].startswith("fact:"))
        tgt["text"]["text"] = "Resistente a água e super durável"
        r2 = V.validate(job / "video.mp4", sb2, brief, self.cfg, rr, ar)
        self.assertFalse(r2["ok"])
        self.assertTrue(any("inventada" in e for e in r2["errors"]))
        # 3) texto fora da safe area
        rr3 = copy.deepcopy(rr)
        rr3["scenes"][0]["layers"] = rr3["scenes"][0]["layers"] or [{"scene": 1, "bbox": [0, 0, 100, 100], "font_px": 60, "contrast": 9}]
        rr3["scenes"][0]["layers"][0]["bbox"] = [0, 10, 300, 100]
        self.assertFalse(V.validate(job / "video.mp4", sb, brief, self.cfg, rr3, ar)["ok"])
        # 4) arquivo mudo / sem CTA
        sb4 = copy.deepcopy(sb)
        sb4["scenes"][-1]["text"]["role"] = "fact"
        self.assertFalse(V.validate(job / "video.mp4", sb4, brief, self.cfg, rr, ar)["ok"])

    def test_failed_job_never_ready(self):
        brief = self.brief(0)
        brief["product"]["images"][0]["path"] = str(TMP / "nao-existe.jpg")
        with self.assertRaises(PipelineError):
            build_video(brief, self.cfg, "e2e-fail", day="2026-01-03", seed=1, voice_mode="off", out_root=TMP / "out")
        st = load_json(TMP / "work" / "2026-01-03" / "e2e-fail" / "status.json")
        self.assertEqual(st["status"], "FAILED")
        self.assertFalse((TMP / "out" / "2026-01-03").exists(), "nada é entregue quando falha")

    def test_daily_routine_three_distinct_videos_with_fallback(self):
        import scheduler as S
        calls = {"n": 0}

        def flaky(brief, cfg, job_id, **kw):  # a 1ª tentativa do 1º slot falha: deve haver nova tentativa
            calls["n"] += 1
            if calls["n"] == 1:
                raise PipelineError("falha simulada")
            return build_video(brief, cfg, job_id, **kw)
        out = TMP / "out-daily"
        # 4 produtos no catálogo para provar a variedade; reaproveita as fotos de teste
        cat = load_json(TMP / "fx" / "catalog.json")
        p4 = copy.deepcopy(cat["products"][0])
        p4.update({"id": "teste-004", "name": "PRODUTO TESTE QUATRO"})
        cat["products"].append(p4)
        save_json(TMP / "fx" / "catalog4.json", cat)
        res = S.run_daily(self.cfg, day="2026-02-01", catalog=TMP / "fx" / "catalog4.json", voice_mode="off",
                          out_root=out, build_fn=flaky, now_fn=lambda: __import__("datetime").datetime(2026, 2, 1, 3, 0))
        self.assertEqual(res["ready"], 3, res)
        self.assertEqual(res["exit_code"], 0)
        files = sorted((out / "2026-02-01").glob("video_*.mp4"))
        self.assertEqual(len(files), 3)
        arche = [v["arquetipo"] for v in res["videos"]]
        prods = [v["produto"] for v in res["videos"]]
        self.assertEqual(len(set(arche)), 3, f"arquétipos repetidos: {arche}")
        self.assertEqual(len(set(prods)), 3)
        self.assertTrue(res["errors"], "a falha simulada foi registrada")
        # idempotência: rodar de novo não gera mais vídeos
        again = S.run_daily(self.cfg, day="2026-02-01", catalog=TMP / "fx" / "catalog4.json", voice_mode="off", out_root=out,
                            now_fn=lambda: __import__("datetime").datetime(2026, 2, 1, 5, 0))
        self.assertEqual(again["videos"], [])
        from common import logs_dir
        daily = load_json(logs_dir() / "daily-2026-02-01.json")
        self.assertEqual(daily["ready"], 3, "a rodada de recuperação (sem nada a fazer) não pode zerar o resumo do dia")
        self.assertEqual(again["ready"], 3)
        self.assertEqual(len(daily["videos"]), 3)
        self.assertGreaterEqual(len(daily["runs"]), 2)
        self.assertEqual(len(list((out / "2026-02-01").glob("video_*.mp4"))), 3)
        # dia seguinte: evita repetir os produtos de ontem quando há alternativa
        st = S.load_state(self.cfg)
        self.assertEqual(len(st["days"]["2026-02-01"]["slots"]), 3)

    def test_catch_up_after_deadline(self):
        """PC ligou depois das 08:00: retoma e produz o que falta (marcado como atrasado)."""
        import scheduler as S
        late = lambda: __import__("datetime").datetime(2026, 3, 1, 8, 30)
        res = S.run_daily(self.cfg, day="2026-03-01", count=1, catalog=TMP / "fx" / "catalog.json", voice_mode="off",
                          out_root=TMP / "out-late", now_fn=late)
        self.assertEqual(res["ready"], 1)
        self.assertTrue(res["late"])
        cfg2 = copy.deepcopy(self.cfg)
        cfg2["daily"]["catch_up_after_deadline"] = False
        res2 = S.run_daily(cfg2, day="2026-03-02", count=1, catalog=TMP / "fx" / "catalog.json", voice_mode="off",
                           out_root=TMP / "out-late", now_fn=late)
        self.assertEqual(res2["ready"], 0)
        self.assertTrue(all(s["motivo"] == "prazo" for s in res2["skipped"]))

    def test_resume_after_power_loss(self):
        """Queda de energia no meio: trava abandonada + job pela metade + cópia incompleta não impedem a retomada."""
        import scheduler as S
        from common import work_dir
        day, out = "2026-05-01", TMP / "out-resume"
        wd = work_dir(self.cfg)
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "daily.lock").write_text(json.dumps({"pid": 2 ** 22 + 12345, "since": "x"}))      # processo que não existe mais
        job = wd / day / "job-interrompido"
        job.mkdir(parents=True)
        save_json(job / "status.json", {"job_id": "job-interrompido", "status": "RENDERING", "history": [], "meta": {}})
        (out / day).mkdir(parents=True)
        (out / day / "video_01_x.mp4.partial").write_bytes(b"lixo")
        res = S.run_daily(self.cfg, day=day, count=1, catalog=TMP / "fx" / "catalog.json", voice_mode="off", out_root=out,
                          now_fn=lambda: __import__("datetime").datetime(2026, 5, 1, 2, 0))
        self.assertEqual(res["ready"], 1)
        self.assertFalse(list((out / day).glob("*.partial")), "cópia incompleta foi limpa")
        # mesmo job_id de uma execução interrompida: recomeça limpo em vez de falhar
        brief = self.brief(0)
        wd2 = work_dir(self.cfg) / "2026-05-02" / "mesmo-id"
        wd2.mkdir(parents=True)
        save_json(wd2 / "status.json", {"job_id": "mesmo-id", "status": "VALIDATING", "history": [], "meta": {}})
        r = build_video(brief, self.cfg, "mesmo-id", day="2026-05-02", seed=1, voice_mode="off", deliver_output=False)
        self.assertEqual(r["status"], "READY")

    def test_not_enough_products_does_not_invent(self):
        import scheduler as S
        one = load_json(TMP / "fx" / "catalog.json")
        one["products"] = one["products"][:1]
        save_json(TMP / "fx" / "catalog1.json", one)
        res = S.run_daily(self.cfg, day="2026-04-01", catalog=TMP / "fx" / "catalog1.json", voice_mode="off", out_root=TMP / "out-one",
                          now_fn=lambda: __import__("datetime").datetime(2026, 4, 1, 3, 0))
        self.assertEqual(res["ready"], 1)
        self.assertEqual(res["exit_code"], 2)
        self.assertEqual(len(res["skipped"]), 2)

    def test_task_xml(self):
        import scheduler as S
        xml = S.task_xml(r"C:\Python312\pythonw.exe", self.cfg, "02:00", "05:00")
        for needle in ("T02:00:00", "T05:00:00", "<WakeToRun>true", "<StartWhenAvailable>true", "run-daily", "IgnoreNew", "InteractiveToken"):
            self.assertIn(needle, xml)
        import xml.dom.minidom as md
        md.parseString(xml.split("?>", 1)[1])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
