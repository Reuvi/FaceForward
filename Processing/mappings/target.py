"""Destination filtering; a fixed observation never becomes ongoing velocity."""

import math

from Processing.mouse.engine import AxisFilter, length


class TargetFilter(AxisFilter):
    """Reuse capture buffering/freshness, then smooth position and hold fixations.

    The engine's signed output slots carry a bounded position here. The explicit
    target mode on every serialized command determines their meaning downstream.
    """

    def __init__(self, config, *, gain=1, adaptive=True, jitter=.01, down_gain=1, delay_ms=None):
        self.jitter = jitter
        self.delay_ms = delay_ms
        super().__init__(config, 2, gain=gain, adaptive=adaptive, down_gain=down_gain)

    def reset_motion(self):
        super().reset_motion()
        self.filtered = self.anchor = None
        if self.adaptive:
            self.adaptive.reset()

    def neutral(self):
        # Any fresh destination is allowed after explicit Start. Buttons/head
        # must still pass the owning processor's independent release gates.
        return True

    def push(self, value, timestamp):
        if value is None:
            self.clear()
            return
        point = tuple(value)
        if self.history and timestamp == self.history[-1][0]:
            self.history[-1] = (timestamp, point)
        else:
            self.history.append((timestamp, point))
        self.valid = True

    def step(self, now, delay_ms, dt):
        self.position = self.interpolate(now - (delay_ms if self.delay_ms is None else self.delay_ms))
        if self.position is None:
            self.reset_motion()
            return self.velocity
        self.target = tuple(max(-1, min(1, v*self.gain)) for v in self.normalize(self.position))
        if self.filtered is None:
            self.filtered = self.target
            if self.adaptive:
                self.adaptive.reset(self.target)
        elif self.adaptive and self.config.smoothing_ms:
            self.filtered = self.adaptive.step(self.target, dt)
        else:
            alpha = 1 if not self.config.smoothing_ms else -math.expm1(-dt*1000/self.config.smoothing_ms)
            self.filtered = tuple(p+alpha*(v-p) for p,v in zip(self.filtered,self.target))
        # Smoothing approaches endpoints asymptotically; the fixation hold must
        # not strand a saturated destination a few pixels short of the border.
        edges = tuple(abs(t) == 1 and abs(t-v) <= .004 for t,v in zip(self.target,self.filtered))
        self.filtered = tuple(t if edge else v for t,v,edge in zip(self.target,self.filtered,edges))
        self.active = (self.anchor is None or
                       length(tuple(v-p for v,p in zip(self.filtered,self.anchor))) > 2*self.jitter)
        if self.active:
            self.anchor = self.filtered
        else:
            self.anchor = tuple(v if edge else p for v,p,edge in zip(self.filtered,self.anchor,edges))
        self.velocity = self.anchor
        return self.velocity
