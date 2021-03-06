from .groups import get_groups
from .initialize import initialize_normal
from .log import Log
from .loss import l2_loss_grad
from .utils import sigmoid
from datetime import datetime
from tqdm import tqdm
import jax
import jax.numpy as jnp
import random


def dnmf(
        sequence,
        component_descriptions,
        parameters,
        log_every=10,
        log_gradients=False,
        random_seed=None):
    """Perform distributed NMF on the given sequence.

    Args:

        sequence (array-like, shape `(t, [z,] y, x)`):

            The raw data (usually referred to as 'X') to factorize into `X =
            H@W`, where `H` is an array of the estimated components and `W` is
            their activity over time.

        component_descriptions (list of :class:`ComponentDescription`):

            The bounding boxes and indices of the components to estimate.

        parameters (:class:`Parameters`):

            Parameters to control the optimization.

        log_every (int):

            How often to print iteration statistics.

        log_gradients (bool):

            Whether to record gradients and factor matrices (i.e. H, B, W) after the
            1st iteration.

        random_seed (int):

            A random seed for the initialization of `H` and `W`. If not given,
            a different random seed will be used each time.
    """

    num_frames = sequence.shape[0]
    num_components = len(component_descriptions)
    groups = get_groups(component_descriptions)
    num_groups = len(groups)
    print(f"number of connected components: {num_groups}")

    if random_seed is None:
        random_seed = int(datetime.now().strftime("%Y%m%d%H%M%S"))

    component_size = None
    for description in component_descriptions:
        size = description.bounding_box.get_size()
        if component_size is not None:
            assert component_size == size, \
                "Only components of the same size are supported for now"
        else:
            component_size = size

    H_logits, W_logits, B_logits = initialize_normal(
        num_components,
        num_frames,
        component_size,
        random_seed)

    log = Log()
    l2_loss_grad_jit = jax.jit(l2_loss_grad,
                               static_argnames=['component_description'])
    update_jit = jax.jit(update)

    for iteration in tqdm(range(parameters.max_iteration)):

        total_loss_per_connected_component = 0

        for i in range(num_groups):

            # pick a random component
            component_description = random.sample(groups[i], 1)[0]
            component_bounding_box = component_description.bounding_box

            # pick a random subset of frames
            frame_indices = tuple(random.sample(
                list(range(num_frames)),
                parameters.batch_size))

            # gather the sequence data for those components/frames
            x = get_x(sequence, frame_indices, component_bounding_box)

            # compute the current loss and gradient
            loss, (grad_H_logits, grad_W_logits, grad_B_logits) = \
                l2_loss_grad_jit(
                    H_logits,
                    W_logits,
                    B_logits,
                    x,
                    component_description,
                    frame_indices)

            total_loss_per_connected_component += loss

            # update current estimate
            H_logits, W_logits, B_logits = update_jit(
                H_logits,
                W_logits,
                B_logits,
                grad_H_logits,
                grad_W_logits,
                grad_B_logits,
                parameters.step_size)
            update_end_time = timer()
            time_update += update_end_time - update_start_time

        if iteration % log_every == 0:
            log.log_time(
                            iteration,
                            float(time_loss/log_every),
                            float(time_getx/log_every),
                            float(time_update/log_every))

        # log gradients after the 1st iteration
        average_loss = \
                float(total_loss_per_group/num_groups)

        if iteration == 0 and log_gradients:
            log.log_iteration(
                        iteration,
                        average_loss,
                        grad_H_logits,
                        grad_W_logits,
                        grad_B_logits,
                        H_logits,
                        W_logits,
                        B_logits)

        elif iteration % log_every == 0:
            log.log_iteration(i, average_loss)

        if average_loss < parameters.min_loss:
            print(f"Optimization converged ({average_loss}<{parameters.min_loss})")
            break

    return sigmoid(H_logits), sigmoid(W_logits), sigmoid(B_logits), log


def get_x(sequence, frames, bounding_box):

    slices = bounding_box.to_slices()
    x = jnp.array([sequence[(t,) + slices] for t in frames])
    x = x.reshape(-1, *bounding_box.shape)

    return x


def update(H, W, B, grad_H, grad_W, grad_B, step_size):

    H = H - step_size * grad_H
    W = W - step_size * grad_W
    B = B - step_size * grad_B

    return H, W, B
