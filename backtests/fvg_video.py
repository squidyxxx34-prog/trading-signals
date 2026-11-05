"""Vidéo verticale 1080x1920 : le FVG pas à pas sur 2 vraies séquences XAUUSD H4."""
import json, sys, subprocess, os, math, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(OUT, exist_ok=True)
D = json.load(open("fvg_anim.json"))
FD = "/usr/share/fonts/opentype/inter/"
def F(w, s): return ImageFont.truetype(FD + {"b": "Inter-Bold.otf", "s": "Inter-SemiBold.otf", "r": "Inter-Regular.otf", "d": "InterDisplay-Bold.otf" if os.path.exists(FD + "InterDisplay-Bold.otf") else "Inter-Bold.otf"}[w], s)
M = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 26)
MB = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 30)
BG = (13, 18, 24); PANEL = (20, 28, 37); RULE = (36, 49, 64); INK = (229, 236, 242); MUT = (147, 161, 176)
UP = (43, 197, 154); DN = (240, 101, 122); BLUE = (124, 156, 255); GOLD = (240, 180, 60)

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x) ** 3

def steps(e, kind):
    d = e["dec"]; f = lambda v: f"{v:.{d}f}"; risk = e["top"] - e["sl"]; size = e["top"] - e["bot"]
    s = [
        dict(upto=e["g"] - 3, t="Le marché avant", x=f"Or (XAUUSD), bougies de 4h,\n{e['date'][8:10]}/{e['date'][5:7]}/{e['date'][:4]}. Pas encore de FVG."),
        dict(upto=e["g"] - 2, m1=1, t="Bougie 1", x=f"On note son PLUS HAUT :\n{f(e['bot'])} $"),
        dict(upto=e["g"] - 1, m1=1, t="Bougie 2 = l'impulsion", x="Une grosse bougie part d'un coup.\nLe prix monte trop vite."),
        dict(upto=e["g"], m1=1, m3=1, t="Bougie 3", x=f"On note son PLUS BAS :\n{f(e['top'])} $ (au-dessus de la bougie 1)"),
        dict(upto=e["g"], gap=1, t="Le trou = le FVG", x=f"Entre {f(e['bot'])} et {f(e['top'])}\nsoit {size:.1f} $ de vide. Milieu (CE) : {f(e['ce'])}"),
        dict(upto=e["k"] - 1, gap=1, t="On ne court pas après", x=f"Ordre LIMITE posé au haut du FVG\n({f(e['top'])}). On attend le retour."),
        dict(upto=e["k"], gap=1, tr=1, t="Retour : ordre rempli", x=f"Achat {f(e['top'])}  ·  Stop {f(e['sl'])}\nRisque {risk:.1f} $  ·  Objectif 2R {f(e['tp'])}"),
    ]
    if kind == "win":
        s.append(dict(upto=e["m"], gap=1, tr=1, done="TP", t="Le FVG tient : +2R", x=f"La zone sert de support.\nObjectif {f(e['tp'])} touché = 2× le risque."))
    else:
        s += [dict(upto=e["inv"], gap=1, tr=1, t="Clôture SOUS le FVG", x=f"Une bougie ferme sous {f(e['bot'])}.\nLes acheteurs ne défendent plus la zone."),
              dict(upto=e["m"], gap=1, inv=1, tr=1, done="SL", t="Stop touché : −1R", x=f"Stop {f(e['sl'])} touché.\nPerte limitée à 1R grâce au stop."),
              dict(upto=len(e["ohlc"]) - 1, gap=1, inv=1, tr=1, done="SL", t="Le FVG devient un iFVG", x="La zone change de rôle :\nelle devient une RÉSISTANCE.")]
    t = 0.0
    prev = -1
    for st in s:
        n_new = max(0, st["upto"] - prev)
        st["start"] = t; st["reveal"] = n_new / 7.0; st["dur"] = max(3.2, st["reveal"] + 2.6); st["from"] = prev + 1
        t += st["dur"]; prev = st["upto"]
    return s, t

def rr(d, box, r, fill=None, outline=None, width=1): d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)
def blend(c, a, bg=BG): return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))

def dashed(d, x0, x1, y, col, w=3, on=16, off=10):
    x = x0
    while x < x1: d.line([x, y, min(x + on, x1), y], fill=col, width=w); x += on + off

def draw_scene_frame(e, kind, S, t, label):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im, "RGBA")
    i = max(k for k, st in enumerate(S) if st["start"] <= t) if t >= 0 else 0; st = S[i]; lt = t - st["start"]
    vis = min(st["upto"] + 1, st["from"] + int(lt * 7) + 1) if lt < st["reveal"] else st["upto"] + 1
    # en-tête
    d.text((60, 70), label, font=F("s", 30), fill=BLUE)
    d.text((60, 112), "Le FVG", font=F("b", 84), fill=INK)
    d.text((60, 214), "Fair Value Gap · XAUUSD · H4 · vraies bougies", font=F("r", 32), fill=MUT)
    # graphique
    o = e["ohlc"]; n = len(o); X0, X1, Y0, Y1 = 50, 880, 330, 1290
    lo = min(min(r[2] for r in o), e["sl"]); hi = max(max(r[1] for r in o), e["tp"]); pad = (hi - lo) * .05; lo -= pad; hi += pad
    cw = (X1 - X0) / n; X = lambda j: X0 + cw * (j + .5); XL = lambda j: X0 + cw * j; Y = lambda v: Y0 + (Y1 - Y0) * (hi - v) / (hi - lo)
    rr(d, [30, 300, W - 30, 1320], 24, fill=PANEL)
    for k in range(5):
        v = lo + (hi - lo) * k / 4; y = Y(v); d.line([X0, y, X1, y], fill=RULE, width=2); d.text((X1 + 18, y - 14), f"{v:.0f}", font=M, fill=MUT)
    fa = ease(lt / .5)
    def first(flag): return next(k for k, s_ in enumerate(S) if s_.get(flag))
    if st.get("gap"):
        a = fa if i == first("gap") else 1
        inv = st.get("inv"); ia = (fa if i == first("inv") else 1) if inv else 0
        col = tuple(int(BLUE[c] + (DN[c] - BLUE[c]) * ia) for c in range(3))
        x0 = XL(e["g"] - 2); x1 = XL(max(vis, e["g"] + 1)) + 6
        d.rectangle([x0, Y(e["top"]), x1, Y(e["bot"])], fill=col + (int(60 * a),), outline=col + (int(255 * a),), width=3)
        dashed(d, x0, x1, Y(e["ce"]), col + (int(200 * a),), w=2, on=8, off=8)
        d.text((x0 + 8, Y(e["bot"]) + 8), "iFVG = résistance" if inv and ia > .5 else "FVG", font=F("b", 32), fill=col + (int(255 * a),))
    if st.get("tr"):
        a = fa if i == first("tr") else 1; xk = X(e["k"])
        for v, c, txt in [(e["top"], GOLD, f"entrée {e['top']:.1f}"), (e["sl"], DN, f"stop {e['sl']:.1f}"), (e["tp"], UP, f"objectif 2R {e['tp']:.1f}")]:
            cc = c + (int(255 * a),)
            if c == GOLD: d.line([xk, Y(v), X1, Y(v)], fill=cc, width=4)
            else: dashed(d, xk, X1, Y(v), cc, w=4)
            tw = d.textlength(txt, font=F("s", 28)); d.text((X1 - tw, Y(v) - (40 if c != DN else -10)), txt, font=F("s", 28), fill=cc)
    bw = max(4, cw * .62); ww = max(2, cw * .14)
    for j in range(min(vis, n)):
        r = o[j]; up = r[3] >= r[0]; c = UP if up else DN; x = X(j)
        pop = 1.0
        if j == vis - 1 and lt < st["reveal"] + .2: pop = ease((lt * 7) % 1 / .6)
        y0, y1 = Y(max(r[0], r[3])), Y(min(r[0], r[3])); mid = (y0 + y1) / 2
        d.line([x, Y(r[1]), x, Y(r[2])], fill=c, width=int(ww))
        hh = max(2, (y1 - y0) * pop)
        hl = (st.get("m1") or (st.get("gap") and i < 5)) and e["g"] - 2 <= j <= e["g"] and i < 5
        d.rectangle([x - bw / 2, mid - hh / 2, x + bw / 2, mid + hh / 2], fill=c, outline=INK if hl else None, width=3 if hl else 0)
    if st.get("m1") and i < 5:
        r = o[e["g"] - 2]; y = Y(r[1]); a = fa if i == 1 else 1
        d.line([X(e["g"] - 2) - 30, y, X(e["g"] + 3), y], fill=BLUE + (int(255 * a),), width=4)
        d.text((X(e["g"] - 2) - 30, y + 10), f"haut 1 : {r[1]:.1f}", font=F("s", 30), fill=BLUE + (int(255 * a),))
    if st.get("m3") and i < 5:
        r = o[e["g"]]; y = Y(r[2]); a = fa
        d.line([X(e["g"] - 3), y, X(e["g"]) + 30, y], fill=BLUE + (int(255 * a),), width=4)
        d.text((X(e["g"]) - 40, y - 46), f"bas 3 : {r[2]:.1f}", font=F("s", 30), fill=BLUE + (int(255 * a),))
    if (st.get("m1") or st.get("m3")) and i < 4:
        for k, j in enumerate([e["g"] - 2, e["g"] - 1, e["g"]]):
            if j < vis:
                d.ellipse([X(j) - 22, Y(o[j][2]) + 26, X(j) + 22, Y(o[j][2]) + 70], fill=INK); d.text((X(j), Y(o[j][2]) + 48), str(k + 1), font=F("b", 30), fill=BG, anchor="mm")
    if st.get("tr") and vis > e["k"]:
        x = X(e["k"]); y = Y(o[e["k"]][2]) + 18; d.polygon([(x, y), (x - 16, y + 26), (x + 16, y + 26)], fill=GOLD)
    if st.get("done") and vis > e["m"]:
        win = st["done"] == "TP"; a = ease((t - S[next(k for k, s_ in enumerate(S) if s_.get("done"))]["start"] - st["reveal"]) / .4) if i == next(k for k, s_ in enumerate(S) if s_.get("done")) else 1
        txt = "+2R ✓" if win else "−1R"; c = UP if win else DN; sc = 1 + .25 * (1 - a)
        fnt = F("b", int(64 * sc)); xx = X(e["m"]); yy = Y(e["tp"]) - 120 if win else Y(e["sl"]) + 60
        tw = d.textlength(txt, font=fnt); rr(d, [xx - tw / 2 - 20, yy - 40 * sc, xx + tw / 2 + 20, yy + 44 * sc], 18, fill=BG + (230,), outline=c, width=4)
        d.text((xx, yy), txt, font=fnt, fill=c, anchor="mm")
    # légende / narration
    rr(d, [30, 1360, W - 30, 1800], 24, fill=PANEL)
    ca = ease(lt / .35); off = int(30 * (1 - ca))
    d.text((70, 1395 + off), f"ÉTAPE {i + 1} / {len(S)}", font=F("s", 28), fill=MUT + (int(255 * ca),))
    d.text((70, 1440 + off), st["t"], font=F("b", 58), fill=INK + (int(255 * ca),))
    for k, line in enumerate(st["x"].split("\n")):
        d.text((70, 1540 + off + k * 56), line, font=F("r", 42), fill=(200, 210, 220, int(255 * ca)))
    # barre de progression
    tot = S[-1]["start"] + S[-1]["dur"]; d.rounded_rectangle([60, 1840, W - 60, 1852], 6, fill=RULE); d.rounded_rectangle([60, 1840, 60 + (W - 120) * min(1, t / tot), 1852], 6, fill=BLUE)
    return im

def title_frame(t, dur):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im, "RGBA"); a = ease(t / .6); off = int(60 * (1 - a))
    d.text((80, 640 + off), "APPRENDRE EN 1 MINUTE", font=F("s", 36), fill=BLUE + (int(255 * a),))
    d.text((80, 700 + off), "Le FVG", font=F("b", 170), fill=INK + (int(255 * a),))
    d.text((80, 900 + off), "Fair Value Gap", font=F("s", 64), fill=MUT + (int(255 * a),))
    b = ease((t - .5) / .6)
    # bougie 1 (haut = 1270), bougie 2 (impulsion), bougie 3 (bas = 1210) : le trou est entre 1210 et 1270
    for k, (wt, bt, bb, wb) in enumerate([(1270, 1300, 1380, 1410), (1100, 1120, 1330, 1350), (1030, 1060, 1180, 1210)]):
        x = 300 + k * 160; c = UP + (int(255 * b),)
        d.line([x + 40, wt, x + 40, wb], fill=c, width=8); d.rectangle([x, bt, x + 80, bb], fill=c)
    g = ease((t - 1.1) / .5)
    d.rectangle([280, 1210, 800, 1270], fill=BLUE + (int(80 * g),), outline=BLUE + (int(255 * g),), width=4)
    d.text((820, 1218), "le trou", font=F("b", 40), fill=BLUE + (int(255 * g),))
    for k, lab in enumerate(["1", "2", "3"]):
        d.text((340 + k * 160, 1460), lab, font=F("b", 40), fill=MUT + (int(255 * b),), anchor="mm")
    d.text((80, 1560), "2 vraies séquences sur l'or (XAUUSD, 4h)", font=F("r", 40), fill=MUT + (int(255 * a),))
    return im

def outro_frame(t, dur):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im, "RGBA"); st = D["stats"]
    d.text((80, 260), "Ce que disent", font=F("b", 84), fill=INK); d.text((80, 360), f"{st['n']:,} FVG".replace(",", " "), font=F("b", 84), fill=BLUE)
    d.text((80, 480), "11 paires forex + or · 4h · 2012-2022", font=F("r", 36), fill=MUT)
    rows = [(st["win"], "gagnent à 2R", "il faut 33,3 % pour finir à zéro", GOLD),
            (st["top_win"], "si le prix touche juste le bord", "la zone tient mieux", UP),
            (st["ce_win"], "si le prix descend jusqu'au CE (50 %)", "la zone faiblit", DN)]
    for k, (v, l1, l2, c) in enumerate(rows):
        a = ease((t - .4 - k * .5) / .5); y = 640 + k * 300 + int(40 * (1 - a))
        rr(d, [60, y, W - 60, y + 250], 24, fill=PANEL + (int(255 * a),))
        d.text((100, y + 40), f"{v:.1f} %".replace(".", ","), font=F("b", 96), fill=c + (int(255 * a),))
        d.text((100, y + 155), l1, font=F("s", 40), fill=INK + (int(255 * a),)); d.text((100, y + 205), l2, font=F("r", 32), fill=MUT + (int(255 * a),))
    a = ease((t - 2.2) / .6)
    d.text((80, 1600), "Seul, le FVG = pile ou face.", font=F("b", 52), fill=INK + (int(255 * a),))
    d.text((80, 1680), "Il sert à placer l'entrée et le stop.", font=F("r", 44), fill=MUT + (int(255 * a),))
    return im

def encode(name, gen, dur):
    tmp = f"{OUT}/{name}.tmp.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-f", "mp4", tmp], stdin=subprocess.PIPE)
    for fi in range(int(dur * FPS)):
        p.stdin.write(gen(fi / FPS).tobytes())
    p.stdin.close(); assert p.wait() == 0
    os.replace(tmp, f"{OUT}/{name}.mp4")

SW, TW = steps(D["win"], "win"); SF, TF = steps(D["fail"], "fail")
INTRO, OUTRO = 3.5, 6.0
if __name__ == "__main__" and "--preview" in sys.argv:
    for nm, im in [("p_win_gap", draw_scene_frame(D["win"], "win", SW, SW[4]["start"] + 1.5, "EXEMPLE 1 · LE FVG TIENT")),
                   ("p_win_end", draw_scene_frame(D["win"], "win", SW, TW - .2, "EXEMPLE 1 · LE FVG TIENT")),
                   ("p_fail_end", draw_scene_frame(D["fail"], "fail", SF, TF - .2, "EXEMPLE 2 · LE FVG CASSE")),
                   ("p_intro", title_frame(3, INTRO)), ("p_outro", outro_frame(5.5, OUTRO))]:
        im.save(f"{OUT}/{nm}.jpg", quality=85)
    print("durées", INTRO, TW, TF, OUTRO)
elif __name__ == "__main__":
    encode("s0_intro", lambda t: title_frame(t, INTRO), INTRO)
    encode("s1_win", lambda t: draw_scene_frame(D["win"], "win", SW, t, "EXEMPLE 1 · LE FVG TIENT"), TW)
    encode("s2_fail", lambda t: draw_scene_frame(D["fail"], "fail", SF, t, "EXEMPLE 2 · LE FVG CASSE"), TF)
    encode("s3_outro", lambda t: outro_frame(t, OUTRO), OUTRO)
    # bruitages : whoosh à chaque étape, clic à l'entrée, carillon +2R, coup sourd −1R
    sr = 44100; total = INTRO + TW + TF + OUTRO; a = np.zeros(int(total * sr) + sr)
    rng = np.random.default_rng(1)
    def add(t0, sig):
        i = int(t0 * sr); a[i:i + len(sig)] += sig[:len(a) - i]
    def whoosh(d=.45):
        n = int(d * sr); x = rng.standard_normal(n); env = np.sin(np.linspace(0, np.pi, n)) ** 2
        k = np.ones(40) / 40; x = np.convolve(x, k, "same"); return .25 * x * env
    def tone(f, d, v=.3):
        tt = np.arange(int(d * sr)) / sr; return v * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5)
    add(0.2, whoosh(.8)); add(1.4, tone(660, .6, .2))
    for off, S in [(INTRO, SW), (INTRO + TW, SF)]:
        add(off, whoosh(.6))
        for st in S[1:]: add(off + st["start"], whoosh())
        for st in S:
            if st.get("tr") and not any(s_.get("tr") for s_ in S[:S.index(st)]): add(off + st["start"] + st["reveal"], tone(1200, .15, .25))
            if st.get("done") and not any(s_.get("done") for s_ in S[:S.index(st)]):
                t0 = off + st["start"] + st["reveal"]
                if st["done"] == "TP": add(t0, tone(880, .5)); add(t0 + .12, tone(1320, .6))
                else: add(t0, tone(110, .6, .5)); add(t0, tone(82, .7, .4))
    add(INTRO + TW + TF, whoosh(.7))
    a = np.clip(a / max(1e-9, np.abs(a).max()) * .8, -1, 1)
    with wave.open(f"{OUT}/sfx.wav", "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32767).astype(np.int16).tobytes())
    open(f"{OUT}/list.txt", "w").write("".join(f"file '{n}.mp4'\n" for n in ["s0_intro", "s1_win", "s2_fail", "s3_outro"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{OUT}/list.txt", "-c", "copy", f"{OUT}/video.tmp.mp4"], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{OUT}/video.tmp.mp4", "-i", f"{OUT}/sfx.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", f"{OUT}/fvg-pas-a-pas.tmp.mp4"], check=True)
    os.replace(f"{OUT}/fvg-pas-a-pas.tmp.mp4", f"{OUT}/fvg-pas-a-pas.mp4")
    print("OK", total)
