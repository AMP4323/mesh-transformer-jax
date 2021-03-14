import os
import time
import jax
import numpy as np
import optax
import haiku as hk

from transformer_shard import CausalTransformer

from loader import TextLoader

bs = 8
seq = 1024
it = 50

loader = TextLoader("data/enwik8", bs, seq)

devices = np.array(jax.devices()).reshape((1, 8))

import jax.profiler
server = jax.profiler.start_server(9999)
hk.experimental.profiler_name_scopes()

with jax.experimental.maps.mesh(devices, ('dp', 'mp')):
    opt = optax.chain(
        optax.clip_by_global_norm(1),
        optax.scale_by_adam(eps=1e-4),
        optax.scale(-1e-4),
    )

    start = time.time()
    
    # 2.7B
    # c = CausalTransformer(dim=3072, heads=8, layer_count=24, vocab=256, optimizer=opt)
    
    # 4.8B
    # c = CausalTransformer(dim=4096, heads=32, layer_count=24, vocab=256, optimizer=opt)
    
    # 10B
    c = CausalTransformer(dim=5120, heads=40, layer_count=32, vocab=256, optimizer=opt)

    param_count = hk.data_structures.tree_size(c.tpu_state['params'])

    print(f"Initialized in {time.time() - start:.06}s")
    print(f"Total parameters: {param_count}")

    start = time.time()
    sample = loader.get_samples()
    loss = c.train(sample)
    print(f"Train step compiled in {time.time() - start:.06}s")

    start = time.time()
    c.update(1)
    print(f"Update step compiled in {time.time() - start:.06}s")

    start = time.time()
    for i in range(it):
        with jax.profiler.StepTraceContext("train", step_num=i):
            sample = loader.get_samples()
            loss = c.train(sample)
            print(f"it: {i}, loss: {loss.mean()}")

            if i in range(10):
                start = time.time()
                c.update(10)
                print(f"Update step done in {time.time() - start:.06}s")
    total_time = time.time() - start
    print(f"{it} steps in {total_time:.06}s")

    total_flops = bs * seq * it * param_count * 6
    print(f"effective flops (not including attn): {total_flops / total_time:.06}")
    jax.profiler.save_device_memory_profile("memory.pprof")
