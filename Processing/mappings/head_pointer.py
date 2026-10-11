"""Capture-timed head speed response on the existing position-driven pointer."""

from Processing.mouse.engine import AxisFilter, centered, length


class HeadPointerFilter(AxisFilter):
    WINDOW_MS = 80
    EXPIRE_MS = 150
    SPEED_FLOOR = .35
    FULL_SPEED = 2.0

    def __init__(self, config, motion, *, gain=1, down_gain=1, adaptive=True):
        self.motion = motion
        super().__init__(config, 2, gain=gain, down_gain=down_gain, adaptive=adaptive)

    def reset_motion(self):
        super().reset_motion()
        self.motion_state = dict(phase="resting", radial_speed=0.0, multiplier=1.0,
                                 braking=0.0, acceleration=self.config.acceleration,
                                 deceleration=self.config.deceleration)

    def push(self, value, timestamp):
        super().push(value, timestamp)
        # This replaces generic jump boost, which cannot distinguish a return
        # toward neutral from an intentional outward movement.
        self.boost = 0.0

    def head_coordinates(self, point):
        # Measure personal half-ranges/s, before downward gain and inversion.
        return (centered(point[0], self.config.center_x),
                centered(point[1], self.config.center_y))

    def motion_response(self, target, now):
        outward = returning = speed = 0.0
        if len(self.history) >= 2:
            last_time, last = self.history[-1]
            previous_time, previous = self.history[-2]
            age = now-last_time
            if last_time-previous_time >= 8 and 0 <= age < self.EXPIRE_MS:
                begin = max(self.history[0][0], last_time-self.WINDOW_MS)
                elapsed = (last_time-begin)/1000
                current = self.head_coordinates(last)
                prior = self.head_coordinates(previous)
                baseline = self.head_coordinates(self.interpolate(begin))
                speed = max(-8, min(8, (length(current)-length(baseline))/elapsed))
                change = length(current)-length(prior)
                instant_speed = change/((last_time-previous_time)/1000)
                reversal = sum(a*b for a,b in zip(current,prior)) < 0
                # Latest evidence suppresses lingering boost as soon as the
                # head holds, returns or crosses neutral. The window rejects
                # small oscillations; output ticks never add derivative samples.
                strength = max(0, min(1, (min(abs(speed),abs(instant_speed))-self.SPEED_FLOOR) /
                                        (self.FULL_SPEED-self.SPEED_FLOOR)))
                # Hold between normal camera captures, then fade on a stalled
                # stream. A per-tick decay from age zero would add speed ripple.
                strength *= min(1, (self.EXPIRE_MS-age)/(self.EXPIRE_MS-self.WINDOW_MS))
                if change > .001 and speed > 0 and not reversal and self.active:
                    outward = strength
                elif (change < -.001 and speed < 0) or reversal:
                    returning = strength
        multiplier = 1+self.motion.speed_gain*outward
        braking = self.motion.return_brake*returning
        magnitude = length(target)
        scale = min(multiplier, 1/magnitude) if magnitude else 1
        target = tuple(v*scale*(1-braking) for v in target)
        acceleration = self.config.acceleration*(1+self.motion.speed_gain*outward)
        deceleration = self.config.deceleration*(1+2*braking)
        if returning and sum(v*t for v,t in zip(self.velocity,target)) < 0:
            acceleration = deceleration
        phase = ("accelerating" if outward and self.motion.speed_gain else
                 "return braking" if braking else "steady" if self.active else "resting")
        self.motion_state = dict(phase=phase, radial_speed=speed, multiplier=multiplier,
                                 braking=braking, acceleration=acceleration, deceleration=deceleration)
        return target, acceleration, deceleration
