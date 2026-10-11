import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from mapmatching.src.registration import register


class RegistrationScaleTests(unittest.TestCase):
    def inputs(self,hypotheses):
        game=SimpleNamespace(image_factor=.25)
        ref=SimpleNamespace(map_id='known',difficulty='hard',mode=None,
                            evidence=SimpleNamespace(image_factor=.5),regions=[],exclusions=[])
        return game,SimpleNamespace(reference=ref,score=8,hypotheses=np.array(hypotheses,float))

    def test_tiny_hypotheses_rejected_before_verification(self):
        game,retrieved=self.inputs([[.15,0,0],[.3,1,1]])
        with patch('mapmatching.src.registration.observed_points',return_value=np.ones((25,2))), \
             patch('mapmatching.src.registration.verify') as verify:
            result=register(game,retrieved)
        self.assertIsNone(result.pose);verify.assert_not_called()

    def test_prior_filters_hypotheses_and_bounds_refinement(self):
        game,retrieved=self.inputs([[.5,0,0],[1.,0,0],[2.,0,0]])
        with patch('mapmatching.src.registration.observed_points',return_value=np.ones((25,2))), \
             patch('mapmatching.src.registration.verify',return_value=(.8,.1)) as verify, \
             patch('mapmatching.src.registration.residuals',return_value=np.zeros(25)), \
             patch('mapmatching.src.registration.minimize',return_value=SimpleNamespace(x=np.array([1.,0,0]))) as fit:
            result=register(game,retrieved,scale_bounds=(1.9,2.1))
        self.assertEqual(result.pose.scale,2.)
        self.assertTrue(all(call.args[0][0]==1. for call in verify.call_args_list))
        self.assertEqual(fit.call_args.kwargs['bounds'][0],(.95,1.05))
