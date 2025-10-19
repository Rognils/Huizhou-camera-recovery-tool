#!/usr/bin/env python3
import os, sys, glob, mmap, argparse, bisect, subprocess, io
from datetime import datetime, timezone
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cv2
import numpy as np

SOI = b"\xff\xd8"; EOI = b"\xff\xd9"

def find_pairs(input_dir: str):
    pairs=[]
    for idx in glob.glob(os.path.join(input_dir, "*.txt")):
        base=os.path.basename(idx)[:-4]; data=os.path.join(input_dir, base)
        if os.path.exists(data) and os.path.getsize(data)>0: pairs.append((data,idx))
    pairs.sort(key=lambda x:x[0]); return pairs

def read_index(idx_path):
    rows=[]
    with open(idx_path) as f:
        for line in f:
            p=line.split()
            if len(p)==3:
                ts,off,ln=map(int,p); rows.append((ts,off,ln))
    rows.sort(key=lambda x:x[1]); return rows

def all_sois(mm):
    res=[]; i=0; N=mm.size()
    while True:
        j=mm.find(SOI,i)
        if j==-1: break
        res.append(j); i=j+2
        if i>=N: break
    return res

def load_font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,size=size)
    return ImageFont.load_default()

def text_size(draw, text, font):
    try:
        x0,y0,x1,y1 = draw.textbbox((0,0), text, font=font); return x1-x0, y1-y0
    except Exception:
        return draw.textsize(text, font=font)

def enhance_cv(img_bgr, denoise=True, sharpen=True, clahe=True, up=1, crop=None):
    # optional crop: (x,y,w,h)
    if crop:
        x,y,w,h = crop
        img_bgr = img_bgr[y:y+h, x:x+w].copy()
    # scale up
    if up>1:
        img_bgr = cv2.resize(img_bgr, None, fx=up, fy=up, interpolation=cv2.INTER_LANCZOS4)
    # mild denoise
    if denoise:
        img_bgr = cv2.fastNlMeansDenoisingColored(img_bgr, None, 3, 3, 7, 21)
    # contrast/brightness via CLAHE
    if clahe:
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l,a,b = cv2.split(lab)
        cl  = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(l)
        lab = cv2.merge((cl,a,b))
        img_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    # unsharp mask
    if sharpen:
        g = cv2.GaussianBlur(img_bgr, (0,0), 1.0)
        img_bgr = cv2.addWeighted(img_bgr, 1.5, g, -0.5, 0)
    return img_bgr

def build_mp4(folder, fps, out_path):
    pattern = os.path.join(folder, "*.jpg")
    cmd = ["ffmpeg","-y","-r",str(fps),"-pattern_type","glob","-i",pattern,
           "-c:v","libx264","-pix_fmt","yuv420p",out_path]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode==0 and os.path.exists(out_path) and os.path.getsize(out_path)>0

def process_event(data_path, idx_path, out_root, fps, stamp, use_utc, denoise, sharpen, clahe, up, crop):
    base=os.path.basename(data_path)
    evt_dir=os.path.join(out_root, base); os.makedirs(evt_dir, exist_ok=True)
    raw_dir=os.path.join(evt_dir,"frames_by_soi"); os.makedirs(raw_dir, exist_ok=True)
    stamp_dir=os.path.join(evt_dir,"frames_stamped"); 
    if stamp: os.makedirs(stamp_dir, exist_ok=True)

    rows=read_index(idx_path); offsets=[off for (_,off,_) in rows]
    with open(data_path,"rb") as f:
        mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
        N=mm.size(); sois=all_sois(mm)
        if not sois: print(f"[{base}] Inga SOI."); mm.close(); return
        saved=0
        for k,start in enumerate(sois):
            end = sois[k+1] if k+1<len(sois) else N
            chunk = mm[start:end]
            pos_eoi = chunk.rfind(EOI)
            data = chunk[:pos_eoi+2] if pos_eoi!=-1 else chunk
            # öppna via OpenCV direkt för bättre tolerans
            arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                if pos_eoi==-1:
                    arr = np.frombuffer(data+EOI, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None: 
                continue
            # improve/crop/scale
            img = enhance_cv(img, denoise=denoise, sharpen=sharpen, clahe=clahe, up=up, crop=crop)
            out_raw = os.path.join(raw_dir, f"frame_{k:05d}.jpg")
            cv2.imwrite(out_raw, img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            saved += 1
        mm.close()
    print(f"[{base}] Extracted {saved} enhanced pictures → {raw_dir}")
    if saved==0: return

    # timestamp
    src_dir=raw_dir
    if stamp:
        imgs=sorted(glob.glob(os.path.join(raw_dir,"*.jpg")))
        with open(data_path,"rb") as f:
            mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
            sois=all_sois(mm); mm.close()
        for k,ip in enumerate(imgs):
            soi_pos = sois[k] if k<len(sois) else sois[-1]
            j = bisect.bisect_right(offsets, soi_pos)-1
            if j<0: j=0
            ts_ms = rows[j][0]
            dt = datetime.fromtimestamp(ts_ms/1000.0, tz=timezone.utc if use_utc else None)
            ts = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + ("Z" if use_utc else "")
            im = Image.open(ip).convert("RGB")
            W,H=im.size; pad=int(max(W,H)*0.015); fs=int(max(W,H)*0.05)
            font=load_font(fs); draw=ImageDraw.Draw(im)
            tw,th = text_size(draw, ts, font)
            x0,y0=pad, H-th-2*pad; x1,y1=x0+tw+2*pad, H-pad
            overlay=Image.new("RGBA",(W,H),(0,0,0,0))
            od=ImageDraw.Draw(overlay); od.rectangle([x0,y0,x1,y1], fill=(0,0,0,160))
            im=Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            draw=ImageDraw.Draw(im)
            draw.text((x0+1,y0+1), ts, font=font, fill=(0,0,0))
            draw.text((x0,  y0),   ts, font=font, fill=(255,255,255))
            outp=os.path.join(stamp_dir, f"frame_{k:05d}_{ts_ms}.jpg")
            im.save(outp, "JPEG", quality=95)
        print(f"[{base}] Timestamped {len(imgs)} pictures → {stamp_dir}")
        src_dir=stamp_dir

    mp4=os.path.join(evt_dir, f"out_stamped_{fps}fps.mp4" if stamp else f"out_{fps}fps.mp4")
    ok=build_mp4(src_dir, fps, mp4)
    print(f"[{base}] Video: {mp4}" if ok else f"[{base}] Could not create video.")

def main():
    ap = argparse.ArgumentParser(description="Extract multiple still frames with enhancement from a camera data file.")
    ap.add_argument("--input", default=".", help="Folder containing data file + .txt (default: .)")
    ap.add_argument("--fps", type=int, default=25, help="FPS for output video")
    ap.add_argument("--no-stamp", action="store_true", help="Skip timestamp overlay on images")
    ap.add_argument("--utc", action="store_true", help="Use UTC time for timestamps")
    ap.add_argument("--up", type=int, default=1, help="Upscale factor (1=none, 2=2x, 3=3x)")
    ap.add_argument("--crop", type=str, help="Crop area: x,y,w,h (e.g. 200,120,500,400)")
    ap.add_argument("--no-denoise", action="store_true", help="Disable noise reduction")
    ap.add_argument("--no-sharpen", action="store_true", help="Disable sharpening")
    ap.add_argument("--no-clahe", action="store_true", help="Disable CLAHE (local contrast enhancement)")
    args=ap.parse_args()

    input_dir=os.path.abspath(args.input)
    pairs=find_pairs(input_dir)
    if not pairs:
        print("[!] Did not find any (data, .txt)-par."); sys.exit(1)

    crop=None
    if args.crop:
        x,y,w,h = map(int, args.crop.split(","))
        crop=(x,y,w,h)

    out_root=os.path.join(input_dir,"output"); os.makedirs(out_root, exist_ok=True)
    print(f"[*] Found {len(pairs)} data. Working...")

    for data_path, idx_path in pairs:
        process_event(
            data_path, idx_path, out_root, args.fps,
            stamp=(not args.no_stamp), use_utc=args.utc,
            denoise=(not args.no_denoise), sharpen=(not args.no_sharpen),
            clahe=(not args.no_clahe), up=max(1,args.up), crop=crop
        )
    print("[✓] Done.")

if __name__=="__main__":
    main()
