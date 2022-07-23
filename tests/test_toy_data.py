from dnmfx.utils import sigmoid
from dnmfx.optimize import dnmf
from dnmfx.component_description import create_component_description
from dnmfx.parameters import Parameters as DNMFXParameters
import jax.numpy as jnp
import math
import unittest
from .toy_dataset import create_synthetic_dataset
from .toy_dataset import Parameters as DatasetParameters


class TestCaseA(unittest.TestCase):

    def test_case_A(self):

        toy_data = self._generate_caseA_data()
        component_descriptions = \
                        create_component_description(toy_data.bounding_boxes)
        dnmfx_parameters = DNMFXParameters(max_iteration=1, batch_size=1)
        H, W, B, log = dnmf(toy_data.sequence,
                            component_descriptions,
                            dnmfx_parameters,
                            log_every=1)

        iter_log = log.iteration_logs[0]
        x_hat_logits = -iter_log.x_hat_logits.reshape(-1,)
        W_logits = iter_log.W_logits
        H_logits = iter_log.H_logits
        B_logits = iter_log.B_logits

        expected_grad_B_logits = \
                math.e**(-x_hat_logits)/(1 + math.e**(-x_hat_logits))**2
        expected_grad_H_logits = expected_grad_B_logits * W_logits
        expected_grad_W_logits = expected_grad_B_logits * H_logits

        assert abs(iter_log.grad_H_logits) - abs(expected_grad_H_logits) < 1e-8, \
                "Partial gradient H wrt. loss matches expectation"
        assert abs(iter_log.grad_W_logits) - abs(expected_grad_W_logits) < 1e-8, \
                "Partial gradient W wrt. loss matches expectation"
        assert abs(iter_log.grad_B_logits) - abs(expected_grad_B_logits) < 1e-8, \
                "Partial gradient B wrt. loss matches expectation"

    def _generate_caseA_data(self):

        cell_centers = [(0.5, 0.5)]
        image_size = 1
        cell_size = 1
        num_frames = 1
        trace_parameters = {
                            "possion_lam": 2,
                            "gauss_mu": 0,
                            "gauss_sigma": 0.1
                            }
        noise_magnitudes = {"background": 0.1, "extra": 0.1}
        dataset_parameters = DatasetParameters(image_size,
                                cell_size,
                                num_frames,
                                cell_centers,
                                trace_parameters,
                                noise_magnitudes)
        toy_data = create_synthetic_dataset(dataset_parameters)
        toy_data.sequence = toy_data.render()

        return toy_data
