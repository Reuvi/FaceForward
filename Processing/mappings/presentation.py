"""Presentation-only eye arbitration and continuous mouth braking."""
from dataclasses import replace

from Processing.mouse.engine import AxisFilter
from Processing.mouse.signals import decode
from .engine import HeadMouseProcessor
from .head_pointer import HeadPointerFilter
from .config import presentation_mapping


class EyeGestures:
    """Capture-time gestures; unknown cancels, reopen re-arms, ticks never qualify."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.ready = False
        self.side = None
        self.since = self.both_since = None
        self.blocked = False
        self.drag = self.click = self.enter = self.toggle = False
        self.reason = 'Open both eyes to prepare gestures'

    def sample(self, left, right, timestamp, settings, eligible=(True, True), *, require_wink=False):
        self.click = self.enter = self.toggle = False
        if left is None or right is None:
            self.reset()
            self.reason = 'Eye open/closed unknown — reopen both eyes'
            return
        if not left and not right:
            if self.ready and not self.blocked and self.side and self.since is not None:
                duration = timestamp-self.since
                if (require_wink or duration >= settings.solo_ms) and not self.drag:
                    self.click = self.side == 'left'
                    self.enter = self.side == 'right'
            self.reason = ('Left click requested' if self.click else 'Enter requested' if self.enter else
                           'Eyes open — ready')
            self.ready = True
            self.side = self.since = self.both_since = None
            self.blocked = self.drag = False
            return
        if not self.ready:
            return
        if left and right:
            self.drag = False
            self.side = self.since = None
            if self.blocked:
                return
            if self.both_since is None:
                self.both_since = timestamp
            if timestamp-self.both_since >= settings.chord_ms:
                self.toggle = True
                self.blocked = True
                self.reason = 'Dictation toggled — reopen both eyes'
            else:
                self.reason = 'Both eyes closed — holding for dictation'
            return
        # An incomplete chord must never become a solo action while reopening.
        if self.both_since is not None or self.blocked:
            self.blocked = True
            self.drag = False
            return
        side = 'left' if left else 'right'
        if self.side is not None and self.side != side:
            self.blocked = True
            self.drag = False
            self.reason = 'Eye changed before reopening — reopen both eyes'
            return
        self.side = side
        match = eligible[0 if left else 1]
        if match is None:
            self.blocked = True
            self.drag = False
            self.reason = f'{side.title()} wink unknown — reopen both eyes; check Wink action calibration'
            return
        if not match:
            # Geometry can report closed before the trained appearance matches.
            # Wait for that match; do not veto every later frame in the closure.
            if self.drag:
                self.blocked = True
                self.reason = 'Wink released during drag — reopen both eyes'
            else:
                self.reason = f'{side.title()} eye closed — waiting for calibrated wink'
            self.since = None
            self.drag = False
            return
        if self.since is None:
            self.since = timestamp
        if side == 'left' and timestamp-self.since >= settings.drag_ms:
            self.drag = True
        action = 'click' if left else 'Enter'
        evidence = 'wink recognized' if require_wink else 'eye closed'
        self.reason = ('Dragging — reopen to release' if self.drag else
                       f'{side.title()} {evidence} — reopen for {action}')


class BrakedHeadFilter(HeadPointerFilter):
    def __init__(self, *args, **kwargs):
        self.brake = 0.0
        self.previous_scale = 1.0
        super().__init__(*args, **kwargs)

    def motion_response(self, target, now):
        if self.motion.enabled:
            target, acceleration, deceleration = super().motion_response(target, now)
        else:
            target, acceleration, deceleration = AxisFilter.motion_response(self, target, now)
        scale = 1-self.brake
        # Immediate resistance removes existing momentum as opening increases.
        # Apply only the ratio of changes, never the same damping every tick.
        if scale < self.previous_scale:
            ratio = scale/self.previous_scale if self.previous_scale else 0
            self.velocity = tuple(v*ratio for v in self.velocity)
            if self.adaptive:
                self.adaptive.reset(self.velocity)
        self.previous_scale = scale
        if not scale:
            self.velocity = (0.0, 0.0)
            if self.adaptive:
                self.adaptive.reset(self.velocity)
        return tuple(t*scale for t in target), acceleration, deceleration*(1+3*self.brake)


class PresentationProcessor(HeadMouseProcessor):
    def __init__(self, mapping=None, subject_id='mock-person'):
        self.gestures = EyeGestures()
        self.gesture_counts = dict.fromkeys(('captures', 'left_action_frames', 'right_action_frames',
                                             'left_unknown_frames', 'right_unknown_frames',
                                             'clicks', 'enters', 'drags', 'dictation_toggles'), 0)
        self.dictating = False
        self.dictation_toggle = 0
        self.resume_neutral = False
        super().__init__(mapping or presentation_mapping(), subject_id)
        self.pointer = BrakedHeadFilter(self.config.pointer, self.mapping.head_motion,
                                       gain=self.mapping.pointer_gain, down_gain=self.mapping.pointer_down_gain,
                                       adaptive=self.mapping.adaptive_pointer)

    def arm(self, *, center=False):
        super().arm(center=center)
        self.gestures.reset()
        self.dictating = self.resume_neutral = False

    def disarm(self, reason='Preview stopped'):
        super().disarm(reason)
        self.gestures.reset()
        self.dictating = self.resume_neutral = False

    def decode_sample(self, frame):
        raw = decode(frame, self.config, self.subject_id, raw_eyes=True)
        return replace(super().decode_sample(frame),
                       anatomical_left=raw.left_closed if raw.left_known else None,
                       anatomical_right=raw.right_closed if raw.right_known else None)

    def buttons_released(self):
        sample = self.sample
        return bool(sample and sample.anatomical_left is False and sample.anatomical_right is False)

    def accept(self, frame, received_ms):
        result = super().accept(frame, received_ms)
        if result['accepted'] and self.armed:
            sample = self.sample
            self.gesture_counts['captures'] += 1
            for side in ('left', 'right'):
                self.gesture_counts[side+'_action_frames'] += int(
                    getattr(sample, side+'_known') and getattr(sample, side+'_closed'))
                self.gesture_counts[side+'_unknown_frames'] += int(
                    not getattr(sample, side+'_known') or getattr(sample, 'anatomical_'+side) is None)
            was_dragging = self.gestures.drag
            self.gestures.sample(sample.anatomical_left, sample.anatomical_right,
                                 sample.timestamp_ms, self.mapping.presentation,
                                 (sample.left_closed if sample.left_known else None,
                                  sample.right_closed if sample.right_known else None),
                                 require_wink=self.mapping.require_wink)
            if self.enabled and not self.dictating:
                self.gesture_counts['clicks'] += int(self.gestures.click)
                self.gesture_counts['enters'] += int(self.gestures.enter)
                self.gesture_counts['drags'] += int(self.gestures.drag and not was_dragging)
            if self.enabled and self.gestures.toggle:
                self.gesture_counts['dictation_toggles'] += 1
                self.dictating = not self.dictating
                self.dictation_toggle += 1
                self.resume_neutral = not self.dictating
                self.pointer.reset_motion()
        return result

    def cancel_dictation(self):
        self.dictating = False
        self.gestures.reset()
        self.resume_neutral = True
        self.pointer.reset_motion()

    def tick(self, now_ms):
        sample = self.sample
        fresh = (sample is not None and self.received_ms is not None and
                 0 <= now_ms-sample.timestamp_ms <= self.config.stale_ms and
                 0 <= now_ms-self.received_ms <= self.config.stale_ms)
        openness = sample.mouth_openness if fresh else None
        self.pointer.brake = self.mapping.presentation.brake(openness)
        snap = super().tick(now_ms)
        known = bool(fresh and sample.anatomical_left is not None and sample.anatomical_right is not None)
        active = snap['enabled'] and known and not self.dictating
        snap['left_click'] = int(active and self.gestures.click)
        snap['right_click'] = 0
        snap['keys'] = dict.fromkeys(snap['keys'], 0)
        snap['known']['left_click'] = known
        snap['known']['right_click'] = False
        snap['known']['keys'] = dict.fromkeys(snap['keys'], False)
        snap['presentation'] = dict(enter=bool(active and self.gestures.enter),
                                    drag_left=bool(active and self.gestures.drag), eyes_known=known)
        snap['dictation_request'] = dict(active=bool(snap['enabled'] and self.dictating),
                                        toggle=self.dictation_toggle)
        if self.resume_neutral and self.pointer.valid and self.pointer.neutral():
            self.resume_neutral = False
        if self.dictating or self.resume_neutral or openness is None:
            snap['pointer_x'] = snap['pointer_y'] = .5
            self.pointer.reset_motion()
        snap['diagnostics']['resume_head_neutral'] = self.resume_neutral
        snap['diagnostics']['mouth_brake'] = dict(openness=openness, resistance=self.pointer.brake,
                                                  known=openness is not None)
        snap['diagnostics']['button_actions']['left_eye'].update(down=snap['left_click'])
        snap['diagnostics']['button_actions']['right_eye'].update(down=int(snap['presentation']['enter']), output='enter')
        gesture_status = (snap['status'] if not snap['enabled'] else
                          'Dictation active — solo eye actions paused' if self.dictating else self.gestures.reason)
        snap['diagnostics']['eye_gesture'] = dict(
            status=gesture_status, ready=self.gestures.ready, blocked=self.gestures.blocked,
            side=self.gestures.side, counts=dict(self.gesture_counts),
            anatomical_left=sample.anatomical_left if fresh else None,
            anatomical_right=sample.anatomical_right if fresh else None)
        snap['instructions'] = self.instructions(snap)
        return snap

    def instructions(self, snap):
        # super().tick dispatches here before the presentation fields are added.
        if 'presentation' not in snap:
            return super().instructions(snap)
        brake = snap['diagnostics']['mouth_brake']
        eye_mode = 'Calibrated wink' if self.mapping.require_wink else 'Open / closed'
        status = snap['diagnostics']['eye_gesture']['status']
        rows = [dict(id='eye_left', input='Left eye', raw=snap['diagnostics']['left_closed'],
                     filtered=int(snap['left_click'] or snap['presentation']['drag_left']), threshold=eye_mode,
                     instruction=status+' · left click / hold to drag'),
                dict(id='eye_right', input='Right eye', raw=snap['diagnostics']['right_closed'],
                     filtered=int(snap['presentation']['enter']), threshold=eye_mode, instruction=status+' · right eye: Enter'),
                dict(id='mouth_brake', input='Mouth opening', raw=brake['openness'], filtered=brake['resistance'],
                     threshold='Wider = slower', instruction='Pointer paused: unknown mouth' if not brake['known'] else f"Resistance {brake['resistance']:.0%}"),
                dict(id='both_eyes', input='Both eyes', raw=None, filtered=None,
                     threshold=f"Hold {self.mapping.presentation.chord_ms:.0f} ms",
                     instruction='Dictating — close both to send' if self.dictating else 'Close both to start dictation')]
        return rows + [r for r in super().instructions(snap) if r['id'].startswith('head_pointer_')]
