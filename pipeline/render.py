"""Cut flat views out of each 360 frame: L (left kerb), R (right kerb), F (ahead), B (behind).

The mount turned during the ride (GSAB2131 #100 sits ~40 degrees off), so all four
quarters are cut and the names are nominal, measured at the start.

The Max 2 rode on the front of the bike facing the rider, so 'ahead' sits at a fixed
yaw in the equirect (FWD_YAW, measured on GSAA1911 #120). Thailand drives on the left:
L is the near kerb, R looks across the road.
"""
import subprocess, sys, os, concurrent.futures as cf
FWD_YAW = -80
VIEWS = {"L": FWD_YAW - 90, "R": FWD_YAW + 90, "F": FWD_YAW}
def wrap(y): return (y + 180) % 360 - 180

def render(src, out_dir, views="LRFB", w=1600, h=1100, hfov=100, vfov=75, yaw0=FWD_YAW):
    outs = []
    for v in views:
        yaw = wrap(yaw0 + {"L": -90, "R": 90, "F": 0, "B": 180}[v])
        out = os.path.join(out_dir, os.path.basename(src).rsplit(".", 1)[0] + f"_{v}.jpg")
        if not os.path.exists(out):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-frames:v", "1", "-vf",
                            f"v360=input=e:output=flat:yaw={yaw}:h_fov={hfov}:v_fov={vfov}:w={w}:h={h}",
                            "-q:v", "3", out], check=True)
        outs.append(out)
    return outs

if __name__ == "__main__":
    out_dir = sys.argv[1]; srcs = sys.argv[2:]
    os.makedirs(out_dir, exist_ok=True)
    with cf.ThreadPoolExecutor(6) as ex:
        for i, _ in enumerate(ex.map(lambda s: render(s, out_dir), srcs), 1):
            if i % 50 == 0: print(i, flush=True)
