from dataclasses import replace
import random
import statistics
import unittest

from Processing.mouse.config import AxisConfig
from Processing.mouse.engine import AxisFilter
from Processing.mouse.adaptive import OneEuro


def metrics(adaptive):
    config=AxisConfig(boost_gain=0)
    filt=AxisFilter(config,2,adaptive=adaptive)
    rng=random.Random(27);speeds=[]
    for i in range(600):
        filt.push((.75+rng.uniform(-.008,.008),.5),i*1000/30)
        for j in range(3):
            value=filt.step(i*1000/30+j*1000/90,0,1/90)[0]
            if i>100:speeds.append(value)
    filt=AxisFilter(config,2,adaptive=adaptive)
    filt.push((.5,.5),0);filt.step(0,0,.01)
    for i in range(1,101):
        filt.push((.85,.5),i*10)
        if filt.step(i*10,0,.01)[0]>=filt.target[0]*.9:
            return statistics.pstdev(speeds),i*10
    raise AssertionError('step did not settle')


class AdaptivePointerTests(unittest.TestCase):
    def test_reduces_seeded_stationary_noise_and_step_latency(self):
        fixed=metrics(False);adaptive=metrics(True)
        self.assertLess(adaptive[0],fixed[0]*.85)
        self.assertLess(adaptive[1],fixed[1]*.6)

    def test_axis_symmetry_finite_bounds_and_variable_rates(self):
        for hz in (10,30,60,100):
            filt=AxisFilter(AxisConfig(boost_gain=0),2,adaptive=True)
            for i in range(200):
                x=1 if i<100 else 0
                filt.push((x,x),i*1000/hz)
                value=filt.step(i*1000/hz,0,1/hz)
                self.assertAlmostEqual(value[0],value[1])
                self.assertTrue(all(-1<=v<=1 for v in value))
            self.assertLess(value[0],0)

    def test_invalid_resets_history_and_first_enabled_neutral_is_real(self):
        filt=AxisFilter(AxisConfig(boost_gain=0),2,adaptive=True)
        for i in range(30):
            filt.push((1,0),i*20);filt.step(i*20,0,.02)
        filt.push(None,600)
        self.assertEqual(filt.step(600,0,.02),(0,0))
        self.assertIsNone(filt.position)
        filt.push((1,0),620);self.assertFalse(filt.neutral())
        filt.push((.5,.5),640);self.assertTrue(filt.neutral())
        filt.start_from_latest()
        self.assertEqual(filt.step(640,50,.02),(0,0))

    def test_zero_smoothing_bypasses_and_zero_dt_never_divides(self):
        filt=AxisFilter(replace(AxisConfig(),smoothing_ms=0),2,adaptive=True)
        self.assertIsNone(filt.adaptive)
        euro=OneEuro(2,1)
        self.assertEqual(euro.step((0,0),0),(0,0))
        self.assertEqual(euro.step((1,1),0),(0,0))


if __name__=='__main__':
    print('Synthetic fixed/adaptive (velocity std, 90% step ms):',metrics(False),metrics(True))
    unittest.main()
