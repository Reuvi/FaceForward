"""Sample-time binary traces; accepts a Canvas without importing a GUI toolkit."""

def binary_segments(rows, key, selected, generation, stale_ms):
    """Zero-order hold between adjacent valid captures; never bridge missing data."""
    segments=[]
    previous=None
    for row in rows:
        value=row.get(key) if selected and row.get("subject_id")==selected and row.get("calibration_generation")==generation else None
        current=(row["timestamp_ms"],value) if value in (0,1) else None
        if current and previous and 0 < current[0]-previous[0] <= stale_ms:
            segments.append((previous,(current[0],previous[1]),current))
        previous=current
    return segments


def draw_eye_scope(canvas, state):
    canvas.delete("all")
    w,h=max(320,canvas.winfo_width()),max(180,canvas.winfo_height())
    rows=state["trace"]
    end=rows[-1]["timestamp_ms"] if rows else 0
    start=end-8000
    rows=[row for row in rows if row["timestamp_ms"]>=start]
    frame=state["frame"] or {"faces":[]}
    signals=next((f["signals"] for f in frame["faces"] if f["subject_id"]==state["selected"]),{})
    for i,(side,color) in enumerate((("left","#6ed7fe"),("right","#ffa663"))):
        top=8+i*(h-22)/2
        bottom=top+(h-22)/2-10
        item=signals.get(side+"_eye_open",{})
        value=item.get("value") if item.get("valid") else None
        label=("OPEN · 0" if value==1 else "CLOSED · 1" if value==0 else "UNCERTAIN / UNAVAILABLE")
        canvas.create_text(8,top,text=f"{side.upper()} anatomical eye — {label}",fill=color if value is not None else "#adbbcc",anchor="nw",font=("Arial",11,"bold"))
        for bit,title in ((1,"1 closed"),(0,"0 open")):
            y=bottom-bit*(bottom-top-30)
            canvas.create_text(8,y,text=title,fill="#adbbcc",anchor="w",font=("Arial",9))
            canvas.create_line(65,y,w-10,y,fill="#354555")
        for segment in binary_segments(rows,side+"_closed_bit",state["selected"],state["generation"],state["config"]["stale_ms"]):
            points=[]
            for t,bit in segment:
                points.extend((65+(t-start)/8000*(w-75),bottom-bit*(bottom-top-30)))
            canvas.create_line(*points,fill=color,width=2)
    canvas.create_text(w-8,h-3,text="Last 8 s • sampled steps • gaps = no decision",fill="#adbbcc",anchor="se",font=("Arial",9))
