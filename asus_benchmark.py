import time
import math

def run_cpu_stress_worker(duration, thread_id, results, stop_event):
    count = 0
    start = time.time()
    while time.time() - start < duration and not stop_event.is_set():
        for n in range(2, 2500):
            is_prime = True
            for i in range(2, int(math.sqrt(n)) + 1):
                if n % i == 0:
                    is_prime = False
                    break
        count += 1
    results[thread_id] = count
