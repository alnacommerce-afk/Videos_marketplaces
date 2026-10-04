"""Renderer: compõe os quadros com Pillow/numpy e entrega ao FFmpeg (H.264 + AAC).

Pillow cuida da composição (câmera, texto, transições); o FFmpeg é a ferramenta principal de
codificação: recebe vídeo cru por pipe + o WAV já mixado, normaliza o loudness e grava o MP4
(+faststart, yuv420p, perfil High).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

import graphics as g
from camera import ease_in_out, view_box
from common import Logger, PipelineError, ffprobe_json, fonts_dir, load_styles, run, save_json, which_tool

BG_MARGIN = 60


def _clamp01(x):
    return min(max(x, 0.0), 1.0)


class ClipSource:
    """Lê um clipe de vídeo quadro a quadro (FFmpeg → RGB), já em 9:16.
    Vertical: preenche o quadro. Horizontal 4K: recorta um vertical nítido do centro. Horizontal menor: clipe centralizado
    sobre uma cópia desfocada (evita ampliar demais e ficar mole). O áudio do clipe é ignorado."""

    def __init__(self, path: str, W: int, H: int, fps: int, start: float = 0.4):
        self.path, self.W, self.H, self.fps, self.start = path, W, H, fps, start
        info = ffprobe_json(path)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.w, self.h = int(v["width"]), int(v["height"])
        self.dur = float(info["format"].get("duration", 0))
        self.proc, self.next_idx, self.last, self.eof = None, 0, None, False

    def vf(self) -> str:
        W, H, fps = self.W, self.H, self.fps
        if self.h >= self.w:
            return f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        if self.w >= 3000:
            return f"fps={fps},crop=ih*{W}/{H}:ih,scale={W}:{H}"
        return (f"fps={fps},split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=30:3,eq=brightness=-0.08[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")

    def _cmd(self, ss: float, frames: int | None = None) -> list[str]:
        cmd = [which_tool("ffmpeg"), "-v", "error", "-ss", f"{ss:.3f}", "-i", self.path, "-an", "-vf", self.vf()]
        if frames:
            cmd += ["-frames:v", str(frames)]
        return cmd + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]

    def _start(self):
        self.close()
        self.proc = subprocess.Popen(self._cmd(self.start), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.next_idx, self.eof = 0, False

    def read(self, idx: int) -> Image.Image:
        """Quadro `idx` (sequencial). Depois do fim do clipe, congela o último quadro."""
        if self.proc is None or idx < self.next_idx - 1:
            self._start()
        n = self.W * self.H * 3
        while self.next_idx <= idx and not self.eof:
            buf = self.proc.stdout.read(n)
            if len(buf) < n:
                self.eof = True
                break
            self.last, self.next_idx = buf, self.next_idx + 1
        if self.last is None:
            raise PipelineError(f"Clipe sem quadros legíveis: {self.path}")
        return Image.frombytes("RGB", (self.W, self.H), self.last)

    def peek(self, t: float) -> Image.Image:
        """Um quadro em t segundos, sem mexer na leitura sequencial (usado nas medições de contraste)."""
        res = run(self._cmd(min(self.start + max(t, 0), max(self.dur - 0.2, 0)), frames=1), check=False)
        n = self.W * self.H * 3
        if len(res.stdout) < n:
            raise PipelineError(f"Não consegui ler um quadro de {self.path}")
        return Image.frombytes("RGB", (self.W, self.H), res.stdout[:n])

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.stdout.close()
            except Exception:
                pass
            self.proc = None


class Renderer:
    def __init__(self, sb: dict, cfg: dict, logger: Logger | None = None):
        self.sb, self.cfg = sb, cfg
        self.log = logger or Logger(echo=False)
        f = sb["format"]
        self.W, self.H, self.fps = f["width"], f["height"], f["fps"]
        self.safe = f["safe"]
        self.style = load_styles()[sb["strategy"]["style"]]
        self.font_path, self.font_family = g.find_font(cfg, fonts_dir(cfg), bold=True)
        self.ctx = {"W": self.W, "H": self.H, "safe": self.safe, "font": self.font_path, "style": self.style}
        self.shade = g.gradient_overlay(self.W, self.H, bottom=self.style["grad_bottom"], top=0.16,
                                        dim=0.0, vignette=self.style["vignette"])
        self._photos: dict[str, Image.Image] = {}
        self._clips: dict[int, ClipSource] = {}
        self._bgs: dict[int, Image.Image] = {}
        self.scenes = sb["scenes"]
        self.layers: dict[int, list[g.Layer]] = {}
        self.report = {"font": self.font_family, "scenes": []}
        self._build_layers()

    # -- imagens --------------------------------------------------------------
    def photo(self, path: str) -> Image.Image:
        if path not in self._photos:
            im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            if max(im.size) > 2600:
                im.thumbnail((2600, 2600), Image.LANCZOS)
            im = ImageEnhance.Color(im).enhance(self.style.get("saturation", 1.0))
            self._photos[path] = im
        return self._photos[path]

    def background(self, j: int) -> Image.Image:
        """Fundo para quando a foto não preenche o quadro: cor das bordas da foto (gradiente suave)
        misturada com a própria foto muito desfocada. Evita o 'halo' do produto vazando para o fundo."""
        if j not in self._bgs:
            im = self.photo(self.scenes[j]["image"])
            W, H, m = self.W, self.H, BG_MARGIN
            tw, th = W + 2 * m, H + 2 * m
            thumb = np.asarray(im.resize((64, max(8, int(64 * im.height / im.width))), Image.BILINEAR), dtype=np.float32)
            edge = np.concatenate([thumb[:3].reshape(-1, 3), thumb[-3:].reshape(-1, 3),
                                   thumb[:, :3].reshape(-1, 3), thumb[:, -3:].reshape(-1, 3)])
            col = np.median(edge, axis=0)
            ramp = np.linspace(1.05, 0.88, th, dtype=np.float32)[:, None, None]
            solid = np.clip(col[None, None, :] * ramp, 0, 255) * np.ones((th, tw, 1), dtype=np.float32)
            s = max(tw / im.width, th / im.height)
            small = im.resize((max(1, int(im.width * s / 8)), max(1, int(im.height * s / 8))), Image.BILINEAR)
            small = small.filter(ImageFilter.GaussianBlur(14))
            big = small.resize((int(im.width * s), int(im.height * s)), Image.BICUBIC)
            l, t = (big.width - tw) // 2, (big.height - th) // 2
            blur = np.asarray(big.crop((l, t, l + tw, t + th)), dtype=np.float32)
            bg = Image.fromarray((solid * 0.72 + blur * 0.28).astype("uint8"))
            dim = self.style["bg_dim"]
            if dim > 0:
                bg = Image.blend(bg, Image.new("RGB", bg.size, (8, 8, 10)), dim)
            self._bgs[j] = bg
        return self._bgs[j]

    def _feather(self, dest: tuple, edge: int = 34) -> Image.Image | None:
        """Máscara com bordas suaves nos lados da foto que NÃO encostam na borda do quadro."""
        dx, dy, dw, dh = dest
        sides = (dx > 1, dx + dw < self.W - 1, dy > 1, dy + dh < self.H - 1)  # esq, dir, topo, base
        if not any(sides):
            return None
        e = min(edge, dw // 3, dh // 3)
        x = np.ones(dw, dtype=np.float32)
        y = np.ones(dh, dtype=np.float32)
        ramp = np.linspace(0, 1, e, dtype=np.float32)
        if sides[0]:
            x[:e] = ramp
        if sides[1]:
            x[-e:] = np.minimum(x[-e:], ramp[::-1])
        if sides[2]:
            y[:e] = ramp
        if sides[3]:
            y[-e:] = np.minimum(y[-e:], ramp[::-1])
        return Image.fromarray((np.outer(y, x) * 255).astype("uint8"), "L")

    # -- quadro de uma cena -----------------------------------------------------
    def _tw(self, j: int) -> float:
        return self.scenes[j]["transition_in"]["duration"] or 0.0

    def _clip(self, j: int) -> ClipSource:
        if j not in self._clips:
            self._clips[j] = ClipSource(self.scenes[j]["clip"]["path"], self.W, self.H, self.fps)
        return self._clips[j]

    def photo_frame(self, j: int, tau: float, peek: bool = False) -> Image.Image:
        sc = self.scenes[j]
        if sc.get("clip"):  # cena de b-roll: o quadro vem do vídeo
            src = self._clip(j)
            frame = src.peek(tau) if peek else src.read(max(0, int(tau * self.fps)))
            return ImageChops.multiply(frame, self.shade)
        total = sc["duration"] + self._tw(j)
        p = _clamp01(tau / total)
        cam = sc["camera"]
        im = self.photo(sc["image"])
        bg = self.background(j)
        sx = int((p - 0.5) * 44) if cam.get("parallax") else 0
        m = BG_MARGIN
        frame = bg.crop((m + sx, m, m + sx + self.W, m + self.H))
        vb = view_box(cam, p, im.size, self.W, self.H)
        x0, y0, x1, y1 = vb["src"]
        dx, dy, dw, dh = vb["dest"]
        resample = Image.BICUBIC if vb["scale"] >= 1.0 else Image.LANCZOS
        crop = im.resize((dw, dh), resample, box=(x0, y0, x1, y1))
        frame.paste(crop, (dx, dy), self._feather(vb["dest"]))
        if sc.get("focus_pull") and tau < 0.65:
            r = 18 * (1 - ease_in_out(tau / 0.65))
            if r > 0.4:
                frame = frame.filter(ImageFilter.GaussianBlur(r))
        return ImageChops.multiply(frame, self.shade)

    def scene_frame(self, j: int, tau: float) -> Image.Image:
        frame = self.photo_frame(j, tau)
        t_local = tau - self._tw(j)
        for layer in self.layers.get(j, []):
            layer.draw(frame, t_local)
        return frame

    # -- camadas de texto ---------------------------------------------------------
    def _make_layer(self, j: int, sc: dict) -> g.Layer | None:
        tx = sc["text"]
        if not tx:
            return None
        role, text, ctx = tx["role"], tx["text"], self.ctx
        anim, t_in = tx.get("anim", "fade"), tx.get("t_in", 0.25)
        label = None
        if tx.get("label"):
            from storyboard import KIND_LABEL
            label = KIND_LABEL.get(tx["label"].split(":", 1)[1])
        odd = sc["index"] % 2 == 1
        if role == "headline":
            return g.text_card(text, ctx, "top", anim=anim, t_in=t_in)
        if role == "name":
            return g.text_card(text, ctx, "bottom", size=92, max_lines=3, align="left", anim=anim, t_in=t_in, role="name")
        if role == "fact":
            return g.lower_third(text, ctx, anim="slide" if anim not in ("fade", "mask") else anim, t_in=t_in) if odd \
                else g.product_callout(text, ctx, anim="scale" if anim == "slide" else anim, t_in=t_in)
        if role == "card":
            return (g.benefit_card if odd else g.feature_card)(text, label, ctx, anim=anim if anim in ("slide", "fade", "scale", "mask") else "slide", t_in=t_in)
        if role == "cta":
            return g.cta_button(text, ctx, anim="scale" if anim not in ("fade",) else "fade", t_in=t_in)
        return None

    def _ensure_contrast(self, j: int, layer: g.Layer) -> dict:
        """Mede o contraste real do texto contra a foto (no instante em que a animação termina). Se for
        baixo e o texto não tiver cartão próprio, coloca uma placa translúcida escura atrás."""
        info = {"scene": j + 1, "role": layer.role, "text": layer.text, "plate": False}
        tau = self._tw(j) + layer.t_in + layer.dur_in + 0.05
        tau = min(tau, self.scenes[j]["duration"] + self._tw(j) - 0.02)
        base = self.photo_frame(j, tau, peek=True)
        x, y, w, h = layer.bbox
        region = base.crop((max(x, 0), max(y, 0), min(x + w, self.W), min(y + h, self.H)))
        mean = tuple(np.asarray(region, dtype=np.float32).reshape(-1, 3).mean(axis=0))
        if layer.card_rgba:
            a = layer.card_rgba[3] / 255.0
            bgc = tuple(layer.card_rgba[i] * a + mean[i] * (1 - a) for i in range(3))
        else:
            bgc = mean
        ratio = g.contrast_ratio(layer.text_rgb, bgc)
        info["contrast_before"] = round(ratio, 2)
        if ratio < 4.5 and not layer.card_rgba:
            pad = 30
            plate = Image.new("RGBA", (layer.surf.width + 2 * pad, layer.surf.height + 2 * pad), (0, 0, 0, 0))
            ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=34, fill=(10, 10, 14, 188))
            plate.alpha_composite(layer.surf, (pad, pad))
            layer.x = min(max(layer.x - pad, self.safe["left"]), self.W - self.safe["right"] - plate.width)
            ny = min(layer.y - pad, self.H - self.safe["bottom"] - plate.height)  # a placa nunca invade a safe area
            layer.y = max(ny, self.safe["top"])
            layer.surf, layer.card_rgba = plate, (10, 10, 14, 188)
            layer.anim = "scale" if layer.anim in ("words", "staggered", "kinetic", "tracking", "mask") else layer.anim
            layer.words, layer.tracking = [], None
            info["plate"] = True
            bgc = tuple(10 * 0.74 + mean[i] * 0.26 for i in range(3))
            ratio = g.contrast_ratio(layer.text_rgb, bgc)
        info["contrast"] = round(ratio, 2)
        return info

    def _build_layers(self) -> None:
        for j, sc in enumerate(self.scenes):
            layers = []
            main = self._make_layer(j, sc)
            if main:
                layers.append(main)
            if sc.get("illustrative"):  # cena de b-roll: rótulo obrigatório
                layers.append(g.badge(self.cfg["broll"]["label"], self.ctx, "top", "fade", 0.1))
            entry = {"scene": sc["index"], "layers": []}
            for layer in layers:
                info = self._ensure_contrast(j, layer)
                x, y, w, h = layer.bbox
                info.update({"bbox": [x, y, w, h], "font_px": layer.font_px, "t_in": layer.t_in,
                             "visible_until_end": True, "anim": layer.anim})
                entry["layers"].append(info)
            if layers:
                self.layers[j] = layers
            self.report["scenes"].append(entry)

    # -- transições ---------------------------------------------------------------
    def _zoom(self, im: Image.Image, s: float) -> Image.Image:
        if abs(s - 1) < 1e-3:
            return im
        w, h = im.size
        cw, ch = w / s, h / s
        return im.resize((w, h), Image.BILINEAR, box=((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2))

    def _hblur(self, im: Image.Image, k: int) -> Image.Image:
        if k < 2:
            return im
        a = np.asarray(im, dtype=np.float32)
        acc = np.zeros_like(a)
        shifts = np.linspace(-k, k, 7).astype(int)
        for s in shifts:
            acc += np.roll(a, s, axis=1)
        return Image.fromarray((acc / len(shifts)).astype("uint8"))

    def transition(self, kind: str, A: Image.Image, B: Image.Image, p: float, direction: int = 1) -> Image.Image:
        W, H = self.W, self.H
        e = ease_in_out(p)
        if kind in ("dissolve", "cross_dissolve"):
            return Image.blend(A, B, e)
        if kind == "fade":
            black = Image.new("RGB", (W, H), (0, 0, 0))
            return Image.blend(A, black, p * 2) if p < 0.5 else Image.blend(black, B, (p - 0.5) * 2)
        if kind == "zoom":
            return Image.blend(self._zoom(A, 1 + 0.45 * e), self._zoom(B, 1.45 - 0.45 * e), e)
        if kind in ("whip", "motion"):
            canvas = Image.new("RGB", (W, H))
            off = int(W * e)  # direction=+1: a câmera segue para a direita (A sai pela esquerda); -1: o contrário
            canvas.paste(A, (-direction * off, 0))
            canvas.paste(B, (direction * (W - off), 0))
            return self._hblur(canvas, int((70 if kind == "whip" else 28) * np.sin(np.pi * p)))
        if kind == "directional_wipe":
            xs = np.arange(W, dtype=np.float32)[None, :]
            edge, soft = e * (W + 200) - 100, 90.0
            m = np.clip((edge - xs) / soft + 0.5, 0, 1)
            if direction < 0:
                m = m[:, ::-1]
            mask = Image.fromarray((np.repeat(m, H, axis=0) * 255).astype("uint8"), "L")
            return Image.composite(B, A, mask)
        if kind == "mask_reveal":
            mask = Image.new("L", (W, H), 0)
            r = e * (W ** 2 + H ** 2) ** 0.5 / 2
            ImageDraw.Draw(mask).ellipse((W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r), fill=255)
            return Image.composite(B, A, mask.filter(ImageFilter.GaussianBlur(6)))
        if kind == "blur":
            a = A.filter(ImageFilter.GaussianBlur(26 * e)) if e > 0.02 else A
            b = B.filter(ImageFilter.GaussianBlur(26 * (1 - e))) if e < 0.98 else B
            return Image.blend(a, b, e)
        if kind == "light_sweep":
            base = Image.blend(A, B, e)
            xs = np.arange(W, dtype=np.float32)[None, :]
            ys = np.arange(H, dtype=np.float32)[:, None]
            pos = e * (W + H * 0.6 + 500) - 250
            d = xs + ys * 0.5 - pos
            band = np.exp(-(d / 130.0) ** 2) * 0.55 * np.sin(np.pi * p)
            add = Image.fromarray((np.repeat(band[:, :, None], 3, axis=2) * 255).astype("uint8"), "RGB")
            return ImageChops.add(base, add)
        if kind == "speed_ramp":
            def zb(im, s):
                acc = None
                for k in range(5):
                    z = self._zoom(im, 1 + (s - 1) * (k / 4))
                    a = np.asarray(z, dtype=np.float32)
                    acc = a if acc is None else acc + a
                return Image.fromarray((acc / 5).astype("uint8"))
            return zb(A, 1 + 0.55 * e * 2) if p < 0.5 else zb(B, 1 + 0.55 * (1 - e) * 2)
        return B if p >= 0.5 else A  # hard_cut / match_cut / desconhecido

    # -- linha do tempo ----------------------------------------------------------
    def frame_at(self, t: float) -> Image.Image:
        sc = self.scenes
        j = 0
        for k, s in enumerate(sc):
            if t >= s["start"] - 1e-9:
                j = k
        tau = t - (sc[j]["start"] - self._tw(j))
        nxt = j + 1 if j + 1 < len(sc) else None
        if nxt is not None:
            tw = self._tw(nxt)
            if tw > 0 and t >= sc[nxt]["start"] - tw:
                p = (t - (sc[nxt]["start"] - tw)) / tw
                A = self.scene_frame(j, tau)
                B = self.scene_frame(nxt, t - (sc[nxt]["start"] - tw))
                return self.transition(sc[nxt]["transition_in"]["type"], A, B, _clamp01(p), sc[nxt]["transition_in"].get("direction", 1))
        return self.scene_frame(j, max(tau, 0.0))

    # -- render final -------------------------------------------------------------
    def render(self, out_mp4: Path, audio_wav: Path, loudnorm_filter: str, progress_every: int = 90) -> dict:
        ff = which_tool("ffmpeg")
        enc = self.cfg["encode"]
        D = self.sb["total_duration"]
        nframes = int(round(D * self.fps))
        out_mp4 = Path(out_mp4)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_mp4.with_name(out_mp4.stem + ".partial.mp4")
        cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.W}x{self.H}",
               "-r", str(self.fps), "-i", "-", "-i", str(audio_wav), "-map", "0:v:0", "-map", "1:a:0",
               "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
               "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]), "-profile:v", "high", "-level", "4.1",
               "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-r", str(self.fps), "-g", str(self.fps * 2),
               "-af", loudnorm_filter + f",aresample={self.cfg['audio']['sample_rate']}",
               "-c:a", "aac", "-b:a", enc["audio_bitrate"], "-ar", str(self.cfg["audio"]["sample_rate"]), "-ac", "2",
               "-t", f"{D:.3f}", "-movflags", "+faststart", "-f", "mp4", str(tmp)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        thumbs = []
        mids = {int(round((s["start"] + s["duration"] * 0.7) * self.fps)): s["index"] for s in self.scenes}
        try:
            for i in range(nframes):
                t = i / self.fps
                fr = self.frame_at(t)
                proc.stdin.write(fr.tobytes())
                if i in mids:
                    th = fr.copy()
                    th.thumbnail((270, 480))
                    thumbs.append(th)
                if i and i % progress_every == 0:
                    self.log.info("renderizando", quadro=f"{i}/{nframes}")
            proc.stdin.close()
            err = proc.stderr.read().decode("utf-8", "replace")
            if proc.wait() != 0:
                raise PipelineError(f"FFmpeg falhou ao codificar:\n{err[-1500:]}")
        except BrokenPipeError:
            err = proc.stderr.read().decode("utf-8", "replace")
            raise PipelineError(f"FFmpeg encerrou antes do fim:\n{err[-1500:]}")
        except Exception:
            proc.kill()
            tmp.unlink(missing_ok=True)
            raise
        finally:
            for c in self._clips.values():
                c.close()
        tmp.replace(out_mp4)
        sheet = None
        if thumbs:
            cols = min(len(thumbs), 4)
            rows = (len(thumbs) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * 270, rows * 480), (20, 20, 20))
            for k, th in enumerate(thumbs):
                sheet.paste(th, ((k % cols) * 270, (k // cols) * 480))
            sheet.save(out_mp4.with_suffix(".contact.jpg"), quality=88)
        self.report.update({"frames": nframes, "fps": self.fps, "size": [self.W, self.H], "duration": D,
                            "safe_area": self.safe, "output": str(out_mp4)})
        return self.report
