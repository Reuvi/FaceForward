"""Coupled 2D 1€ filter (Casiez, Roussel & Vogel, CHI 2012).

Original implementation of the published equations; no prediction or dependency.
Cutoff rises with a low-pass estimate of speed to reduce deliberate-motion lag.
"""

import math


class OneEuro:
    def __init__(self, dimensions, min_cutoff, beta=4.0, derivative_cutoff=1.0):
        self.dimensions = dimensions
        self.min_cutoff, self.beta = min_cutoff, beta
        self.derivative_cutoff = derivative_cutoff
        self.reset()

    def reset(self, value=None):
        self.previous = self.value = value
        self.derivative = (0.0,) * self.dimensions

    @staticmethod
    def alpha(cutoff, dt):
        ratio = 2 * math.pi * cutoff * dt
        return ratio / (1 + ratio)

    def step(self, value, dt):
        value = tuple(value)
        if self.previous is None:
            self.reset(value)
            return value
        if dt <= 0:
            return self.value
        raw_speed = tuple((v-p)/dt for v, p in zip(value, self.previous))
        alpha = self.alpha(self.derivative_cutoff, dt)
        self.derivative = tuple(d+alpha*(s-d) for d, s in zip(self.derivative, raw_speed))
        speed = math.sqrt(sum(d*d for d in self.derivative))
        alpha = self.alpha(self.min_cutoff+self.beta*speed, dt)
        self.value = tuple(p+alpha*(v-p) for p, v in zip(self.value, value))
        self.previous = value
        return self.value
