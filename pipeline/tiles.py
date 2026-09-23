"""OCR tiles: 8 yaws x 2 pitches, 50x30 degrees at the source's native scale (~21 px/degree)."""
import subprocess, sys, os, concurrent.futures as cf
YAWS = range(-180, 180, 45)
PITCHES = (3, 22)
def tiles(src, out_dir):
    base = os.path.basename(src).rsplit(".", 1)[0]
    outs = [(y, p, os.path.join(out_dir, f"{base}_y{y}_p{p}.jpg")) for y in YAWS for p in PITCHES]
    todo = [o for o in outs if not os.path.exists(o[2])]
    if todo:
        # one decode, many outputs
        chains, maps = [], []
        n = len(todo)
        fc = f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n)) + ";" + ";".join(
            f"[s{i}]v360=input=e:output=flat:yaw={y}:pitch={p}:h_fov=50:v_fov=30:w=1066:h=640[o{i}]"
            for i, (y, p, _) in enumerate(todo))
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-filter_complex", fc]
        for i, (_, _, o) in enumerate(todo):
            cmd += ["-map", f"[o{i}]", "-frames:v", "1", "-q:v", "3", o]
        subprocess.run(cmd, check=True)
if __name__ == "__main__":
    out_dir = sys.argv[1]; os.makedirs(out_dir, exist_ok=True)
    srcs = [l.strip() for l in open(sys.argv[2])]
    with cf.ThreadPoolExecutor(4) as ex:
        for i, _ in enumerate(ex.map(lambda s: tiles(s, out_dir), srcs), 1):
            if i % 50 == 0: print(i, flush=True)
