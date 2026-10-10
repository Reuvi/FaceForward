"""Display-only sampled eye traces, with dark holds for unknown measurements."""

from LabUI.traces import darker, trace_runs


def scope_samples(rows, key, selected, generation):
    for row in rows:
        matching = selected and row.get("subject_id") == selected and row.get("calibration_generation") == generation
        context = (row.get("session_id"), selected, generation) if matching else None
        value = row.get(key)
        if key.endswith("_raw") and row.get(key[:-4]+"_quality", 0) <= 0:
            value = None
        if key+"_valid" in row and not row[key+"_valid"]:
            value = None
        if key.endswith("_closed_bit"):
            valid_key = key[:-11]+"_eye_open_valid"
            if value not in (0, 1) or valid_key in row and not row[valid_key]:
                value = None
        yield row["timestamp_ms"], value, context


def binary_runs(rows, key, selected, generation, stale_ms, start=None):
    return trace_runs(scope_samples(rows, key, selected, generation),
                      step=True, max_gap=stale_ms, start=start)


def draw_feature_scope(canvas, state, mode):
    """Inspect the same captured features that train the per-eye classifier."""
    canvas.delete("all")
    width,height=max(320,canvas.winfo_width()),max(180,canvas.winfo_height())
    rows=state["trace"]
    start=(rows[-1]["timestamp_ms"] if rows else 0)-8000
    if mode=="Eye ratios":
        series=(("left_raw","left","#6ed7fe"),("right_raw","right","#ffa663"))
        title,maximum="Lid gap / eye width · 0–0.5",.5
    else:
        side="left" if mode.startswith("Left") else "right"
        series=tuple((side+"_"+key,key,color) for key,color in (
            ("blink","#6ed7fe"),("squint","#ffa663"),("cheek","#75e3a8"),
            ("brow","#d6a1ff"),("wink_score","#ffffff")))
        title,maximum=side.title()+" appearance · 0–1 (score is not a probability)",1
    canvas.create_text(8,5,text=title,fill="white",anchor="nw",font=("Arial",10))
    for index,(key,label,color) in enumerate(series):
        canvas.create_text(8+index*(width-16)/len(series),25,text=label,fill=color,anchor="nw",font=("Arial",9))
        for unknown,segment in trace_runs(scope_samples(rows,key,state["scope_subject"],state["generation"]),
                                           max_gap=state["config"]["stale_ms"],start=start):
            points=[]
            for timestamp,value in segment:
                points.extend((10+(timestamp-start)/8000*(width-20),height-25-max(0,min(maximum,value))/maximum*(height-75)))
            canvas.create_line(*points,fill=darker(color) if unknown else color,width=2)
    canvas.create_text(width-8,height-3,text="Last 8 s · dark = unknown hold · Export trace CSV for samples",fill="#adbbcc",anchor="se",font=("Arial",9))


def draw_eye_scope(canvas, state, *, intent=False):
    canvas.delete("all")
    w,h=max(320,canvas.winfo_width()),max(180,canvas.winfo_height())
    rows=state["trace"]
    end=rows[-1]["timestamp_ms"] if rows else 0
    start=end-8000
    frame=state["frame"] or {"faces":[]}
    signals=next((f["signals"] for f in frame["faces"] if f["subject_id"]==state["selected"]),{})
    for i,(side,color) in enumerate((("left","#6ed7fe"),("right","#ffa663"))):
        top=8+i*(h-22)/2
        bottom=top+(h-22)/2-10
        item=state.get("wink_readings",{}).get(side,{}) if intent else signals.get(side+"_eye_open",{})
        value=item.get("value") if item.get("known" if intent else "valid") else None
        label=(("WINK · 1" if value==1 else "OPEN / BLINK · 0" if value==0 else "UNKNOWN · held trace") if intent else
               "OPEN · 0" if value==1 else "CLOSED · 1" if value==0 else "UNKNOWN · held trace")
        name="wink output" if intent else "anatomical eye"
        canvas.create_text(8,top,text=f"{side.upper()} {name} — {label}",fill=color if value is not None else "#adbbcc",anchor="nw",font=("Arial",11,"bold"))
        for bit,title in ((1,"1 wink" if intent else "1 closed"),(0,"0 off" if intent else "0 open")):
            y=bottom-bit*(bottom-top-30)
            canvas.create_text(8,y,text=title,fill="#adbbcc",anchor="w",font=("Arial",9))
            canvas.create_line(65,y,w-10,y,fill="#354555")
        for unknown, segment in binary_runs(rows,side+("_wink_bit" if intent else "_closed_bit"),state.get("scope_subject",state["selected"]),state["generation"],state["config"]["stale_ms"],start):
            points=[]
            for t,bit in segment:
                points.extend((65+(t-start)/8000*(w-75),bottom-bit*(bottom-top-30)))
            canvas.create_line(*points,fill=darker(color) if unknown else color,width=2)
    canvas.create_text(w-8,h-3,text="Last 8 s • dark = unknown, last value held for display only",fill="#adbbcc",anchor="se",font=("Arial",9))
